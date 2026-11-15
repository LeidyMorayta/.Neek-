"""Motor exploratorio: datos ECOCROP trazables + penalizaciones explicables.

IMPORTANTE: La calibración por sequía/calor es HEURÍSTICA, NO una
validación agronómica o un pronóstico de producción.
"""
from .climate import summary_by_crop

# Peso total = 1.0. Se asigna parte de temperatura a calor y de lluvia a rachas secas.
WEIGHTS = {
    'temperature': 0.17, 'rainfall': 0.16,
    'ph': 0.13, 'texture': 0.09, 'depth': 0.09,
    'humidity': 0.05, 'solar': 0.05, 'heavy_rain': 0.06,
    'heat_exposure': 0.10, 'dry_streak': 0.10,
}
MISSING = 'datos_insuficientes'


def evaluate_data_confidence(soil, summary):
    """Calidad de la evidencia (alta/media/baja); independiente del semáforo.

    NO representa porcentaje de acierto, confianza estadística ni probabilidad
    de cosecha. Solo documenta procedencia, cobertura y datos pendientes.
    """
    reasons = []
    if not summary.get('sufficient'):
        return 'baja', ['No existen suficientes ciclos climáticos completos.']
    if soil.get('ph') is None or soil.get('texture') is None:
        return 'baja', ['Faltan propiedades necesarias del suelo.']
    origin = str(soil.get('source', '')).lower()
    if any(word in origin for word in ('simul', 'demo', 'invent')):
        return 'baja', ['Los valores del suelo son simulados; no representan una parcela real.']

    reasons.append('Clima histórico NASA POWER regional; no se midió en la parcela.')
    if 'soilgrids' in origin or 'isric' in origin:
        reasons.append('pH y textura estimados por SoilGrids; requieren comprobación local.')
    else:
        reasons.append('La procedencia de pH y textura no consta como análisis de laboratorio.')

    depth_value = soil.get('depth_cm')
    interval = soil.get('depth_interval_cm')
    valid_interval = (isinstance(interval, (list, tuple)) and len(interval) == 2
                      and all(isinstance(n, (int, float)) and not isinstance(n, bool) for n in interval)
                      and 0 <= interval[0] < interval[1] <= 250)
    if depth_value is None:
        if valid_interval:
            reasons.append('INEGI aporta un intervalo de restricción a escala 1:250 000, no una profundidad medida.')
            level = 'media'
        else:
            reasons.append('Profundidad efectiva desconocida; no hay intervalo cartográfico interpretable.')
            level = 'baja'
    elif soil.get('depth_source') == 'medicion_campo':
        reasons.append('Profundidad declarada como medición de campo; comprobar el protocolo utilizado.')
        level = 'media'
    else:
        reasons.append('La profundidad es numérica pero no se acredita una medición de campo.')
        level = 'baja'

    # Solo permitir ALTA si constan mediciones locales de TODAS las variables
    # fundamentales y clima local validado. Ninguno de los descargadores actuales
    # genera esas marcas, por lo que la confianza del prototipo no será ALTA.
    if (level == 'media' and soil.get('depth_source') == 'medicion_campo'
            and soil.get('ph_source') == 'laboratorio'
            and soil.get('texture_source') == 'laboratorio'
            and summary.get('clima_local_validado') is True):
        level = 'alta'
        reasons = ['pH, textura y profundidad con evidencia de campo/laboratorio; clima local validado.']
    return level, reasons


def interval_score(v, optimum, tolerance):
    """100 dentro del óptimo; 0 tras la tolerancia externa (método provisional)."""
    if v is None:
        return None
    low, high = optimum
    if low <= v <= high:
        return 100.0
    distance = low-v if v < low else v-high
    return round(max(0.0, 100.0 * (1 - distance / max(tolerance, 1e-6))), 2)


def ecocrop_score(v, optimum, absolute):
    """100 dentro del óptimo FAO; 0 fuera de límites absolutos FAO."""
    if v is None:
        return None
    a, b = optimum
    outer_low, outer_high = absolute
    if a <= v <= b:
        return 100.0
    if v < outer_low or v > outer_high:
        return 0.0
    if v < a:
        return round(100 * (v-outer_low)/max(1e-6, a-outer_low), 2)
    return round(100 * (outer_high-v)/max(1e-6, outer_high-b), 2)


def heat_screen_for_crop(crop):
    """Umbral orientativo en Tmax diaria, NO umbral letal validado.

    Regla explícita y reproducible basada en máximo óptimo FAO +3 °C,
    acotada a 30-38 °C; verificar con ensayos por variedad y etapa.
    """
    return float(max(30.0, min(38.0, crop['temperature_c'][1] + 3.0)))


