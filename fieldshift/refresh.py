"""Actualización histórica incremental: NASA POWER, Meteomatics y NDVI.

Las fuentes históricas existentes de V9 no se sobrescriben. Si falla una
consulta, no se rellenan fechas ni se declara que el periodo está completo.
"""
from datetime import date, timedelta
from pathlib import Path
from statistics import median
from tempfile import TemporaryDirectory
import os

from .history import (BEGIN, LAST_FULL_YEAR, LATEST_YEAR, latest_power_day,
                      latest_meteo_day, merge_rows, full_year_missing,
                      first_unfetched_day, observed_range, atomic_csv)
from .power import read_csv, save_csv
from .meteomatics import fetch_meteomatics, read_meteomatics_csv, write_meteomatics_csv
from .regional import fetch_region, sample_ndvi_geometry
from .report import write_json

DATA = Path('data')
POWER = DATA / 'power_yucatan_2020_2026.csv'
POWER_OLD = DATA / 'power_yucatan_2023_2025.csv'
METEO = DATA / 'meteomatics_yucatan_2020_2026.csv'
METEO_OLD = DATA / 'meteomatics_yucatan_2023_2025.csv'
NDVI = DATA / 'ndvi_muestra_yucatan_2020_2026.json'
NDVI_OLD = DATA / 'ndvi_muestra_yucatan_2023_2025.json'


def preferred(new, old):
    """Para un análisis sin nuevos datos, mantener compatibilidad con V9."""
    return new if new.exists() else old


def _historical_rows(new, old, reader):
    if new.exists():
        return reader(new)
    if old.exists():
        return reader(old)
    return []


def _missing_full_years(rows):
    return [year for year in range(BEGIN,LAST_FULL_YEAR+1)
            if full_year_missing(rows, year)]


def _year_groups(years):
    """Agrupa años consecutivos para reducir solicitudes a NASA POWER."""
    out=[]
    for year in years:
        if out and year == out[-1][1] + 1:
            out[-1] = (out[-1][0], year)
        else:
            out.append((year,year))
    return out


def refresh_power(geom, today=None, regional_fetcher=fetch_region):
    rows = _historical_rows(POWER, POWER_OLD, read_csv)
    parts = []
    errors = []
    latest = latest_power_day(today)
    ranges = [(a,b,None,None) for a,b in _year_groups(_missing_full_years(rows))]
    if latest >= date(LATEST_YEAR,1,1):
        start_2026 = first_unfetched_day(rows,LATEST_YEAR,latest)
        if start_2026 is not None:
            ranges.append((LATEST_YEAR,LATEST_YEAR,start_2026,latest))
    for a,b,first,last in ranges:
        try:
            with TemporaryDirectory(prefix='fieldshift_nasa_') as dirname:
                temp = Path(dirname) / 'region.csv'
                kwargs = {'start_date':first,'end_date':last} if first is not None else {}
                metadata = regional_fetcher(geom,temp,start=a,end=b,**kwargs)
                got = read_csv(temp)
                if first is not None:
                    got = [r for r in got if first <= r['date'] <= last]
                rows = merge_rows(rows,got)
                parts.append({'inicio':str(first or date(a,1,1)),
                              'fin':str(last or date(b,12,31)),
                              'dias_descargados':len(got),
                              'muestras':metadata.get('numero_muestras')})
        except (RuntimeError, ValueError, OSError, KeyError) as exc:
            errors.append({'inicio':str(first or date(a,1,1)),
                           'fin':str(last or date(b,12,31)),
                           'motivo':str(exc)[:180]})
    if rows:
        atomic_csv(rows,POWER,save_csv)
    return {'estado': 'parcial' if errors else ('actualizado' if parts else 'ya_disponible'),
            'archivo':str(POWER) if rows else None,
            'rangos_nuevos':parts,'errores':errors,'cobertura':observed_range(rows),
            'corte_consulta_2026':latest.isoformat() if latest.year==2026 else None}


