"""Parcel raster overlays. No artificial detail or interpolated field measurements."""
from datetime import date, timedelta
from functools import lru_cache
import json
import math

import numpy as np
import rasterio
from rasterio.features import geometry_mask
from rasterio.transform import from_bounds
from rasterio.warp import reproject, Resampling
from shapely.geometry import mapping, shape

from .soilgrids import WCS_URL, wcs_params


def normalized_difference(a, b):
    valid = np.isfinite(a) & np.isfinite(b) & (a >= 0) & (b >= 0) & (a + b > 0)
    return np.divide(a-b, a+b, out=np.full(a.shape, np.nan), where=valid)


def grid_spec(geom, resolution):
    west, south, east, north = geom.bounds
    width = max(1, math.ceil((east-west)*111320*math.cos(math.radians((north+south)/2))/resolution))
    height = max(1, math.ceil((north-south)*111320/resolution))
    # Bounded response and memory; larger fields are explicitly coarsened.
    factor = max(1, width/384, height/384)
    width, height = math.ceil(width/factor), math.ceil(height/factor)
    transform = from_bounds(west, south, east, north, width, height)
    return width, height, transform, max(resolution, resolution*factor)


def read_grid(source, geom, resolution, band=1):
    width, height, transform, effective = grid_spec(geom, resolution)
    result = np.full((height, width), np.nan, dtype='float32')
    with rasterio.open(source) as ds:
        if ds.crs is None:
            raise ValueError('Raster sin sistema de referencia.')
        reproject(rasterio.band(ds, band), result, src_transform=ds.transform,
                  src_crs=ds.crs, src_nodata=ds.nodata, dst_transform=transform,
                  dst_crs='EPSG:4326', dst_nodata=np.nan, resampling=Resampling.nearest)
    inside = geometry_mask([mapping(geom)], (height, width), transform, invert=True)
    result[~inside] = np.nan
    return result, effective


def pack(values, geom, resolution, **metadata):
    valid = np.isfinite(values)
    if not valid.any():
        raise ValueError('No hay píxeles válidos dentro de la parcela en esta escena.')
    return dict(bounds=list(geom.bounds), width=values.shape[1], height=values.shape[0],
                values=[[round(float(v), 4) if np.isfinite(v) else None for v in row] for row in values],
                resolution_m=round(resolution), valid_pixels=int(valid.sum()),
                statistics={'mean':round(float(values[valid].mean()),4),'min':round(float(values[valid].min()),4),'max':round(float(values[valid].max()),4)}, **metadata)


def sentinel_layer(geom, layer, before=None):
    import pystac_client
    import planetary_computer
    today = before or date.today()
    client = pystac_client.Client.open('https://planetarycomputer.microsoft.com/api/stac/v1',
                                      modifier=planetary_computer.sign_inplace, timeout=25)
    items = list(client.search(collections=['sentinel-2-l2a'], intersects=mapping(geom),
        datetime=f'{today-timedelta(days=180)}/{today}',
        query={'eo:cloud_cover': {'lt': 60}}, sortby='-datetime', max_items=12).items())
    errors = []
    for item in items[:5]:
        try:
            other = 'B04'
            native = 10
            with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN='EMPTY_DIR', GDAL_HTTP_TIMEOUT='25', GDAL_HTTP_MAX_RETRY='1'):
                nir, res = read_grid(item.assets['B08'].href, geom, native)
                second, _ = read_grid(item.assets[other].href, geom, native)
                scl, _ = read_grid(item.assets['SCL'].href, geom, native)
            # Reflectance metadata is required: never silently guess processing offsets.
            def reflectance(values, key):
                bands = item.assets[key].extra_fields.get('raster:bands', [])
                values = np.where(values > 0, values, np.nan)
                if bands and 'scale' in bands[0] and 'offset' in bands[0]:
                    return values*bands[0]['scale'] + bands[0]['offset']
                baseline = item.properties.get('s2:processing_baseline')
                if baseline is None:
                    raise ValueError('La escena no declara calibración radiométrica.')
                # Sentinel-2 L2A: PB >= 04.00 uses DN offset -1000, scale 1/10000.
                return (values - (1000 if float(baseline) >= 4 else 0))/10000
            index = normalized_difference(reflectance(nir, 'B08'), reflectance(second, other))
            # Land only, no clouds, shadows, water, snow or unclassified pixels.
            index[~np.isin(scl, [4, 5])] = np.nan
            return pack(index, geom, res, source='Sentinel-2 L2A / Microsoft Planetary Computer',
                        date=item.datetime.date().isoformat(), scene=item.id,
                        metric='NDVI', minimum=-1, maximum=1,
                        caution='Vigor/cobertura vegetal; no diagnostica enfermedades.')
        except (ValueError, OSError, RuntimeError, KeyError) as exc:
            errors.append(type(exc).__name__ + ': ' + str(exc)[:160])
    raise ValueError('Sin escena utilizable en los últimos 180 días. ' + '; '.join(errors[-2:]))