def _get_abs(crop, key, default_delta):
    if key in crop:
        return crop[key]
    if key == 'temperature_absolute_c':
        return [crop['temperature_c'][0] - default_delta,
                crop['temperature_c'][1] + default_delta]
    return [crop['soil_ph'][0]-default_delta, crop['soil_ph'][1]+default_delta]


def evaluate(crop, soil, summary, weights=None, thresholds=(50, 80)):
    confianza, factores_confianza = evaluate_data_confidence(soil, summary)
    if not summary['sufficient']:
        return {'cultivo':crop['name'], 'estado':MISSING, 'confianza_datos':confianza,
                'factores_confianza':factores_confianza,
                'motivo':'Menos de dos ciclos históricos completos.'}
    # SoilGrids publica pH y textura, no profundidad efectiva hasta roca.
    # Nunca convertir la profundidad de la CAPA (0-5 cm) en profundidad útil.
    for key in ('ph', 'texture'):
        if soil.get(key) is None:
            return {'cultivo':crop['name'], 'estado':MISSING, 'confianza_datos':confianza,
                    'factores_confianza':factores_confianza,
                    'motivo':f'Falta dato de suelo: {key}.'}
    depth_unknown = soil.get('depth_cm') is None
    m = summary['metrics']
    temp = crop['temperature_c']; rain = crop['rainfall_mm']
    ph = crop['soil_ph']; depth = crop['min_depth_cm']
    abs_temp = _get_abs(crop, 'temperature_absolute_c', 7)
    abs_ph = _get_abs(crop, 'soil_ph_absolute', 1.5)
    observed = m.get('observed_days')
    screen = heat_screen_for_crop(crop)
    heat_days = m.get('heat_days_screen')
    if observed and heat_days is not None:
        # Índice exploratorio; limitado a pérdida máxima de 85 puntos.
        heat_penalty = min(85.0, 140.0 * heat_days / observed +
                           2.0 * max(0, (m.get('temp_max_p95_c') or screen)-screen))
        heat_score = round(100.0-heat_penalty, 2)
    else:
        heat_score = None
    streak = m.get('dry_streak_max_days')
    dry_score = None if streak is None else round(
        max(0.0, 100.0-min(80.0, max(0.0, streak-5.0)*10.0)), 2)
    scores = {
        'temperature': ecocrop_score(m.get('temp_mean_c'), temp, abs_temp),
        # Lluvia del CICLO: referencia DEMOSTRATIVA (no es la precipitación anual de FAO).
        'rainfall': interval_score(m.get('rain_total_mm'), rain,
                                   max(80, (rain[1]-rain[0])*.75)),
        'ph': ecocrop_score(float(soil['ph']), ph, abs_ph),
        'texture': 100.0 if str(soil['texture']).lower().strip() in crop['textures'] else 30.0,
        'depth': None if depth_unknown else interval_score(float(soil['depth_cm']), [depth, 250], max(15, depth*.7)),
        'humidity': interval_score(m.get('rh_mean_pct'), crop['humidity_pct'], 25),
        'solar': interval_score(m.get('solar_mean_mj_m2_day'), crop['solar_mj_m2_day'], 10),
        'heavy_rain': max(0, 100 - 12*(m.get('heavy_rain_days_30mm') or 0)),
        'heat_exposure': heat_score,
        'dry_streak': dry_score,
    }
    missing = [k for k,s in scores.items() if s is None]
    if any(k != 'depth' for k in missing):
        return {'cultivo':crop['name'], 'estado':MISSING, 'confianza_datos':confianza,
                'factores_confianza':factores_confianza,
                'motivo':'Faltan variables: '+', '.join(missing)}
    w = weights or WEIGHTS
    if (abs(sum(w.values())-1) > 0.000001 or set(w)!=set(scores)
            or any(v < 0 for v in w.values())):
        raise ValueError('Los pesos deben incluir las 10 variables, ser no negativos y sumar 1.')
    # Si falta profundidad, reponderar SOLO con evidencia disponible.
    # La calidad de los datos se informa APARTE; no cambia el semáforo.
    valid_weight = sum(w[k] for k in scores if scores[k] is not None)
    if valid_weight <= 0:
        return {'cultivo':crop['name'], 'estado':MISSING, 'confianza_datos':confianza,
                'factores_confianza':factores_confianza, 'motivo':'No hay componentes disponibles.'}
    total = round(sum(scores[k]*w[k] for k in scores if scores[k] is not None) / valid_weight, 1)
    # ECOCROP describe aptitud general; evidencia local puede mostrar producción
    # fuera de sus límites. No se altera el pH de FAO ni su componente (puede ser 0):
    # únicamente se evita el ROJO automático dentro del máximo OBSERVADO para
    # Capsicum chinense en Yucatán. No implica aptitud demostrada para otra parcela.
    ph_value = float(soil['ph'])
    ph_regional = crop.get('ph_evidencia_yucatan', {})
    ph_local_observado = (
        crop.get('ecocrop', {}).get('scientific_name') == 'Capsicum chinense'
        and ph_regional.get('tipo') == 'observacion_suelos_cultivados'
        and ph_regional.get('ph_max_observado') is not None
        and abs_ph[1] < ph_value <= float(ph_regional['ph_max_observado'])
    )
    advertencias_locales = []
    if ph_local_observado:
        advertencias_locales.append(
            'El pH está por encima del límite absoluto FAO ECOCROP, pero se han '
            'documentado suelos de Yucatán con chile habanero hasta pH 7.7. '
            'Esto NO confirma aptitud de la parcela: comprobar micronutrientes, '
            'drenaje y resultados de análisis local.'
        )
    critical = []
    if not depth_unknown and float(soil['depth_cm']) < depth*.4:
        critical.append('Profundidad del suelo extremadamente limitada para el cultivo (umbral provisional).')
    if not abs_ph[0] <= ph_value <= abs_ph[1] and not ph_local_observado:
        critical.append('pH fuera de los límites absolutos consignados en la ficha FAO ECOCROP.')
    if not abs_temp[0] <= m['temp_mean_c'] <= abs_temp[1]:
        critical.append('Temperatura media fuera de los límites absolutos consignados por FAO ECOCROP.')
    if m['rain_total_mm'] < rain[0]*0.4:
        critical.append('Precipitación del ciclo muy inferior al rango PROVISIONAL del catálogo.')
    estado = 'verde' if total >= thresholds[1] else 'amarillo' if total >= thresholds[0] else 'rojo'
    if critical:
        estado = 'rojo'
    elif ph_local_observado and estado == 'verde':
        # La excepción local al pH FAO sigue siendo advertencia agronómica.
        # La ausencia de profundidad NO cambia automáticamente la aptitud.
        estado = 'amarillo'
    risks = list(advertencias_locales)
    # El mapa 1:250 000 solo establece intervalos aproximados para el suelo
    # dominante. No convertirlo a depth_cm ni crear un falso puntaje exacto.
    depth_map = soil.get('depth_interval_cm') if depth_unknown else None
    depth_risk = None
    if isinstance(depth_map,(list,tuple)) and len(depth_map)==2:
        low_map, high_map = depth_map
        if isinstance(low_map,(int,float)) and isinstance(high_map,(int,float)) and 0<=low_map<high_map<=250:
            if high_map <= depth:
                depth_risk = 'alto_riesgo_cartografico'
                risks.append(f'INEGI: el suelo dominante presenta roca o capa limitante antes de {high_map:g} cm; el cultivo requiere al menos {depth:g} cm según catálogo provisional. Verificar en parcela.')
            elif low_map >= depth:
                depth_risk = 'sin_alerta_cartografica_directa'
                risks.append('INEGI: intervalo de profundidad no contradice el mínimo catalogado; esto NO confirma profundidad en parcela.')
            else:
                depth_risk = 'intervalo_incierto'
                risks.append(f'INEGI: la restricción cartográfica aparece entre {low_map:g} y {high_map:g} cm; comprobar profundidad real antes de sembrar.')

    if depth_unknown:
        risks.append('Profundidad efectiva DESCONOCIDA: verificar contacto con roca y otras restricciones de raíces; el color es preliminar y la confianza se informa por separado.')
    if m.get('heavy_rain_days_30mm',0) >= 3:
        risks.append('Lluvias fuertes frecuentes: posible encharcamiento y erosión; verificar drenaje.')
    if heat_days is not None and heat_days > 0:
        risks.append(f'Días con Tmax > {screen:g} °C (referencia EXPLORATORIA por cultivo); posible estrés térmico, especialmente en etapas sensibles.')
    if streak is not None and streak >= 7:
        risks.append(f'Racha seca máxima histórica: {streak:g} días consecutivos con lluvia <1 mm; analizar agua del suelo y riego.')
    if m['rain_total_mm'] < rain[0]:
        risks.append('Lluvia histórica inferior al rango PROVISIONAL del ciclo; podría necesitar riego.')
    if m['rain_total_mm'] > rain[1]:
        risks.append('Lluvia histórica superior al rango PROVISIONAL del ciclo; revisar encharcamiento.')
    if not depth_unknown and float(soil['depth_cm']) < depth:
        risks.append('Profundidad del suelo por debajo de la referencia provisional del cultivo.')
    if summary['years_used'] and any(6 <= mo <= 11 for mo in crop_months(crop.get('_planting_month',1),crop['cycle_days'])):
        risks.append('Coincide en parte con la temporada atlántica de ciclones (junio-noviembre); no se predice ninguno.')
    advice = list(crop['management'])
    if depth_unknown:
        advice.append('Medir profundidad efectiva del suelo hasta roca u otra capa limitante; no inferirla de la profundidad 0-5 cm de SoilGrids.')
    if ph_local_observado:
        advice.append(
            'Realizar análisis de suelo antes de sembrar: evaluar disponibilidad '
            'de Fe y Zn, manejo nutricional, carbonatos y condiciones de drenaje. '
            'No aplicar enmiendas sin diagnóstico agronómico.'
        )
    if scores['rainfall'] < 80 or scores['dry_streak'] < 80:
        advice.append('Revisar captación y riego suplementario con recursos disponibles; validar necesidades reales por etapa.')
    if scores['texture'] < 80:
        advice.append('Revisar tipo de suelo, estructura y drenaje antes de modificar el sustrato.')
    if scores['heat_exposure'] < 80 or scores['temperature'] < 80:
        advice.append('Evaluar cambio de fecha, sombreo o manejo protegido; revisar riesgos durante floración.')
    soil_origin = str(soil.get('source','')).upper()
    demo_soil = ('SIMUL' in soil_origin or 'DEMO' in soil_origin or 'INVENT' in soil_origin)
    return {
        'cultivo':crop['name'], 'estado':estado, 'puntaje_provisional':total,
        'aptitud':{'color':estado, 'puntaje_provisional':total, 'es_preliminar':True},
        'confianza_datos':confianza, 'factores_confianza':factores_confianza,
        'confianza_no_es_probabilidad':True,
        'componentes':scores, 'ponderaciones':w,
        'profundidad_cartografica':{'intervalo_cm':depth_map,'riesgo':depth_risk,
             'origen':'INEGI Serie II 1:250 000, suelo dominante' if depth_risk else None,
             'es_medicion':False},
        'componentes_no_evaluados':missing,
        'cobertura_ponderada_de_componentes':round(valid_weight, 3),
        'resultado_condicionado_por_datos_pendientes':bool(depth_unknown),
        'aptitud_sin_profundidad_medida':bool(depth_unknown),
        'restricciones_criticas':critical, 'riesgos_historicos':risks,
        'advertencias_locales':advertencias_locales,
        'pH_evaluacion':{
            'valor_suelo':ph_value,
            'rango_optimo_fao':ph,
            'rango_absoluto_fao':abs_ph,
            'fuera_del_limite_fao':not (abs_ph[0] <= ph_value <= abs_ph[1]),
            'evidencia_local_observacional_aplicable':bool(ph_local_observado),
            'fuente_evidencia_local':ph_regional.get('url') if ph_local_observado else None,
            'interpretacion':('Advertencia condicional, no aptitud demostrada.'
                              if ph_local_observado else 'Regla general FAO ECOCROP.')
        },
        'recomendaciones':list(dict.fromkeys(advice)),
        'resumen_climatico':m, 'anios_utilizados':summary['years_used'],
        'anios_descartados':summary['years_excluded'], 'ciclos_historicos':summary['periods'],
        'fuente_requisitos_verificados':crop.get('ecocrop',{}).get('url'),
        'umbrales_exploratorios':{
            'umbral_calor_maximo_diario_c':screen,
            'racha_seca_referencia_dias':5,
            'metodo':'HEURISTICO sin calibración local; no equivale a daño fisiológico demostrado'},
        'limitaciones':['Rangos FAO ECOCROP generales, no ajustados a variedad, etapa de cultivo o región.',
            'Evidencia de pH de parcelas donde se cultiva NO equivale a un ensayo de tolerancia ni garantiza rendimientos.',
            'Lluvia por ciclo, humedad y radiación tienen rangos provisionales; la textura SoilGrids es estimada; profundidad no disponible salvo medición local.'],
        'validacion_suelo':'SIMULADO: no utilizar para decisiones de siembra' if demo_soil else
                             'ESTIMACION ESPACIAL: verificar en parcela pH, textura y profundidad efectiva',
        'observacion':'Comparación exploratoria, NO predicción, garantía de cosecha ni modelo entrenado.'
    }


def crop_months(month, n_days):
    from datetime import date, timedelta
    start = date(2024,month,1)
    return {(start+timedelta(days=i)).month for i in range(n_days)}


def analyze(rows, soil, crops, planting_month, weights=None):
    output=[]
    for raw in crops:
        crop=dict(raw)
        crop['_planting_month']=planting_month
        summary=summary_by_crop(rows,planting_month,crop['cycle_days'],
                                heat_screen_c=heat_screen_for_crop(crop))
        output.append(evaluate(crop,soil,summary,weights=weights))
    priority={'verde':0,'amarillo':1,'rojo':2,MISSING:3}
    return sorted(output,key=lambda x:(priority[x['estado']],-x.get('puntaje_provisional',-1)))
