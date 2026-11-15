"""Análisis de una parcela GeoJSON real, sin inventar resolución satelital local.

El contorno es geográfico. Se consulta una muestra SoilGrids en un punto
representativo *dentro* de la parcela; el clima sigue siendo NASA POWER
regional compartido, no una serie calculada píxel a píxel para el polígono.
"""
from __future__ import annotations

import hashlib
from math import isfinite
from pathlib import Path

from pyproj import Geod
from shapely.geometry import Polygon, Point, shape, mapping
from shapely.ops import unary_union

from .geo import read_state
from .power import read_csv
from .soilgrids import COVERAGES, approximate_texture, fetch_layer
from .engine import analyze
from .rotation import compare_rotations
from .climate import summary_by_crop
from .history import observed_range
from .local_climate import recent_rain, recent_et0

GEOD = Geod(ellps='WGS84')
MAX_VERTICES = 500
MIN_AREA_HA = 0.001
MAX_AREA_HA = 100_000


class InvalidParcel(ValueError):
    """Error de datos geométricos que debe aparecer como 422 en la API."""


def _geometry_from_geojson(value):
    if not isinstance(value, dict):
        raise InvalidParcel('El GeoJSON debe ser un objeto JSON.')
    obj = value
    if obj.get('type') == 'FeatureCollection':
        features = obj.get('features')
        if not isinstance(features, list) or not features or len(features) > 20:
            raise InvalidParcel('FeatureCollection debe contener entre 1 y 20 entidades.')
        geoms = [_geometry_from_geojson(f) for f in features]
        return unary_union(geoms)
    if obj.get('type') == 'Feature':
        return _geometry_from_geojson(obj.get('geometry'))
    if obj.get('type') not in ('Polygon', 'MultiPolygon'):
        raise InvalidParcel('GeoJSON debe contener Polygon o MultiPolygon.')
    try:
        geom = shape(obj)
    except (ValueError, TypeError, KeyError, IndexError) as exc:
        raise InvalidParcel('Coordenadas GeoJSON inválidas.') from exc
    return geom


def _ring_from_matrix(points):
    if not isinstance(points, list) or not 3 <= len(points) <= MAX_VERTICES:
        raise InvalidParcel('La matriz necesita entre 3 y 500 vértices.')
    coordinates = []
    for pt in points:
        if isinstance(pt, dict):
            lon = pt.get('longitud', pt.get('lon'))
            lat = pt.get('latitud', pt.get('lat'))
        elif isinstance(pt, (list, tuple)) and len(pt) == 2:
            lon, lat = pt  # GeoJSON [longitud, latitud]
        else:
            raise InvalidParcel('Cada vértice necesita [longitud, latitud] o {longitud, latitud}.')
        if (isinstance(lon, bool) or isinstance(lat, bool)
                or not isinstance(lon, (int, float)) or not isinstance(lat, (int, float))
                or not (isfinite(lon) and isfinite(lat))
                or not (-180 <= lon <= 180 and -90 <= lat <= 90)):
            raise InvalidParcel('Coordenadas inválidas: usa longitud y latitud WGS 84.')
        coordinates.append((float(lon), float(lat)))
    if coordinates[0] != coordinates[-1]:
        coordinates.append(coordinates[0])
    return Polygon(coordinates)


def validate_parcel(*, geojson=None, points=None, state_geom=None):
    """Devuelve (polígono válido, superficie en ha, punto interior)."""
    if (geojson is None) == (points is None):
        raise InvalidParcel('Indica GeoJSON o matriz de puntos, pero no ambos.')
    geom = _geometry_from_geojson(geojson) if geojson is not None else _ring_from_matrix(points)
    if geom.is_empty or geom.geom_type not in ('Polygon', 'MultiPolygon') or not geom.is_valid:
        raise InvalidParcel('El contorno se cruza, está vacío o no es un polígono válido.')
    vertices = sum(len(p.exterior.coords) + sum(len(r.coords) for r in p.interiors)
                   for p in ([geom] if geom.geom_type == 'Polygon' else geom.geoms))
    if vertices > MAX_VERTICES + 25:
        raise InvalidParcel('Polígono demasiado complejo (máximo 500 vértices aproximadamente).')
    coords = [pt for p in ([geom] if geom.geom_type == 'Polygon' else geom.geoms)
              for ring in [p.exterior, *p.interiors] for pt in ring.coords]
    if not all(isfinite(x) and isfinite(y) and -180 <= x <= 180 and -90 <= y <= 90 for x,y in coords):
        raise InvalidParcel('GeoJSON requiere coordenadas longitud/latitud WGS 84 (RFC 7946).')
    area_m2, _ = GEOD.geometry_area_perimeter(geom)
    area_ha = abs(area_m2) / 10000
    if not MIN_AREA_HA <= area_ha <= MAX_AREA_HA:
        raise InvalidParcel(f'Extensión fuera de límites ({area_ha:.4f} ha). Aceptado: 0.001–100,000 ha.')
    state_geom = state_geom if state_geom is not None else read_state()
    overlap = geom.intersection(state_geom).area / geom.area
    if overlap < 0.99:
        raise InvalidParcel('La parcela debe estar dentro del estado de Yucatán (mínimo 99 % de superficie).')
    interior = geom.representative_point()
    if not state_geom.covers(interior):
        interior = geom.intersection(state_geom).representative_point()
    return geom, round(area_ha, 4), interior