def soil_layer(geom, prop="phh2o"):
    import requests
    west, south, east, north = geom.bounds
    params = [(k,v) for k,v in wcs_params('phh2o', (south+north)/2, (west+east)/2) if k != 'SUBSET']
    params = [(k, v.replace('phh2o', prop)) for k,v in params]
    # Small padding ensures that even subpixel fields receive their native soil cell.
    params += [('SUBSET',f'long({west-.003},{east+.003})'), ('SUBSET',f'lat({south-.003},{north+.003})')]
    response = requests.get(WCS_URL, params=params, timeout=75)
    response.raise_for_status()
    with rasterio.MemoryFile(response.content) as mem:
        values, res = read_grid(mem.name, geom, 250)
    values /= 10
    low, high, metric, caution = {
        'phh2o':(3,11,'pH','No califica fertilidad integral.'),
        'soc':(0,1000,'Carbono orgánico (g/kg)','No equivale a materia orgánica medida ni permite inferir una mejora causada por la rotación.'),
        'cec':(0,200,'CEC (cmol(c)/kg)','Capacidad de intercambio catiónico estimada; no es una dosis de fertilizante ni disponibilidad de nutrientes.')
    }[prop]
    values[(values < low) | (values > high)] = np.nan
    return pack(values, geom, res, source='ISRIC SoilGrids WCS · 0–5 cm', date=None,
                metric=metric, minimum=low, maximum=(max(100, float(np.nanmax(values))) if prop in ('soc','cec') else high),
                caution='Estimación ~250 m; las parcelas pequeñas pueden contener un solo píxel. '+caution)


def vegetation_change(geom, days=30):
    latest = get_layer(geom, 'vegetation')
    before = date.fromisoformat(latest['date'])-timedelta(days=days)
    previous = sentinel_layer(geom, 'vegetation', before=before)
    def array(result):
        return np.array([[np.nan if v is None else v for v in row] for row in result['values']], dtype='float32')
    current, prior = array(latest), array(previous)
    if current.shape != prior.shape:
        raise ValueError('Las escenas no comparten la misma cuadrícula.')
    change = current-prior
    return pack(change, geom, latest['resolution_m'], source=latest['source'], date=latest['date'],
                previous_date=previous['date'], scene=latest['scene'], previous_scene=previous['scene'],
                metric='Cambio NDVI (reciente − anterior)', minimum=-2, maximum=2,
                caution=f"Comparación {previous['date']} → {latest['date']}. Solo píxeles válidos en ambas escenas. Cambios de etapa o cosecha pueden explicar la diferencia; no diagnostica estrés.")


def rainfall_layer(geom):
    from .local_climate import point_climate, recent_rain
    from .refresh import POWER
    point = geom.representative_point()
    rows, meta = point_climate(point, POWER)
    recent = recent_rain(rows)
    value = recent['lluvia_acumulada_mm']
    if value is None:
        raise ValueError('Faltan días de lluvia: no se puede presentar un acumulado completo de 30 días.')
    return pack(np.array([[value]], dtype='float32'), geom, 60000,
        source=meta['fuente'], date=recent['fin'], metric='Lluvia acumulada 30 días (mm)',
        minimum=0, maximum=max(300, value), recent=recent,
        caution=f"{recent['inicio']} → {recent['fin']}. NASA POWER consultado en ({point.y:.5f}, {point.x:.5f}); meteorología ~0.5° × 0.625°. Valor de contexto del punto interior, NO medición por píxel de parcela.")


