"""Cruza puntos SoilGrids con cartografía REAL INEGI Serie II (Clave_WRB).

No convierte calificadores cartográficos en profundidades medidas. Solo genera
intervalos orientativos de presencia de roca del SUELO DOMINANTE del polígono.
"""
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile, BadZipFile
from collections import defaultdict
import json
import re

import fiona
from pyproj import Transformer, CRS
from shapely.geometry import Point, shape

from .soilgrids import SOIL_FILE, read_soil_samples

DEPTH_MAP = Path('data/profundidad_inegi_yucatan.json')
SOURCE_URL = 'https://www.inegi.org.mx/app/biblioteca/ficha.html?upc=794551131916'
GUIDE_URL = 'https://www.inegi.org.mx/contenidos/productos/prod_serv/contenidos/espanol/bvinegi/productos/nueva_estruc/702825231606.pdf'

# INEGI, Guía de edafología Serie II: Lítico <10, epiléptico 0-49,
# endoléptico 50-100 cm. Son límites de intervalo, no datos medidos.
QUALIFIERS = {
    'li': ('lítico', 0, 10),
    'lep': ('epiléptico', 0, 50),
    'len': ('endoléptico', 50, 100),
}


def interpret_key(key):
    """Solo calificador del suelo dominante: el primer segmento de Clave_WRB."""
    if not isinstance(key, str) or not key.strip():
        return {'calificador': None, 'intervalo_cm': None, 'razon': 'Clave_WRB ausente'}
    primary = key.strip().split('/')[0].split('+')[0].strip()
    # No inferir a partir de claves de otros grupos ni de pedregosidad R/r.
    soil_type = primary[:2].upper()
    qualifiers = primary[2:].lower()
    # Segmentos codificados juntos: sufijos más específicos primero.
    for suffix in ('lep', 'len', 'li'):
        if qualifiers.endswith(suffix):
            name, lo, hi = QUALIFIERS[suffix]
            return {'suelo_dominante': soil_type,
                    'calificador': name, 'codigo': suffix,
                    'intervalo_cm': [lo, hi],
                    'razon': 'Intervalo cartográfico asociado al calificador del suelo dominante.'}
    return {'suelo_dominante': soil_type, 'calificador': None,
            'intervalo_cm': None,
            'razon': 'Sin calificador de profundidad inequívoco en el suelo dominante.'}


def _safe_unzip(zfile, target):
    """Solo lectura de ZIP; bloquea entradas fuera del directorio y bombas simples."""
    target = Path(target).resolve()
    with ZipFile(zfile) as z:
        expanded = 0
        for info in z.infolist():
            out = (target / info.filename).resolve()
            if not out.is_relative_to(target):
                raise ValueError('ZIP con rutas inseguras.')
            expanded += info.file_size
            if expanded > 1_500_000_000:
                raise ValueError('Archivo excesivamente grande (>1.5 GB descomprimido).')
        z.extractall(target)


def _input_layers(path):
    path = Path(path)
    if path.is_dir():
        return sorted(p for p in path.rglob('*') if p.suffix.lower() in ('.shp','.gpkg','.geojson','.json'))
    if path.suffix.lower() in ('.shp','.gpkg','.geojson','.json'):
        return [path]
    raise ValueError('Usa .zip, .shp, .gpkg, .geojson o una carpeta con datos vectoriales oficiales.')


def _key_field(props, campo=None):
    fields = list(props)
    if campo:
        return next((f for f in fields if f.lower() == campo.lower()), None)
    for key in ('clave_wrb', 'clavewrb', 'clave edafológica', 'clave_eda'):
        match = next((f for f in fields if f.lower().strip() == key), None)
        if match:
            return match
    return None


