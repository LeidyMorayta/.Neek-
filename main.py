"""FieldShift Yucatán V10: historial 2020-2025 + ciclos completos 2026.

  python main.py descargar          # clima y NDVI existente
  python main.py descargar-suelo    # 7 puntos SoilGrids desde GeoJSON estatal
  python main.py analizar --mes 6 --zona YUC-01
"""
import argparse
import json
import os
from pathlib import Path

from fieldshift.geo import read_state, point_info, STATE_FILE
from fieldshift.power import read_csv
from fieldshift.meteomatics import read_meteomatics_csv
from fieldshift.engine import analyze
from fieldshift.rotation import compare_rotations
from fieldshift.evidence import climate_comparison, meteomatics_risk_by_crop
from fieldshift.report import write_json
from fieldshift.soilgrids import download_soils, read_soil_samples, SOIL_FILE
from fieldshift.inegi_depth import import_inegi, read_inegi, DEPTH_MAP
from fieldshift.refresh import (POWER as POWER_NEW, POWER_OLD, METEO as METEO_NEW,
                                METEO_OLD, NDVI as NDVI_NEW, NDVI_OLD,
                                refresh_power, refresh_meteo, refresh_ndvi, preferred)
from fieldshift.history import observed_range

DATA = Path('data')
POWER = preferred(POWER_NEW, POWER_OLD)
METEO = preferred(METEO_NEW, METEO_OLD)
NDVI = preferred(NDVI_NEW, NDVI_OLD)
SOIL = Path('config/suelo.json')  # legado V6, NO se usa en V7
DEPTH_OBSERVATIONS = Path('config/profundidad_campo.json')
HISTORY = Path('config/historial.json')
CATALOG = Path('config/cultivos_demo.json')


def _read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def _status(obj):
    print(json.dumps(obj,ensure_ascii=False,indent=2))


def descargar():
    """Conserva los archivos V9 y descarga solo periodos ausentes 2020-2026."""
    geom = read_state()
    DATA.mkdir(parents=True,exist_ok=True)
    status={'geojson':str(STATE_FILE),
            'periodo_objetivo':'2020-2025 completos + ciclos terminados de 2026',
            'fuentes':{}}
    status['fuentes']['nasa_power']=refresh_power(geom)
    status['fuentes']['meteomatics']=refresh_meteo(geom)
    status['fuentes']['planetary_computer']=refresh_ndvi(geom)
    status['advertencia']='Se conservan las descargas 2023-2025; los fallos aparecen por fuente y NO se rellenan con datos inventados.'
    write_json(status,DATA/'estado_descargas_2020_2026.json')
    _status(status)


def descargar_suelo():
    geom = read_state()
    data = download_soils(geom)
    _status({
        'estado':'muestras_descargadas',
        'fuente':'ISRIC SoilGrids WCS (estimaciones, no mediciones de campo)',
        'archivo':str(SOIL_FILE),
        'geojson_puntos':'results/puntos_suelo_yucatan.geojson',
        'muestras_validas':len(data['muestras']),
        'fallos':data['fallos'],
        'advertencia':'La profundidad no medida reduce la confianza; un verde es aptitud preliminar, no garantía de siembra.'
    })


