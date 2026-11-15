"""Resumen de ciclos históricos y eventos diarios; sin predicciones.

El conteo de rachas usa días consecutivos con lluvia <1 mm. Los días
sin medición interrumpen la racha; no se imputan como secos.
"""
from datetime import date, timedelta
from statistics import mean, median
import math


def _pct(values, percentile):
    seq = sorted(v for v in values if v is not None)
    if not seq:
        return None
    i = (len(seq) - 1) * percentile / 100
    low, high = math.floor(i), math.ceil(i)
    return seq[low] + (seq[high] - seq[low]) * (i-low)


def _mean(values):
    nums = [v for v in values if v is not None]
    return round(mean(nums), 3) if nums else None


def _dry_run_stats(dates, by_date, limit_mm=1.0, min_run=7):
    longest = 0
    current = 0
    long_runs = 0
    for d in dates:
        r = by_date.get(d)
        rain = r.get('PRECTOTCORR') if r else None
        if rain is not None and rain < limit_mm:
            current += 1
            longest = max(longest, current)
        else:
            if current >= min_run:
                long_runs += 1
            current = 0
    if current >= min_run:
        long_runs += 1
    return longest, long_runs


def summary_by_crop(rows, month, cycle_days, years=None,
                    min_coverage=0.90, heat_screen_c=35.0):
    if not 1 <= month <= 12:
        raise ValueError('El mes de siembra debe estar entre 1 y 12.')
    if cycle_days < 1:
        raise ValueError('La duración del cultivo debe ser positiva.')
    by_date = {r['date']: r for r in rows}
    if years is None:
        years = sorted({d.year for d in by_date})
    # No admitir temporadas cuyo último día todavía no existe en el historial:
    # evita que 2026 parcial parezca un ciclo terminado por tener >=90% de días.
    vital = ('T2M', 'T2M_MIN', 'T2M_MAX', 'PRECTOTCORR')
    observed = [d for d, r in by_date.items() if all(r.get(k) is not None for k in vital)]
    last_observed = max(observed) if observed else None
    annual = []
    excluded = []
    for year in years:
        start = date(year, month, 1)
        dates = [start + timedelta(days=i) for i in range(cycle_days)]
        if last_observed is None or dates[-1] > last_observed:
            excluded.append(year)
            continue
        all_rows = [by_date[d] for d in dates if d in by_date]
        complete = [r for r in all_rows if all(r.get(key) is not None for key in
                    ('T2M', 'T2M_MIN', 'T2M_MAX', 'PRECTOTCORR'))]
        if len(complete) / len(dates) < min_coverage:
            excluded.append(year)
            continue
        def vals(k):
            return [r.get(k) for r in complete if r.get(k) is not None]
        rain = vals('PRECTOTCORR')
        max_t = vals('T2M_MAX')
        min_t = vals('T2M_MIN')
        longest, n_long = _dry_run_stats(dates, by_date)
        annual.append({
            'year': year, 'days': len(dates), 'observed_days': len(complete),
            'coverage': round(len(complete)/len(dates), 3),
            'temp_mean_c': _mean(vals('T2M')),
            'temp_max_p95_c': round(_pct(max_t, 95), 2),
            'temp_min_p05_c': round(_pct(min_t, 5), 2),
            'rain_total_mm': round(sum(rain), 2),
            'rain_max_day_mm': round(max(rain), 2),
            'heavy_rain_days_30mm': sum(v >= 30 for v in rain),
            'heat_days_35c': sum(v >= 35 for v in max_t),
            'heat_days_screen': sum(v > heat_screen_c for v in max_t),
            'heat_screen_c': float(heat_screen_c),
            'dry_days_1mm': sum(v < 1 for v in rain),
            'dry_streak_max_days': longest,
            'dry_spells_7plus': n_long,
            'rh_mean_pct': _mean(vals('RH2M')),
            'solar_mean_mj_m2_day': _mean(vals('ALLSKY_SFC_SW_DWN')),
        })
    if not annual:
        return {'years_used': [], 'years_excluded': excluded, 'periods': [],
                'sufficient': False}
    metric_names = [k for k in annual[0] if k not in ('year', 'days', 'coverage')]
    metrics = {k: _mean([p[k] for p in annual]) for k in metric_names}
    metrics['rain_total_mm'] = round(median(p['rain_total_mm'] for p in annual), 2)
    metrics['dry_streak_max_days'] = max(p['dry_streak_max_days'] for p in annual)
    metrics['heat_screen_c'] = float(heat_screen_c)
    return {'years_used': [p['year'] for p in annual], 'years_excluded': excluded,
            'periods': annual, 'sufficient': len(annual) >= 2, 'metrics': metrics}
