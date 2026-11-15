"""Resumen NDVI exploratorio (Sentinel-2 L2A de Planetary Computer).

Observación histórica de vegetación, no idoneidad futura ni diagnóstico de suelo.
Los activos COG se leen de forma remota y se recortan al polígono.
"""
from __future__ import annotations

from datetime import date
import math
from statistics import median


def compute_ndvi(red, nir, valid_mask):
    """NDVI con pares rojos/NIR válidos. Devuelve una lista de números entre -1 y 1."""
    import numpy as np
    a = np.asarray(red, dtype='float64')
    b = np.asarray(nir, dtype='float64')
    valid = np.asarray(valid_mask, dtype=bool) & np.isfinite(a) & np.isfinite(b)
    valid &= (a > 0) & (b > 0) & (a+b > 0)
    with np.errstate(divide='ignore', invalid='ignore'):
        ndvi = np.divide(b-a, b+a, out=np.full_like(a, np.nan), where=valid)
    return ndvi[valid & np.isfinite(ndvi) & (ndvi >= -1) & (ndvi <= 1)]


def summarize_ndvi_samples(samples, *, min_valid=20):
    """Resumen determinista para tests offline; sin confundir muestras con píxeles de campo completos."""
    values = [float(x) for x in samples if math.isfinite(float(x)) and -1 <= float(x) <= 1]
    if len(values) < min_valid:
        return {'ndvi_medio': None, 'pixeles_validos': len(values), 'calidad': 'datos_insuficientes'}
    return {'ndvi_medio': round(sum(values)/len(values), 4), 'pixeles_validos': len(values),
            'calidad': 'observacion_usable'}


def _read_scene_ndvi(item, geom):
    """Lee solo la ventana del polígono; usa clases SCL para excluir nubes/sombra."""
    import numpy as np
    import rasterio
    from rasterio.mask import mask
    from rasterio.vrt import WarpedVRT
    from rasterio.enums import Resampling
    from shapely.geometry import mapping
    from shapely.ops import transform
    from pyproj import Transformer

    if not all(k in item.assets for k in ('B04','B08','SCL')):
        raise ValueError('La escena no tiene bandas B04/B08/SCL.')
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN='EMPTY_DIR'):
        with rasterio.open(item.assets['B04'].href) as red_ds, \
             rasterio.open(item.assets['B08'].href) as nir_ds, \
             rasterio.open(item.assets['SCL'].href) as scl_ds:
            if red_ds.crs is None:
                raise ValueError('La escena no tiene CRS.')
            projector = Transformer.from_crs('EPSG:4326', red_ds.crs, always_xy=True)
            projected = transform(projector.transform, geom)
            area = [mapping(projected)]
            with WarpedVRT(nir_ds, crs=red_ds.crs, transform=red_ds.transform,
                           width=red_ds.width, height=red_ds.height,
                           resampling=Resampling.bilinear) as nir_match, \
                 WarpedVRT(scl_ds, crs=red_ds.crs, transform=red_ds.transform,
                           width=red_ds.width, height=red_ds.height,
                           resampling=Resampling.nearest) as scl_match:
                red, _ = mask(red_ds, area, crop=True, filled=True, nodata=0)
                nir, _ = mask(nir_match, area, crop=True, filled=True, nodata=0)
                scl, _ = mask(scl_match, area, crop=True, filled=True, nodata=0)
                if red.shape != nir.shape or red.shape != scl.shape:
                    raise ValueError('No se pudieron alinear las bandas Sentinel-2.')
                # Sentinel SCL: 4 vegetación, 5 suelo desnudo, 6 agua, 7 sin clasificación.
                # 0,1,2,3,8,9,10,11 se excluyen (nodata/saturación/oscuro/sombra/nubes/nieve).
                valid_scl = np.isin(scl[0], [4,5,6,7])
                candidates = valid_scl & (red[0]>0) & (nir[0]>0)
                vals = compute_ndvi(red[0], nir[0], candidates)
                return summarize_ndvi_samples(vals)


def retrieve_ndvi(geom, start=2023, end=2025, month=6, months=3,
                  max_cloud=35.0, scenes_per_year=2, end_date=None):
    """Busca hasta N escenas poco nubladas por año, y recorta el raster al polígono.

    La media de escenas no equivale a media anual ni sirve como señal de siembra.
    """
    from datetime import timedelta
    from shapely.geometry import mapping
    import pystac_client
    import planetary_computer

    if not (2020 <= start <= end <= date.today().year and 1 <= month <= 12
            and 1 <= months <= 6 and 0 < max_cloud <= 100 and 1 <= scenes_per_year <= 5):
        raise ValueError('Parámetros Planetary Computer fuera de los límites permitidos.')
    api = pystac_client.Client.open(
        'https://planetarycomputer.microsoft.com/api/stac/v1',
        modifier=planetary_computer.sign_inplace)
    scenes = []
    errors = []
    for year in range(start, end+1):
        first = date(year, month, 1)
        # Ventana fija en el mismo periodo de cada año, no promedio anual.
        next_month = (year*12 + month - 1 + months)
        last = date((next_month//12), (next_month%12)+1, 1) - timedelta(days=1)
        last = min(last, date(end,12,31), end_date or date.today())
        if first > last:
            continue
        search = api.search(collections=['sentinel-2-l2a'],
            intersects=mapping(geom), datetime=f'{first.isoformat()}/{last.isoformat()}',
            query={'eo:cloud_cover': {'lt': max_cloud}}, max_items=120)
        # El orden del catálogo no garantiza cobertura de toda la ventana: ordenar por nubes.
        items = sorted(list(search.items()), key=lambda x: float(x.properties.get('eo:cloud_cover',100)))
        for item in items[:scenes_per_year]:
            try:
                summary = _read_scene_ndvi(item, geom)
                scenes.append({
                    'fecha': item.datetime.date().isoformat() if item.datetime else first.isoformat(),
                    'escena': item.id,
                    'nubes_escena_pct': item.properties.get('eo:cloud_cover'),
                    **summary})
            except (ValueError, OSError, RuntimeError) as exc:
                errors.append({'escena': item.id, 'motivo': type(exc).__name__})
    means = [r['ndvi_medio'] for r in scenes if r['ndvi_medio'] is not None]
    return {
        'fuente': 'Microsoft Planetary Computer / Sentinel-2 L2A',
        'intervalo': f'{start}-{end}', 'mes_inicio': month, 'meses_ventana': months,
        'parcela_limites': [round(v,6) for v in geom.bounds],
        'ndvi_mediana_de_escenas_validas': round(median(means),4) if means else None,
        'escenas': scenes, 'errores_lectura': errors,
        'estado': 'evidencia_disponible' if means else 'datos_insuficientes',
        'interpretacion': 'NDVI histórico observacional: indica cobertura/vigor relativo de vegetación existente; NO determina fertilidad, especie ni viabilidad futura.',
        'advertencias': ['La cobertura de nubes por escena NO mide el porcentaje de nubes dentro de la parcela.',
            'Una parcela desnuda o en barbecho puede tener NDVI bajo aun siendo apta.',
            'Este cálculo rápido no corrige en detalle desplazamientos ni offsets radiométricos entre productos; requiere revisión antes de análisis científico.',
            'El índice no afecta el puntaje del semáforo ni las rotaciones en esta versión.']
    }