def _scan_layer(path, observations, campo=None, crs_faltante=None):
    found_schema = False
    results = defaultdict(list)
    # GeoPackage admite varias capas; para SHP y GeoJSON, una sola.
    try:
        layers = fiona.listlayers(path)
    except Exception:
        layers = [None]
    for layer in layers:
        try:
            with fiona.open(path, layer=layer) as src:
                if src.schema.get('geometry','').lower() not in ('polygon','multipolygon','3d polygon','3d multipolygon'):
                    continue
                keyfield = _key_field(src.schema['properties'], campo)
                if keyfield is None:
                    continue
                found_schema = True
                # Un .shp sin .prj no indica su sistema de referencia.
                # Permitir asignación explícita SOLO con --crs-faltante y comprobar
                # que al menos uno de los puntos quede dentro de la extensión del SHP.
                if src.crs:
                    layer_crs = CRS.from_user_input(src.crs)
                elif crs_faltante:
                    layer_crs = CRS.from_user_input(crs_faltante)
                else:
                    raise ValueError('La cartografía carece de CRS; usa --crs-faltante EPSG:6362 únicamente si confirmaste que es INEGI Serie II nacional.')
                trans = Transformer.from_crs(CRS.from_epsg(4326), layer_crs, always_xy=True)
                native = {p['id']: Point(*trans.transform(p['longitud'], p['latitud'])) for p in observations}
                if not src.crs and crs_faltante:
                    l, b, r, t = src.bounds
                    if not any(l <= point.x <= r and b <= point.y <= t for point in native.values()):
                        raise ValueError('El CRS asignado no ubica ninguna muestra dentro de la extensión del SHP: revisa --crs-faltante y el origen de los datos.')
                xs = [pt.x for pt in native.values()]
                ys = [pt.y for pt in native.values()]
                # Filtro espacial, con pequeño margen en unidades del CRS.
                dx=max((max(xs)-min(xs))*0.01, 1e-3)
                dy=max((max(ys)-min(ys))*0.01, 1e-3)
                bbox = (min(xs)-dx,min(ys)-dy,max(xs)+dx,max(ys)+dy)
                for feature in src.filter(bbox=bbox):
                    if not feature.geometry:
                        continue
                    geom = shape(feature.geometry)
                    for id_, point in native.items():
                        if geom.covers(point):
                            value = feature.properties.get(keyfield)
                            interpreted=interpret_key(value)
                            results[id_].append({'clave_wrb': value, **interpreted,
                                                 'archivo':Path(path).name, 'capa':str(layer or ''),
                                                 'campo':keyfield})
        except (fiona.errors.DriverError, OSError):
            continue
    return found_schema, results


def import_inegi(path, output=DEPTH_MAP, campo=None, samples_path=SOIL_FILE, crs_faltante=None):
    """Crear archivo separado, sin modificar la descarga SoilGrids ni inventar cm."""
    path=Path(path).expanduser()
    if not path.exists():
        raise ValueError(f'Archivo INEGI no encontrado: {path}')
    samples=read_soil_samples(samples_path)['muestras']
    with TemporaryDirectory(prefix='fieldshift_inegi_') as tmp:
        if path.suffix.lower() == '.zip':
            try:
                _safe_unzip(path,tmp)
            except BadZipFile as exc:
                raise ValueError('El ZIP de INEGI está dañado.') from exc
            layers = _input_layers(Path(tmp))
        else:
            layers = _input_layers(path)
        if not layers:
            raise ValueError('No se encontraron archivos geográficos vectoriales.')
        matched = defaultdict(list)
        recognized=False
        for file in layers:
            schema, hits=_scan_layer(file,samples,campo=campo,crs_faltante=crs_faltante)
            recognized = recognized or schema
            for ident, matches in hits.items():
                matched[ident].extend(matches)
        if not recognized:
            raise ValueError('No se encontró una capa poligonal con campo Clave_WRB. Usa INEGI Serie II o --campo NOMBRE.')
        result=[]
        for sample in samples:
            hits = matched.get(sample['id'],[])
            # La cartografía puede contener varias unidades que coinciden en límites.
            if len(hits)==1:
                chosen=hits[0]
                status='coincidencia_unica' if chosen['intervalo_cm'] else 'sin_calificador_de_profundidad'
            elif len(hits)==0:
                chosen=None
                status='sin_cobertura_en_cartografia'
            else:
                chosen=None
                status='coincidencia_ambigua'
            result.append({'id':sample['id'], 'latitud':sample['latitud'], 'longitud':sample['longitud'],
                           'estado':status, 'evidencia':chosen,
                           'numero_poligonos_coincidentes':len(hits),
                           'profundidad_medida_cm':None,
                           'nota':'Intervalo del suelo dominante; puede no representar cada parcela.'})
    doc={'source':'INEGI edafología Serie II 1:250 000 (importación local)',
         'crs_declarado_para_capas_sin_prj': crs_faltante,
         'archivo_ingresado':path.name, 'fuente_url':SOURCE_URL,'documentacion':GUIDE_URL,
         'tipo':'intervalos_inferidos_del_calificador_WRB_NO_mediciones',
         'advertencia':'La profundidad exacta queda desconocida; el intervalo contribuye a riesgos y confianza, no es medición local.',
         'muestras':result}
    output=Path(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(doc,ensure_ascii=False,indent=2),encoding='utf-8')
    return doc


def read_inegi(path=DEPTH_MAP):
    doc=json.loads(Path(path).read_text(encoding='utf-8'))
    if doc.get('tipo') != 'intervalos_inferidos_del_calificador_WRB_NO_mediciones':
        raise ValueError('Archivo de profundidad INEGI con formato desconocido.')
    return {r['id']: r for r in doc.get('muestras',[])}
