"""Gestión incremental y segura del historial 2020-2026.

No sustituye valores observados por datos inventados. Las descargas originales
2023-2025 quedan intactas para poder revertir cambios.
"""
from datetime import date, timedelta
from pathlib import Path

BEGIN = 2020
LAST_FULL_YEAR = 2025
LATEST_YEAR = 2026


def latest_power_day(today=None):
    """Fecha conservadora: retraso de hasta 7 días (solar), margen 10 días."""
    today = today or date.today()
    return min(date(LATEST_YEAR, 12, 31), today - timedelta(days=10))


def latest_meteo_day(today=None):
    """Solo observaciones históricas: no consultar el día en curso."""
    today = today or date.today()
    return min(date(LATEST_YEAR, 12, 31), today - timedelta(days=2))


def merge_rows(existing, incoming):
    """Combina por fecha y conserva valores no nulos de registros previos."""
    merged = {}
    for r in list(existing) + list(incoming):
        d = r['date']
        if isinstance(d, str):
            d = date.fromisoformat(d)
        old = merged.setdefault(d, {'date': d})
        for k, v in r.items():
            if k != 'date' and (v is not None or k not in old):
                old[k] = v
    return [merged[d] for d in sorted(merged) if BEGIN <= d.year <= LATEST_YEAR]


def full_year_missing(rows, year):
    """Detecta año con fechas faltantes (no vuelve a descargar un año completo)."""
    dates = {r['date'] if isinstance(r['date'],date) else date.fromisoformat(r['date']) for r in rows}
    d = date(year, 1, 1)
    stop = date(year,12,31)
    while d <= stop:
        if d not in dates:
            return True
        d += timedelta(days=1)
    return False


def first_unfetched_day(rows, year, last):
    dates = {r['date'] if isinstance(r['date'],date) else date.fromisoformat(r['date'])
             for r in rows if str(r['date'])[:4] == str(year)}
    day = date(year,1,1)
    while day <= last:
        if day not in dates:
            return day
        day += timedelta(days=1)
    return None


def observed_range(rows):
    valid = sorted(r['date'] if isinstance(r['date'],date) else date.fromisoformat(r['date']) for r in rows)
    return {'primera_fecha':valid[0].isoformat() if valid else None,
            'ultima_fecha':valid[-1].isoformat() if valid else None,
            'dias':len(set(valid)), 'anios_presentes':sorted({d.year for d in valid})}


def atomic_csv(rows, path, writer):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.nuevo')
    try:
        writer(rows, temporary)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