def analizar(mes, zona='YUC-01', guardar_resultado=True, mostrar_resumen=True):
    if not 1<=mes<=12:
        raise ValueError('El mes debe estar entre 1 y 12.')
    geom=read_state()
    if not POWER.exists():
        raise ValueError('Primero ejecuta: python main.py descargar')
    if not SOIL_FILE.exists():
        raise ValueError('Primero ejecuta: python main.py descargar-suelo; ya NO se usa config/suelo.json simulado.')
    clim=read_csv(POWER)
    cobertura=observed_range(clim)
    soil_data=read_soil_samples()
    samples=[dict(p) for p in soil_data['muestras']]
    inegi_depth={}
    if DEPTH_MAP.exists():
        inegi_depth=read_inegi()
        for pt in samples:
            entry=inegi_depth.get(pt['id'], {})
            match=entry.get('evidencia') if entry.get('estado')=='coincidencia_unica' else None
            if match is not None:
                pt['depth_interval_cm']=match.get('intervalo_cm')
                pt['depth_inegi_qualifier']=match.get('calificador')
                pt['depth_inegi_key']=match.get('clave_wrb')
                pt['depth_inegi_status']='Restricción cartográfica del suelo dominante; NO medida local.'
            else:
                pt['depth_inegi_status']=entry.get('estado','no_importado')

    if DEPTH_OBSERVATIONS.exists():
        observed=_read(DEPTH_OBSERVATIONS).get('mediciones', {})
        if not isinstance(observed,dict):
            raise ValueError('config/profundidad_campo.json: mediciones debe ser objeto.')
        for pt in samples:
            entry=observed.get(pt['id'])
            if entry is None:
                continue
            if not isinstance(entry,dict) or entry.get('fuente') != 'medicion_campo':
                raise ValueError('La profundidad de '+pt['id']+' requiere fuente=medicion_campo.')
            depth=entry.get('depth_cm')
            if isinstance(depth,bool) or not isinstance(depth,(int,float)) or not 1 <= depth <= 250:
                raise ValueError('Profundidad inválida en '+pt['id']+'; usa cm medidos (1-250).')
            pt['depth_cm']=float(depth)
            pt['depth_status']='Medida en campo y declarada por el usuario; validar protocolo.'
            pt['depth_source']='medicion_campo'
            pt['depth_interval_cm']=None  # la medición directa prevalece sobre la cartografía
    sample=next((p for p in samples if p['id']==zona),None)
    if sample is None:
        raise ValueError('Muestra no disponible. Elige: '+', '.join(p['id'] for p in samples))
    history=_read(HISTORY)
    catalog=_read(CATALOG)

    # Las 7 muestras están georreferenciadas; se evita fingir que hay un suelo
    # único estatal. El clima es un promedio REGIONAL compartido (NASA POWER).
    points=[]
    by_crop={c['name']:{} for c in catalog}
    for pt in samples:
        results=analyze(clim,pt,catalog,mes)
        summary={k:sum(x['estado']==k for x in results) for k in
                 ('verde','amarillo','rojo','datos_insuficientes')}
        confidence_counts={k:sum(x.get('confianza_datos')==k for x in results)
                           for k in ('alta','media','baja')}
        points.append({'id':pt['id'], 'latitud':pt['latitud'], 'longitud':pt['longitud'],
                       'suelo':{'ph':pt['ph'], 'texture':pt['texture'],
                                'depth_cm':pt['depth_cm'], 'depth_interval_cm':pt.get('depth_interval_cm'),
                                'depth_inegi_key':pt.get('depth_inegi_key'),
                                'depth_status':pt.get('depth_status') or pt.get('depth_inegi_status'),
                                'sand_pct':pt['sand_pct'],
                                'silt_pct':pt['silt_pct'],'clay_pct':pt['clay_pct']},
                       'conteo':summary, 'conteo_confianza':confidence_counts, 'cultivos':results})
        for r in results:
            by_crop[r['cultivo']][pt['id']]=r['estado']
    chosen=next(p for p in points if p['id']==zona)
    crops=chosen['cultivos']
    rotations=compare_rotations(clim,sample,catalog,mes,history)
    distribution={name:{
        'estados_por_punto':cases,
        'conteo':{state:sum(s==state for s in cases.values()) for state in
                  ('verde','amarillo','rojo','datos_insuficientes')},
        'estado_regional':next(iter(set(cases.values()))) if len(set(cases.values()))==1 else 'heterogeneo'
    } for name,cases in by_crop.items()}
    extra={}
    if METEO.exists():
        secondary=read_meteomatics_csv(METEO)
        extra['meteomatics']={'alcance':'solo punto regional, no media estatal',
                              'contraste':climate_comparison(clim,secondary)}
        alerts=meteomatics_risk_by_crop(secondary,catalog,mes)
        for pt in points:
            for crop in pt['cultivos']:
                crop['evidencia_meteomatics']=alerts.get(crop['cultivo'])
    if NDVI.exists():
        obs=_read(NDVI)
        extra['planetary_computer']={'alcance':obs.get('alcance'),
            'estado':obs.get('estado'),
            'ndvi_mediana_de_escenas_validas':obs.get('ndvi_mediana_de_escenas_validas'),
            'escenas':obs.get('escenas',[])}
    output={'proyecto':'FieldShift Yucatán', 'version':'10.0',
      'periodo_clima':f"{cobertura['primera_fecha']} a {cobertura['ultima_fecha']}",
      'cobertura_climatica':cobertura,
      'criterio_2026':'Solo ciclos terminados con al menos 90% de días climáticos válidos; se excluyen temporadas aún abiertas.',
      'anios_por_cultivo_en_punto':{c['cultivo']:c.get('anios_utilizados',[]) for c in crops},
      'geojson':str(STATE_FILE),'region':'Estado de Yucatán, México',
      'enfoque':'Muestreo estatal exploratorio por puntos, NO zonificación de parcelas',
      'mes_inicio':mes,'region_info':point_info(geom),
      'fuente_principal':'NASA POWER: promedio regional diario de siete muestras',
      'suelo_fuente':soil_data['source'],
      'suelo_fuente_url':soil_data['provider_url'],
      'suelo_muestreo_geojson':'results/puntos_suelo_yucatan.geojson',
      'fuente_profundidad_inegi':str(DEPTH_MAP) if DEPTH_MAP.exists() else None,
      'punto_seleccionado':zona,
      'suelo_del_punto_seleccionado':chosen['suelo'],
      'catalogo':'temperatura/pH de FAO ECOCROP; lluvia ciclo y penalizaciones aun heuristicas',
      'cultivos':crops, 'rotaciones':rotations,
      'conteo_confianza_punto_seleccionado':chosen['conteo_confianza'],
      'puntos_muestreo':points,
      'distribucion_muestral_por_cultivo':distribution,
      'fuentes_complementarias':extra,
      'avisos':[
        'Los siete puntos no son siete polígonos ni representan todas las parcelas.',
        'SoilGrids pH y textura son estimaciones estáticas a unos 250 m, no medidas en campo.',
        'INEGI identifica intervalos del suelo dominante, NO profundidad exacta. Un verde indica aptitud preliminar; consultar confianza y riesgos.',
        'La confianza alta/media/baja es una clasificación cualitativa de procedencia y completitud, NO probabilidad de éxito.',
        'Clima NASA POWER es promedio regional, NO clima local de cada punto.',
        'Las rotaciones listadas solo aplican a la muestra elegida, y el historial es DEMOSTRATIVO.',
        '2026 puede estar incompleto; cada cultivo informa anios_utilizados y anios_descartados.',
        'Ninguno de los colores representa pronóstico ni garantía de rendimiento.']}
    out=Path('results')/f'recomendaciones_yucatan_mes_{mes:02d}.json'
    if guardar_resultado:
        write_json(output,out)
    counts={s:sum(1 for x in crops if x['estado']==s) for s in
            ('verde','amarillo','rojo','datos_insuficientes')}
    if mostrar_resumen:
        _status({'archivo':str(out),'punto_seleccionado':zona,
                 'cobertura_climatica':cobertura,
                 'muestras_con_suelo':len(samples),'conteo_en_punto_seleccionado':counts,
                 'conteo_confianza_punto_seleccionado':chosen['conteo_confianza'],
                 'rotaciones_en_punto_seleccionado':[
                    {'tipo':x['tipo'],'cultivos':x['cultivos'],'estado':x['estado'],
                     'confianza_datos':x['confianza_datos']}
                    for x in rotations['estrategias']],
                 'advertencia':'La profundidad medida sigue pendiente; consulta aptitud, confianza y riesgos por separado.',
                 'edafologia_inegi':'integrada' if DEPTH_MAP.exists() else 'pendiente_importacion',
                 'complementos':list(extra)})
    return output