def et0_layer(geom):
    from .local_climate import point_climate, recent_et0
    from .refresh import POWER
    point = geom.representative_point()
    rows, meta = point_climate(point, POWER)
    et = recent_et0(rows, point.y)
    if et['et0_media_mm_dia'] is None:
        raise ValueError('Faltan temperaturas diarias para estimar ET0 sin rellenar datos.')
    return pack(np.array([[et['et0_media_mm_dia']]], dtype='float32'), geom, 60000,
        source='NASA POWER + Hargreaves–Samani', date=et['fin'], metric='ET₀ de referencia estimada (mm/día)',
        minimum=0, maximum=max(10,et['et0_media_mm_dia']), summary=et,
        caution=f"{et['inicio']} → {et['fin']}. Contexto climático de la ubicación, NO evapotranspiración real del cultivo ni observación ECOSTRESS. No determina dosis de riego; requiere validación local.")


def moisture_layer(geom):
    """NASA-rendered SMAP L4 moisture, at its real 9 km model resolution."""
    import base64
    import requests
    import xml.etree.ElementTree as ET
    url = 'https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi'
    name = 'SMAP_L4_Analyzed_Surface_Soil_Moisture'
    caps = requests.get(url, params={'service':'WMS', 'request':'GetCapabilities'}, timeout=30)
    caps.raise_for_status()
    ns = {'w':'http://www.opengis.net/wms'}
    root = ET.fromstring(caps.content)
    layer = next(e for e in root.findall('.//w:Layer', ns) if e.findtext('w:Name', namespaces=ns) == name)
    observed = layer.find('w:Dimension', ns).attrib['default']
    west, south, east, north = geom.bounds
    width = height = 256
    image = requests.get(url, params={'service':'WMS', 'version':'1.1.1', 'request':'GetMap',
        'layers':name, 'styles':'', 'srs':'EPSG:4326', 'bbox':f'{west},{south},{east},{north}',
        'width':width, 'height':height, 'format':'image/png', 'transparent':'true', 'time':observed}, timeout=45)
    image.raise_for_status()
    with rasterio.MemoryFile(image.content) as mem:
        with mem.open() as ds:
            rgba = ds.read()
    if rgba.shape[0] != 4:
        raise ValueError('NASA no entregó una imagen RGBA de humedad.')
    inside = geometry_mask([mapping(geom)], (height, width), from_bounds(west,south,east,north,width,height), invert=True)
    rgba[3, ~inside] = 0
    if not np.any(rgba[3]):
        raise ValueError('NASA no tiene humedad válida para esta parcela en la última fecha disponible.')
    with rasterio.MemoryFile() as mem:
        with mem.open(driver='PNG', width=width, height=height, count=4, dtype='uint8') as ds:
            ds.write(rgba)
        encoded = base64.b64encode(mem.read()).decode('ascii')
    return dict(bounds=list(geom.bounds), image='data:image/png;base64,'+encoded,
        source='NASA GIBS / SMAP L4 · análisis con modelo', date=observed,
        metric='Humedad volumétrica superficial (m³/m³)', resolution_m=9000,
        legend='https://gibs.earthdata.nasa.gov/legends/SMAP_Analyzed_Soil_Moisture_H.png',
        caution='Resolución del modelo ~9 km, NO parcelaria. Colores y escala originales NASA. La imagen no proporciona consultas numéricas de cada píxel.')


@lru_cache(maxsize=32)
def cached_layer(geometry_json, layer, day, comparison_days=30):
    geom = shape(json.loads(geometry_json))
    if layer == 'moisture':
        return moisture_layer(geom)
    if layer == 'evapotranspiration':
        return et0_layer(geom)
    if layer == 'change':
        return vegetation_change(geom, comparison_days)
    if layer == 'rainfall':
        return rainfall_layer(geom)
    if layer in ('soil','carbon','cec'):
        return soil_layer(geom, {'soil':'phh2o','carbon':'soc','cec':'cec'}[layer])
    return sentinel_layer(geom, layer)


def get_layer(geom, layer, comparison_days=30):
    if layer not in ('moisture', 'vegetation', 'soil', 'change', 'rainfall', 'evapotranspiration', 'carbon', 'cec'):
        raise ValueError('Capa no reconocida.')
    if not 15 <= comparison_days <= 180:
        raise ValueError('La comparación de vegetación debe ser de 15 a 180 días.')
    return cached_layer(json.dumps(mapping(geom), sort_keys=True), layer, date.today().isoformat(), comparison_days)