def parcel_soil(point, get_layer=fetch_layer):
    """Consultas SoilGrids WCS 0–5 cm en ubicación interior y caché por coordenada."""
    lon, lat = round(point.x, 6), round(point.y, 6)
    sample_id = 'PAR-' + hashlib.sha256(f'{lon:.6f},{lat:.6f}'.encode()).hexdigest()[:16]
    vals = {prop: round(get_layer(prop, lat, lon, sample_id), 2) for prop in COVERAGES}
    ph, sand, silt, clay = vals['phh2o'], vals['sand'], vals['silt'], vals['clay']
    if not (3 <= ph <= 11 and all(0 <= x <= 100 for x in (sand, silt, clay))
            and 85 <= sand+silt+clay <= 115):
        raise ValueError('SoilGrids devolvió valores de pH o textura incoherentes.')
    return {
        'id':sample_id, 'latitud':lat, 'longitud':lon,
        'source':'ISRIC SoilGrids WCS (estimación 0-5 cm, NO muestreo del terreno)',
        'ph':ph, 'texture':approximate_texture(sand,silt,clay),
        'sand_pct':sand, 'silt_pct':silt, 'clay_pct':clay,
        'depth_cm':None,
        'depth_status':'Profundidad efectiva sin medición en la parcela',
        'raster_interval_cm':[0,5],
        'spatial_method':'Muestra WCS en punto interior representativo; NO promedio del polígono',
    }


def run_parcel_analysis(geom, area_ha, interior, month, climate_file, catalog, history,
                        get_soil=parcel_soil, get_climate=None, management=None):
    if not Path(climate_file).exists():
        raise FileNotFoundError('Falta el historial NASA POWER: ejecuta python main.py descargar.')
    climate_meta = {'fuente':'NASA POWER, media regional de siete puntos de Yucatán', 'es_promedio_estatal':True}
    if get_climate is None:
        climate = read_csv(climate_file)
    else:
        climate, climate_meta = get_climate(interior, climate_file)
    soil = get_soil(interior)
    crops = analyze(climate, soil, catalog, month)
    # The shared demonstration history does not describe this field.
    history_source = str((history or {}).get('source', '')).lower()
    if any(word in history_source for word in ('demo', 'invent', 'ejemplo')):
        history = None
    rotations = compare_rotations(climate, soil, catalog, month, history, management=management)
    summary = summary_by_crop(climate, month, 90)
    climate_metrics = summary.get('metrics', {})
    return {
        'proyecto':'NEEK / FieldShift Yucatán',
        'metodo':'estimación con suelo del punto interior y clima de la ubicación consultada',
        'parcela':{
            'geometria':mapping(geom),
            'superficie_ha':area_ha,
            'punto_muestreado':{'latitud':round(interior.y,6),'longitud':round(interior.x,6)},
            'resolucion':'La geometría delimita la parcela, NO convierte datos regionales en mediciones locales',
        },
        'mes_siembra':month,
        'manejo':management or {},
        'periodo_clima':observed_range(climate),
        'clima':{
            'fuente':climate_meta['fuente'],
            'ubicacion_consulta':climate_meta,
            'reciente_30_dias':recent_rain(climate),
            'et0_30_dias':recent_et0(climate, interior.y),
            'lluvia_mediana_historica_ciclo_90d_mm':climate_metrics.get('rain_total_mm'),
            'anios_utilizados':summary.get('years_used', []),
            'humedad_suelo':None,
            'salud_vegetacion_local':None,
        },
        'suelo':{
            'ph':soil['ph'], 'textura':soil['texture'],
            'arena_pct':soil['sand_pct'],'limo_pct':soil['silt_pct'],
            'arcilla_pct':soil['clay_pct'],
            'profundidad_efectiva_cm':None,
            'estado_calidad':'informacion_parcial',
            'interpretacion':'pH y textura estimados, NO una calificación integral de fertilidad',
            'fuente':soil['source'],
            'resolucion_aproximada_m':250,
            'punto_muestreado':soil['id'],
        },
        'cultivos':crops,
        'rotaciones':rotations,
        'advertencias':[
            'La parcela se delimita realmente, pero NO existe un promedio de todos sus píxeles de suelo.',
            'pH y textura provienen de un SOLO punto SoilGrids, en capa superficial 0-5 cm.',
            'NASA POWER es una celda climática consultada por ubicación (o referencia regional en modo offline), NO un pronóstico ni un microclima del polígono.',
            'Las capas de humedad y NDVI se consultan por separado; no intervienen en los puntajes agronómicos.',
            'No se estima la fertilidad completa del suelo ni reducciones reales de pérdidas agrícolas.',
            'Profundidad efectiva requiere medición de campo y su ausencia reduce confianza.',
            ('Se utiliza el historial declarado para esta parcela.' if history else
             'Sin historial agrícola declarado: las propuestas no incluyen una supuesta rotación actual.'),
            'Los puntajes y rotaciones son reglas heurísticas y deben verificarse con un técnico agrícola.',
        ],
    }