def refresh_meteo(geom, today=None, meteomatics_fetcher=fetch_meteomatics):
    rows = _historical_rows(METEO,METEO_OLD,read_meteomatics_csv)
    parts=[]
    errors=[]
    if not (os.getenv('METEOMATICS_USERNAME') and os.getenv('METEOMATICS_PASSWORD')):
        return {'estado':'sin_credenciales','archivo':str(preferred(METEO,METEO_OLD))
                if preferred(METEO,METEO_OLD).exists() else None,
                'instruccion':'Configura METEOMATICS_USERNAME y METEOMATICS_PASSWORD en fish.'}
    p=geom.representative_point()
    latest=latest_meteo_day(today)
    for year in _missing_full_years(rows):
        try:
            got=meteomatics_fetcher(p.y,p.x,year,year)
            rows=merge_rows(rows,got)
            parts.append({'anio':year,'dias_descargados':len(got)})
        except (RuntimeError, ValueError, OSError, KeyError) as exc:
            errors.append({'anio':year,'motivo':str(exc)[:150]})
    if latest >= date(LATEST_YEAR,1,1):
        first=first_unfetched_day(rows,LATEST_YEAR,latest)
        if first is not None:
            try:
                got=meteomatics_fetcher(p.y,p.x,LATEST_YEAR,LATEST_YEAR,
                                        first_day=first,last_day=latest)
                rows=merge_rows(rows,got)
                parts.append({'inicio':str(first),'fin':str(latest),'dias_descargados':len(got)})
            except (RuntimeError, ValueError, OSError, KeyError) as exc:
                errors.append({'inicio':str(first),'fin':str(latest),'motivo':str(exc)[:150]})
    if rows:
        atomic_csv(rows,METEO,write_meteomatics_csv)
        # El punto de referencia es el mismo de V9.
        write_json({'tipo':'muestra_puntual_representativa','latitud':p.y,'longitud':p.x,
                    'aviso':'No es media estatal; Meteomatics NO modifica el semáforo.'},
                   str(METEO)+'.meta.json')
    return {'estado':'parcial' if errors else ('actualizado' if parts else 'ya_disponible'),
            'archivo':str(METEO) if rows else None,'rangos_nuevos':parts,
            'errores':errors,'cobertura':observed_range(rows)}


def refresh_ndvi(geom, today=None, ndvi_fetcher=None):
    """Una escena por año para una pequeña muestra, sin convertirla en aptitud."""
    from .planetary import retrieve_ndvi
    fetcher=ndvi_fetcher or retrieve_ndvi
    source = preferred(NDVI, NDVI_OLD)
    old={}
    if source.exists():
        import json
        old=json.loads(source.read_text(encoding='utf-8'))
    scenes=list(old.get('escenas',[]))
    errors=list(old.get('errores_lectura',[]))
    covered=set(old.get('anios_consultados',[]))
    if not covered and old.get('intervalo')=='2023-2025':
        covered.update((2023,2024,2025))
    new=[]
    issues=[]
    patch=sample_ndvi_geometry(geom)
    cutoff=latest_power_day(today)
    for a,b in _year_groups([y for y in range(BEGIN,LATEST_YEAR+1)
                              if y not in covered and (y < LATEST_YEAR or cutoff >= date(y,6,1))]):
        try:
            result=fetcher(patch,a,b,6,3,35.0,1,end_date=cutoff)
            scenes.extend(result.get('escenas',[]))
            errors.extend(result.get('errores_lectura',[]))
            covered.update(range(a,b+1))
            new.append([a,b])
        except (ValueError, RuntimeError, OSError, ImportError, KeyError) as exc:
            issues.append({'inicio':a,'fin':b,'motivo':type(exc).__name__})
    means=[s['ndvi_medio'] for s in scenes if s.get('ndvi_medio') is not None]
    if covered:
        write_json({'fuente':'Microsoft Planetary Computer / Sentinel-2 L2A',
           'intervalo':f'{BEGIN}-{LATEST_YEAR}', 'anios_consultados':sorted(covered),
           'mes_inicio':6,'meses_ventana':3,'region_geojson':'geojson/yucatan_estado.geojson',
           'alcance':'Una ventana interior pequeña: NO representa Yucatán entero.',
           'escenas':scenes,'errores_lectura':errors,
           'ndvi_mediana_de_escenas_validas':round(median(means),4) if means else None,
           'estado':'evidencia_disponible' if means else 'datos_insuficientes',
           'advertencia':'NDVI no interviene en el semáforo ni garantiza aptitud agrícola.'},NDVI)
    return {'estado':'parcial' if issues else ('actualizado' if new else 'ya_disponible'),
            'archivo':str(NDVI) if covered else None,'anios_consultados':sorted(covered),
            'rangos_nuevos':new,'errores':issues,'escenas':len(scenes)}
