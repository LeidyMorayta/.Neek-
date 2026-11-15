"""NASA POWER queried at each field's interior point, with dated local cache."""
from datetime import date, timedelta
from pathlib import Path
import hashlib
from functools import lru_cache
from threading import Lock

from .power import fetch_power, read_csv, save_csv

CACHE = Path('data/cache_climate')


@lru_cache(maxsize=128)
def _cache_lock(key):
    return Lock()


def point_climate(point, reference_file, fetcher=fetch_power, cache_dir=CACHE):
    reference = read_csv(reference_file)
    first = reference[0]['date']
    # POWER solar has longer latency: do not request today's incomplete observations.
    last = min(reference[-1]['date'], date.today()-timedelta(days=8))
    if first > last:
        raise ValueError('No hay periodo histórico disponible para esta ubicación.')
    lat, lon = round(point.y, 5), round(point.x, 5)
    identity = f'{lat},{lon},{first},{last}'
    key = hashlib.sha256(identity.encode()).hexdigest()[:20]
    path = Path(cache_dir)/f'POWER-{key}.csv'
    metadata = {'fuente':'NASA POWER consultado en el punto interior de esta parcela',
                'latitud':lat, 'longitud':lon, 'inicio':str(first), 'fin':str(last),
                'resolucion':'Meteorología ~0.5° × 0.625°; radiación ~1°. Parcelas cercanas pueden compartir celda.',
                'cache_id':key, 'es_promedio_estatal':False}
    with _cache_lock(key):
        if path.is_file():
            return read_csv(path), metadata
        downloaded = fetcher(lat, lon, start_date=first, end_date=last)
        # Validate before atomic replacement. Failed requests never become a regional fallback.
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix('.tmp.csv')
        save_csv(downloaded, temporary)
        try:
            rows = read_csv(temporary)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
        return rows, metadata


def recent_rain(rows, days=30):
    last = rows[-1]['date']
    by_date = {r['date']:r for r in rows}
    dates = [last-timedelta(days=i) for i in range(days-1,-1,-1)]
    amounts = [by_date.get(d,{}).get('PRECTOTCORR') for d in dates]
    valid = [x for x in amounts if x is not None]
    streak = longest = 0
    for value in amounts:
        streak = streak+1 if value is not None and value < 1 else 0
        longest = max(longest, streak)
    return {'inicio':str(dates[0]), 'fin':str(last), 'dias_esperados':days,
            'dias_validos':len(valid), 'completo':len(valid)==days,
            'lluvia_acumulada_mm':round(sum(valid),2) if len(valid)==days else None,
            'racha_seca_max_dias':longest if len(valid)==days else None}


def reference_et0(day, latitude, tmean, tmin, tmax):
    """Hargreaves–Samani reference ET0, mm/day; Ra converted MJ→equivalent mm.

    Not actual crop ET or an irrigation prescription. FAO-56 equations 21–25/52.
    """
    import math
    if any(v is None or not math.isfinite(v) for v in (tmean,tmin,tmax)) or tmax < tmin:
        return None
    j = day.timetuple().tm_yday
    phi = math.radians(latitude)
    dr = 1 + .033*math.cos(2*math.pi*j/365)
    delta = .409*math.sin(2*math.pi*j/365-1.39)
    ws = math.acos(max(-1,min(1,-math.tan(phi)*math.tan(delta))))
    ra = (24*60/math.pi)*.0820*dr*(ws*math.sin(phi)*math.sin(delta)+math.cos(phi)*math.cos(delta)*math.sin(ws))
    return max(0, .0023*.408*ra*(tmean+17.8)*math.sqrt(tmax-tmin))


def recent_et0(rows, latitude, days=30):
    last = rows[-1]['date']
    by_date = {r['date']:r for r in rows}
    dates = [last-timedelta(days=i) for i in range(days-1,-1,-1)]
    values = []
    for day in dates:
        r = by_date.get(day, {})
        value = reference_et0(day,latitude,r.get('T2M'),r.get('T2M_MIN'),r.get('T2M_MAX'))
        if value is not None:
            values.append(value)
    return {'inicio':str(dates[0]), 'fin':str(last), 'dias_validos':len(values), 'dias_esperados':days,
            'et0_media_mm_dia':round(sum(values)/days,2) if len(values)==days else None,
            'et0_total_mm':round(sum(values),2) if len(values)==days else None,
            'metodo':'Hargreaves–Samani (ET0 de referencia, sin calibración local)'}
