"""Muestreo estatal limitado y agregación diaria; no equivale a malla por parcela."""
from datetime import date
from pathlib import Path
import json
from statistics import mean
from shapely.geometry import Point
from .power import fetch_power, save_csv, PARAMS

# Candidatos distribuidos en zonas interior sur, oeste, centro, este, norte.
# Se usan 7 muestras como máximo, sin afirmar que cubran la heterogeneidad local.
FRACTIONS = [(0.32,0.20), (0.52,0.20), (0.12,0.45), (0.32,0.45),
             (0.52,0.45), (0.72,0.45), (0.32,0.70), (0.52,0.70),
             (0.72,0.70), (0.90,0.70)]


def sample_points(geom, max_points=7):
    a,b,c,d = geom.bounds
    out=[]
    grid=set()
    for fx,fy in FRACTIONS:
        lon = a + (c-a)*fx; lat = b+(d-b)*fy
        if not geom.contains(Point(lon,lat)):
            continue
        key = (round(lon*2)/2, round(lat*2)/2)
        if key in grid:
            continue
        grid.add(key)
        out.append({'latitud':round(lat,6),'longitud':round(lon,6)})
        if len(out)>=max_points:
            break
    if len(out)<3:
        raise ValueError('No se pudieron distribuir al menos 3 muestras sobre el estado.')
    return out


def daily_aggregate(sequences, min_points=3):
    byday={}
    for sample in sequences:
        for r in sample:
            byday.setdefault(r['date'],[]).append(r)
    rows=[]
    for day, records in sorted(byday.items()):
        if len(records)<min_points:
            continue
        row={'date':day}
        for p in PARAMS:
            nums=[float(rec[p]) for rec in records if rec.get(p) is not None]
            row[p] = round(mean(nums),4) if len(nums)>=min_points else None
        rows.append(row)
    return rows


def fetch_region(geom, out, start=2023, end=2025, fetcher=fetch_power, start_date=None, end_date=None):
    samples=sample_points(geom)
    records=[]
    errors=[]
    for idx, pt in enumerate(samples, 1):
        try:
            if start_date is None and end_date is None:
                rows=fetcher(pt['latitud'],pt['longitud'],start,end)
            else:
                rows=fetcher(pt['latitud'],pt['longitud'],start,end,start_date=start_date,end_date=end_date)
            records.append(rows)
        except (ValueError, RuntimeError, OSError) as e:
            errors.append({'punto':idx,'error':type(e).__name__})
    if len(records)<3:
        raise RuntimeError('NASA POWER: menos de 3 muestras disponibles; no se guardará un promedio regional incompleto.')
    agg=daily_aggregate(records)
    expected_first = start_date or date(start,1,1)
    expected_last = end_date or date(end,12,31)
    expected_days = (expected_last - expected_first).days + 1
    if len(agg) < max(1, int(expected_days * .85)):
        raise RuntimeError('NASA POWER: falta más del 15% de días del rango; no se guardará un CSV incompleto.')
    save_csv(agg,out)
    meta={'proveedor':'NASA POWER','cobertura':'Yucatán (muestras interiores del GeoJSON)',
          'periodo':[expected_first.isoformat(),expected_last.isoformat()],'metodo':'Promedio de variables diarias entre puntos de muestreo; lluvia diaria promedio espacial (no total de toda el área)',
          'numero_muestras':len(records),'puntos_consultados':samples,
          'fallos':errors, 'limites_estado':[round(x,6) for x in geom.bounds],
          'advertencia':'Resolución meteorológica regional; no representa diferencias de cada parcela ni celdas exactas del estado.'}
    Path(str(out)+'.meta.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf8')
    return meta


def sample_ndvi_geometry(geom, radius_deg=0.012):
    """Ventana pequeña de ~2.5 km, siempre dentro de estado; evita raster estatal gigantesco."""
    from shapely.geometry import box
    p=geom.representative_point()
    return geom.intersection(box(p.x-radius_deg,p.y-radius_deg,p.x+radius_deg,p.y+radius_deg))
