"""Muestreo edafológico exploratorio de Yucatán mediante ISRIC SoilGrids WCS.

NO hay un perfil único válido para el estado. 7 puntos interiores se consultan
independientemente; los puntos NO delimitan zonas agrícolas ni parcelas.
SoilGrids no entrega profundidad efectiva hasta roca firme: depth_cm = None.
"""
from io import BytesIO
import json
from pathlib import Path
from statistics import median

import numpy as np
import rasterio
import requests

from .regional import sample_points

WCS_URL = 'https://maps.isric.org/mapserv'
PROVIDER_URL = 'https://isric.org/explore/soilgrids'
COVERAGES = ('phh2o', 'sand', 'silt', 'clay')
SOIL_FILE = Path('data/suelo_soilgrids_yucatan.json')
POINTS_GEOJSON = Path('results/puntos_suelo_yucatan.geojson')
CACHE_DIR = Path('data/cache_soilgrids')
SAMPLE_RADIUS_DEGREES = 0.009  # pequeño entorno alrededor de cada punto, NO es parcela


def wcs_params(prop, lat, lon, radius=SAMPLE_RADIUS_DEGREES):
    if prop not in COVERAGES:
        raise ValueError('Variable SoilGrids no reconocida.')
    if not (-91 < lon < -86 and 18 < lat < 23):
        raise ValueError('La muestra está fuera del entorno de Yucatán.')
    # WCS 2.0.1: SUBSET es repetible. WCS en WGS84, extensión pequeña.
    return [
        ('map', f'/map/{prop}.map'),
        ('SERVICE', 'WCS'), ('VERSION', '2.0.1'),
        ('REQUEST', 'GetCoverage'),
        ('COVERAGEID', f'{prop}_0-5cm_mean'),
        ('FORMAT', 'GEOTIFF_INT16'),
        ('SUBSET', f'long({lon-radius:.6f},{lon+radius:.6f})'),
        ('SUBSET', f'lat({lat-radius:.6f},{lat+radius:.6f})'),
        ('SUBSETTINGCRS', 'http://www.opengis.net/def/crs/EPSG/0/4326'),
        ('OUTPUTCRS', 'http://www.opengis.net/def/crs/EPSG/0/4326'),
    ]


def decode_tiff(payload):
    """Devuelve mediana de píxeles válidos. SoilGrids guarda unidades x10."""
    try:
        with rasterio.MemoryFile(payload) as mem:
            with mem.open() as ds:
                data = ds.read(1, masked=True)
                values = np.asarray(data.compressed(), dtype='float64')
                values = values[np.isfinite(values) & (values != -32768)]
                if not len(values):
                    raise ValueError('GeoTIFF de SoilGrids sin valores válidos.')
                return float(median(values) / 10.0)
    except (rasterio.errors.RasterioIOError, TypeError) as exc:
        raise ValueError('SoilGrids no devolvió un GeoTIFF legible (posible error del servidor WCS).') from exc


def fetch_layer(prop, lat, lon, sample_id, cache_dir=CACHE_DIR, request_get=None):
    cache = Path(cache_dir) / f'{sample_id}_{prop}_0-5cm_mean.tif'
    if cache.is_file():
        payload = cache.read_bytes()
    else:
        if request_get is None:
            request_get = requests.get
        try:
            response = request_get(WCS_URL, params=wcs_params(prop, lat, lon), timeout=75)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise RuntimeError(f'Error WCS {prop} en {sample_id}: {type(exc).__name__}') from exc
        payload = response.content
        # Evita almacenar XML/HTML de error del servicio en caché.
        if payload[:4] not in (b'II*\x00', b'MM\x00*', b'II+\x00', b'MM\x00+'):
            raise RuntimeError(f'WCS {prop} en {sample_id} no devolvió un TIFF. Comprueba el servicio ISRIC.')
        value = decode_tiff(payload)
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(payload)
        return value
    return decode_tiff(payload)


def approximate_texture(sand, silt, clay):
    """Clases SIMPLIFICADAS para el catálogo, no sustituyen clasificación USDA."""
    if sand >= 85 and clay < 10:
        return 'arenosa'
    if clay >= 40:
        return 'arcillosa'
    if 27 <= clay < 40:
        return 'franco-arcillosa'
    if sand >= 50 and clay < 27:
        return 'franco-arenosa'
    if silt >= 50 and clay < 27:
        return 'franco-limosa'
    return 'franca'


