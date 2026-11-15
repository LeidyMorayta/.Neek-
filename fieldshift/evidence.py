"""Resumen de Meteomatics sin cambiar el semáforo NASA ni contar datos dos veces."""
from .climate import summary_by_crop


def climate_comparison(nasa_rows, meteo_rows):
    nasa = {r['date']: r for r in nasa_rows}
    meteo = {r['date']: r for r in meteo_rows}
    overlap = sorted(set(nasa) & set(meteo))
    eligible = [d for d in overlap if all(nasa[d].get(k) is not None and meteo[d].get(k) is not None
                   for k in ('T2M', 'PRECTOTCORR'))]
    if not eligible:
        return {'dias_coincidentes': 0, 'estado': 'datos_insuficientes'}
    def avg_delta(key):
        pairs = [(nasa[d][key], meteo[d][key]) for d in eligible
                 if nasa[d].get(key) is not None and meteo[d].get(key) is not None]
        return round(sum(m-n for n,m in pairs)/len(pairs), 3) if pairs else None
    return {'dias_coincidentes': len(eligible), 'dias_nasa': len(nasa), 'dias_meteomatics': len(meteo),
        'delta_temperatura_meteo_menos_nasa_c': avg_delta('T2M'),
        'delta_precipitacion_diaria_meteo_menos_nasa_mm': avg_delta('PRECTOTCORR'),
        'estado': 'contraste_disponible',
        'nota': 'Las diferencias no prueban cuál fuente es más exacta; se comparan series agregadas espacialmente y con distinta metodología.'}


def meteomatics_risk_by_crop(meteo_rows, crops, month):
    output = {}
    for crop in crops:
        metrics = summary_by_crop(meteo_rows, month, crop['cycle_days'])
        if not metrics['sufficient']:
            output[crop['name']] = {'estado': 'datos_insuficientes',
                'motivo': 'Menos de dos periodos históricos Meteomatics con >=90% de cobertura.'}
            continue
        m = metrics['metrics']
        warnings = []
        if m['heat_days_35c'] >= 10:
            warnings.append('Meteomatics: se registran días con máximas >=35 C; revisar estrés térmico.')
        if m['heavy_rain_days_30mm'] >= 3:
            warnings.append('Meteomatics: lluvias fuertes históricas; revisar drenaje y erosión.')
        if m['rain_total_mm'] < crop['rainfall_mm'][0]:
            warnings.append('Meteomatics: lluvia del ciclo por debajo de la referencia provisional; evaluar riego.')
        output[crop['name']] = {'estado': 'contraste_disponible',
            'anios_utilizados': metrics['years_used'],
            'lluvia_total_mediana_mm': m['rain_total_mm'],
            'temperatura_media_c': m['temp_mean_c'],
            'dias_calor_35c_promedio': m['heat_days_35c'],
            'dias_lluvia_30mm_promedio': m['heavy_rain_days_30mm'],
            'alertas': warnings,
            'nota': 'Alertas complementarias; no alteran por sí solas el puntaje NASA.'}
    return output