def main():
    p=argparse.ArgumentParser(description='FieldShift Yucatán V10: historial ampliado y suelos por punto')
    sub=p.add_subparsers(dest='accion',required=True)
    sub.add_parser('descargar',help='Ampliar a 2020-2026 de forma incremental, sin borrar datos anteriores')
    sub.add_parser('descargar-suelo',help='Obtener pH y textura estimados desde SoilGrids en 7 puntos de Yucatán')
    imp=sub.add_parser('importar-edafologia',help='Cruzar suelos INEGI Serie II con los puntos YUC-01 a YUC-07')
    imp.add_argument('--archivo',required=True,help='ZIP, SHP, GPKG, GeoJSON o carpeta de INEGI')
    imp.add_argument('--campo',default=None,help='Nombre del atributo Clave_WRB, si es distinto')
    imp.add_argument('--crs-faltante',default=None,help='CRS explícito si el SHP no incluye .prj; para INEGI nacional Serie II: EPSG:6362')
    ana=sub.add_parser('analizar', help='Semáforo, riesgos y comparación de tres rotaciones')
    ana.add_argument('--mes',type=int,default=6,help='Mes de siembra (1-12; predeterminado 6)')
    ana.add_argument('--punto','--zona',dest='zona',default='YUC-01',help='ID del punto SoilGrids: YUC-01 a YUC-07')
    args=p.parse_args()
    try:
        if args.accion=='descargar': descargar()
        elif args.accion=='descargar-suelo': descargar_suelo()
        elif args.accion=='importar-edafologia':
            doc=import_inegi(args.archivo,campo=args.campo,crs_faltante=args.crs_faltante)
            _status({'archivo':str(DEPTH_MAP), 'coincidencias':sum(x['estado']=='coincidencia_unica' for x in doc['muestras']),
                     'muestras':doc['muestras'],'advertencia':doc['advertencia']})
        else: analizar(args.mes,args.zona)
    except (ValueError,RuntimeError,OSError,KeyError,ImportError) as exc:
        p.exit(2,f'Error: {exc}\n')

if __name__=='__main__':
    main()
