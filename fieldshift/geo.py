"""Geometría administrativa de Yucatán: SOLO el GeoJSON proporcionado."""
import json
from pathlib import Path
from shapely.geometry import shape, Point
from shapely.ops import unary_union

STATE_FILE = Path('geojson/yucatan_estado.geojson')


def read_state(path=STATE_FILE):
    data=json.loads(Path(path).read_text(encoding='utf-8'))
    if data.get('type') != 'FeatureCollection' or len(data.get('features', [])) != 1:
        raise ValueError('Se requiere un GeoJSON FeatureCollection con una sola entidad: Yucatán.')
    feature = data['features'][0]
    meta = feature.get('properties', {})
    if meta.get('id') != 'MX-YUC' or meta.get('codigo_inegi') != '31':
        raise ValueError('El GeoJSON debe corresponder al estado de Yucatán (MX-YUC / INEGI 31).')
    geom = shape(feature['geometry'])
    if geom.geom_type not in ('Polygon', 'MultiPolygon') or geom.is_empty or not geom.is_valid:
        raise ValueError('La geometría de Yucatán es inválida o no es un polígono.')
    west,south,east,north = geom.bounds
    if not (-91 < west < -89 and 19 < south < 21 and -89 < east < -87 and 21 < north < 22):
        raise ValueError('La extensión geográfica no corresponde a Yucatán.')
    return geom


def point_info(geom):
    p = geom.representative_point()
    return {'latitud': round(p.y,6), 'longitud': round(p.x,6),
            'limites':[round(v,6) for v in geom.bounds],
            'advertencia': 'Resumen regional del estado; no equivale a mediciones en parcelas.'}