def build_sample(point, idx, get_layer=fetch_layer):
    lat, lon = point['latitud'], point['longitud']
    sample_id = f'YUC-{idx:02d}'
    vals = {p: round(get_layer(p, lat, lon, sample_id), 2) for p in COVERAGES}
    ph = vals['phh2o']
    sand, silt, clay = vals['sand'], vals['silt'], vals['clay']
    if not (3 <= ph <= 11 and all(0 <= a <= 100 for a in (sand, silt, clay))
            and 85 <= sand+silt+clay <= 115):
        raise ValueError(f'Valores SoilGrids incoherentes en {sample_id}: {vals}')
    return {
        'id': sample_id, 'latitud': lat, 'longitud': lon,
        'source': 'ISRIC SoilGrids 2.0 WCS (estimación, NO medición local)',
        'ph': ph,
        'texture': approximate_texture(sand, silt, clay),
        'texture_method': 'aproximación con arena/limo/arcilla 0-5 cm, NO clase USDA exacta',
        'sand_pct': sand, 'silt_pct': silt, 'clay_pct': clay,
        'depth_cm': None,
        'depth_status': 'No estimable a partir de las capas SoilGrids utilizadas; requiere verificación de profundidad efectiva en terreno.',
        'raster_interval_cm': [0, 5],
        'spatial_method': 'mediana local de píxeles de una pequeña ventana del WCS; sin polígono de influencia',
    }


def download_soils(geom, output=SOIL_FILE, get_layer=fetch_layer):
    points = sample_points(geom)
    samples, failures = [], []
    for idx, point in enumerate(points, 1):
        try:
            samples.append(build_sample(point, idx, get_layer))
        except (ValueError, RuntimeError, OSError) as exc:
            failures.append({'id':f'YUC-{idx:02d}', 'tipo':type(exc).__name__, 'detalle':str(exc)[:150]})
    if not samples:
        raise RuntimeError('No se obtuvo ningún perfil válido de SoilGrids. No se usará suelo simulado.')
    output = Path(output)
    doc = {
        'source':'ISRIC SoilGrids 2.0 via WCS',
        'provider_url':PROVIDER_URL,
        'license':'CC-BY-4.0 (citar a ISRIC SoilGrids)',
        'region_geojson':'geojson/yucatan_estado.geojson',
        'metodo':'7 puntos interiores del GeoJSON, capas estimadas 0-5 cm con entorno local; no hay polígonos de zonas.',
        'resolucion_fuente_m':'aproximadamente 250',
        'fecha':'Capa SoilGrids estática, no corresponde específicamente a 2023-2025.',
        'advertencias':[
            'pH y textura son predicciones del modelo SoilGrids, NO análisis de laboratorio.',
            'SoilGrids no proporciona aquí profundidad efectiva hasta roca, por eso depth_cm=null.',
            'ISRIC desaconseja usar SoilGrids como medición de precisión a escala de parcela.',
            'La evaluación climática conserva promedios NASA POWER de siete muestras: no es clima puntual de cada punto.',
        ],
        'muestras':samples,
        'fallos':failures,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding='utf-8')
    features = []
    for sample in samples:
        features.append({'type':'Feature', 'geometry':{'type':'Point', 'coordinates':[sample['longitud'],sample['latitud']]},
                         'properties':{'id':sample['id'], 'ph':sample['ph'], 'texture':sample['texture'],
                                       'depth_cm':None,'source':'SoilGrids 2.0 estimado'}})
    fc = {'type':'FeatureCollection','features':features}
    POINTS_GEOJSON.parent.mkdir(parents=True, exist_ok=True)
    POINTS_GEOJSON.write_text(json.dumps(fc, ensure_ascii=False, indent=2), encoding='utf-8')
    return doc


def read_soil_samples(path=SOIL_FILE):
    doc=json.loads(Path(path).read_text(encoding='utf-8'))
    if doc.get('source') != 'ISRIC SoilGrids 2.0 via WCS':
        raise ValueError('La fuente del archivo no corresponde a SoilGrids WCS.')
    samples=doc.get('muestras', [])
    if not samples or any(not s.get('id') or s.get('ph') is None or not s.get('texture') for s in samples):
        raise ValueError('Las muestras están incompletas o mal formadas.')
    return doc
