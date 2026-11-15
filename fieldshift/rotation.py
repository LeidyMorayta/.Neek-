"""Explorador DEMOSTRATIVO de tres rotaciones de cultivos (incluida la declarada).

No predice rendimientos, plagas, fijación cuantitativa de N ni mejora de suelo.
Cada regla es una heurística editable, independiente del clima futuro.
"""
from datetime import date, timedelta
from itertools import product
from functools import lru_cache

from .climate import summary_by_crop
from .engine import evaluate, MISSING, heat_screen_for_crop

LENGTH = 3
DEFAULT_PRIORITIES = {'soil_health': 3, 'water_saving': 3, 'pest_break': 3}
WATER_SCORE = {'baja': 100.0, 'media': 65.0, 'alta': 30.0}
COVER_SCORE = {'baja': 25.0, 'media': 60.0, 'alta': 90.0}
RESIDUE_SCORE = {'baja': 25.0, 'media': 60.0, 'alta': 90.0}
ORDER = {'verde': 0, 'amarillo': 1, 'rojo': 2, MISSING: 3}


def validate_history(data, catalog):
    """Exige la rotación ACTUAL para nunca inventarla a partir de los cultivos previos."""
    declared = data is not None
    if data is None:
        data = {'current_rotation': None, 'previous_crops': []}
    if not isinstance(data, dict):
        raise ValueError('El historial debe ser un objeto JSON.')
    by_name = {c['name']: c for c in catalog}
    actual = data.get('current_rotation')
    if declared and (not isinstance(actual, list) or len(actual) != LENGTH or any(x not in by_name for x in actual)):
        raise ValueError('current_rotation necesita exactamente 3 nombres del catálogo, en orden.')
    past = data.get('previous_crops')
    if not isinstance(past, list) or (declared and not past) or any(x not in by_name for x in past):
        raise ValueError('previous_crops necesita al menos un cultivo conocido (orden antiguo a reciente).')
    weights = dict(DEFAULT_PRIORITIES)
    provided = data.get('priorities', {})
    if not isinstance(provided, dict) or set(provided) - set(weights):
        raise ValueError('priorities solo acepta soil_health, water_saving y pest_break.')
    for key, val in provided.items():
        if isinstance(val, bool) or not isinstance(val, int) or not 1 <= val <= 5:
            raise ValueError(f'La prioridad {key} debe ser entero de 1 a 5.')
        weights[key] = val
    for c in catalog:
        meta = c.get('rotation', {})
        if not all(meta.get(k) in allowed for k, allowed in (
                ('water_demand', WATER_SCORE), ('ground_cover', COVER_SCORE), ('residue', RESIDUE_SCORE))):
            raise ValueError('Faltan metadatos de rotación para: ' + c['name'])
        if not isinstance(meta.get('family'), str) or not meta['family'].strip():
            raise ValueError('Falta familia botánica para: ' + c['name'])
        if not isinstance(meta.get('legume'), bool):
            raise ValueError('Falta atributo legume para: ' + c['name'])
    return actual, past, weights


def _composite(seq, past, by_name, priorities):
    profiles = [by_name[n]['rotation'] for n in seq]
    families = [p['family'] for p in profiles]
    changes = [families[i] != families[i-1] for i in range(1, LENGTH)]
    if past:
        prior_family = by_name[past[-1]]['rotation']['family']
        changes.insert(0, families[0] != prior_family)
    distinct = len(set(families))
    diversity = round(100 * distinct / LENGTH, 1)
    breaks = round(100 * sum(changes) / len(changes), 1)
    legume = 100.0 if any(p['legume'] for p in profiles) else 0.0
    cover = round(sum(COVER_SCORE[p['ground_cover']] for p in profiles)/LENGTH, 1)
    residue = round(sum(RESIDUE_SCORE[p['residue']] for p in profiles)/LENGTH, 1)
    water = round(sum(WATER_SCORE[p['water_demand']] for p in profiles)/LENGTH, 1)
    soil = round(0.30*diversity + 0.30*legume + 0.20*cover + 0.20*residue, 1)
    pt = sum(priorities.values())
    composite = (soil*priorities['soil_health'] + water*priorities['water_saving']
                 + breaks*priorities['pest_break']) / pt
    indicators = {'diversidad_familias': diversity, 'cambio_familia': breaks,
                  'leguminosa_en_rotacion': bool(legume), 'cobertura_relativa': cover,
                  'residuos_relativos': residue, 'menor_demanda_hidrica_relativa': water,
                  'suelo_potencial': soil}
    positives = []
    alerts = []
    if legume:
        positives.append('Incluye leguminosa: puede aportar nitrógeno si existe nodulación efectiva y manejo apropiado.')
    else:
        alerts.append('No incorpora leguminosas; evaluar diversificación y manejo de nutrientes.')
    if distinct >= 3:
        positives.append('Alterna tres familias botánicas distintas: posible reducción de presión de plagas específicas.')
    if not all(changes):
        alerts.append('Repite una familia botánica en la secuencia o respecto al último cultivo previo.')
    if any(p['water_demand'] == 'alta' for p in profiles):
        alerts.append('Incluye cultivos de demanda hídrica relativa alta; revisar riego sin asumir disponibilidad.')
    alerts.append('No se estiman cambios medidos de materia orgánica, nitrógeno o erosión; son indicadores orientativos.')
    return round(composite,1), indicators, positives, alerts


def compare_rotations(rows, soil, catalog, month, history=None, management=None):
    """Comparación de 3 ciclos consecutivos a partir del mes elegido, sin tiempo de barbecho.

    Las ventanas se evalúan con temporadas de 2020 a 2026, según disponibilidad;
    el año ficticio 2024 solo ordena los meses y NO es un pronóstico.
    """
    if not 1 <= month <= 12:
        raise ValueError('Mes inválido.')
    actual, past, priorities = validate_history(history, catalog)
    by_name = {crop['name']: crop for crop in catalog}
    management = management or {}
    previous = management.get('previous_crop')
    if previous:
        if previous not in by_name:
            raise ValueError('El cultivo anterior no pertenece al catálogo.')
        past = [previous]
    supplied = management.get('priorities')
    if supplied is not None:
        if set(supplied) != set(DEFAULT_PRIORITIES) or any(isinstance(v,bool) or not isinstance(v,int) or not 1 <= v <= 5 for v in supplied.values()):
            raise ValueError('Prioridades de manejo inválidas; usa valores de 1 a 5.')
        priorities = dict(supplied)
    system = management.get('water_system', 'sin_declarar')
    if system not in ('sin_declarar', 'temporal', 'riego'):
        raise ValueError('Sistema hídrico no reconocido.')

    @lru_cache(maxsize=None)
    def crop_eval(name, m):
        crop = dict(by_name[name]); crop['_planting_month'] = m
        return evaluate(crop, soil, summary_by_crop(rows, m, crop['cycle_days'], heat_screen_c=heat_screen_for_crop(crop)))

    def build(seq, kind):
        now = date(2024, month, 1)  # calendario de ejemplo para saber los meses sucesivos
        slots = []
        for index, name in enumerate(seq, 1):
            ev = crop_eval(name, now.month)
            slots.append({'ciclo': index, 'cultivo': name,
                          'mes_inicio': now.month, 'duracion_dias_aproximada': by_name[name]['cycle_days'],
                          'estado': ev['estado'], 'puntaje_cultivo': ev.get('puntaje_provisional'),
                          'confianza_datos': ev.get('confianza_datos', 'baja'),
                          'riesgos_historicos': ev.get('riesgos_historicos', []),
                          'restricciones_criticas': ev.get('restricciones_criticas', []),
                          'años_historicos_utilizados': ev.get('anios_utilizados', [])})
            now += timedelta(days=int(by_name[name]['cycle_days']))
        status = (MISSING if any(v['estado'] == MISSING for v in slots)
                  else 'rojo' if any(v['estado'] == 'rojo' for v in slots)
                  else 'amarillo' if any(v['estado'] == 'amarillo' for v in slots) else 'verde')
        escala_confianza = {'baja':0, 'media':1, 'alta':2}
        confianza = min((v['confianza_datos'] for v in slots),
                        key=lambda x:escala_confianza.get(x,0))
        combined, indicators, positives, alerts = _composite(seq, past, by_name, priorities)
        valid_scores = [v['puntaje_cultivo'] for v in slots if v['puntaje_cultivo'] is not None]
        aptitude = round(sum(valid_scores)/len(valid_scores),1) if len(valid_scores)==LENGTH else None
        score = round(0.60*aptitude + 0.40*combined,1) if aptitude is not None else None
        water_penalty = 0
        if system == 'temporal' and score is not None:
            water_penalty = round(sum({'baja':0,'media':4,'alta':12}[by_name[n]['rotation']['water_demand']] for n in seq)/LENGTH, 1)
            score = round(max(0, score-water_penalty), 1)
            alerts.append('Temporal declarado: penalización heurística por demanda hídrica relativa; no calcula déficit ni riego en mm.')
        if system == 'riego':
            alerts.append('Riego declarado: no se asumen caudal ni suministro suficientes; la aptitud sigue usando lluvia histórica sin añadir agua ficticia.')
        if confianza != 'alta':
            alerts.insert(0, f'Confianza de datos {confianza}: verificar profundidad y suelo antes de aplicar la rotación.')
        if status == MISSING:
            alerts.insert(0, 'Hay ciclos sin datos suficientes para evaluar esta rotación.')
        if status == 'rojo':
            alerts.insert(0, 'Al menos un ciclo aparece rojo: no recomendado sin revisión especializada.')
        if status == 'amarillo':
            alerts.insert(0, 'Al menos un cultivo requiere medidas de manejo o verificación.')
        return {'tipo': kind, 'cultivos': list(seq), 'estado': status,
                'confianza_datos': confianza,
                'puntaje_orientativo': score, 'penalizacion_temporal':water_penalty, 'compatibilidad_climatica_promedio': aptitude,
                'indicadores_relativos': indicators, 'ciclos': slots,
                'beneficios_potenciales': positives, 'riesgos_y_limitaciones': alerts,
                'fundamento': 'Reglas provisionales: compatibilidad histórica + diversidad de familias + leguminosas + cobertura/residuos + agua relativa; no mide mejora real del suelo.'}

    current = build(actual, 'actual_declarada') if actual else None
    # Pequeño catálogo: buscar combinaciones de 3 ciclos, NO optimizar a escala industrial.
    proposals = []
    for seq in product(by_name, repeat=LENGTH):
        if actual and seq == tuple(actual):
            continue
        families = [by_name[n]['rotation']['family'] for n in seq]
        if past and families[0] == by_name[past[-1]]['rotation']['family']:
            continue
        if len(set(families)) != LENGTH or len(set(seq)) != LENGTH:
            continue
        if not any(by_name[n]['rotation']['legume'] for n in seq):
            continue
        item = build(seq, 'sugerida')
        if item['estado'] in ('verde', 'amarillo'):
            proposals.append(item)
    # Primera alternativa: mejor puntaje global; segunda: más énfasis en menor agua
    # y, cuando sea posible, con un conjunto diferente de especies.
    proposals.sort(key=lambda item: (ORDER[item['estado']], -item['puntaje_orientativo'], item['cultivos']))
    selected = []
    if proposals:
        best = proposals[0]
        best['enfoque'] = 'compatibilidad_y_salud_potencial_del_suelo'
        selected.append(best)
        other = [p for p in proposals if set(p['cultivos']) != set(best['cultivos'])
                 and p['cultivos'][0] != best['cultivos'][0]]
        if not other:
            other = [p for p in proposals if set(p['cultivos']) != set(best['cultivos'])]
        if not other:
            other = [p for p in proposals if p['cultivos'] != best['cultivos']]
        if other:
            alternative = min(other, key=lambda item: (
                ORDER[item['estado']],
                -item['indicadores_relativos']['menor_demanda_hidrica_relativa'],
                -item['puntaje_orientativo'], item['cultivos']))
            alternative['enfoque'] = 'menor_demanda_hidrica_relativa'
            selected.append(alternative)
    if current:
        current['enfoque'] = 'rotacion_actual_declarada_por_agricultor'
    return {'metodo': 'comparacion_de_tres_rotaciones_por_reglas_v1',
            'historico': sorted({r['date'].year for r in rows}), 'mes_inicio': month,
            'historial_declarado': bool(actual), 'cultivo_anterior_declarado':previous, 'sistema_hidrico':system,
            'historial_previos': past, 'prioridades': priorities,
            'estrategias': ([current] if current else []) + selected,
            'completas': len(selected)==2,
            'advertencias': [
                ('La primera estrategia es la rotación declarada por el agricultor.' if current else
                 ('Cultivo anterior declarado: '+previous+'. No se infiere una rotación actual.' if previous else 'Sin historial declarado: no se infiere una rotación actual ni el efecto del cultivo previo.')),
                'Cada ciclo inicia inmediatamente después del anterior: no considera barbecho ni retrasos operativos.',
                'Los meses sucesivos son aproximados; cada cultivo se evalúa con históricos de ese mes.',
                'Las estrategias sugeridas requieren validación local, disponibilidad de semillas, costos, agua, plagas y mercado.',
                'Indicadores de suelo y agua son proxies ordinales NO mediciones ni mejoras garantizadas.',
                'Los ciclos climáticos históricos NO pronostican fenómenos futuros.',
                'Las estrategias pueden ser menos de 3 si no existen alternativas evaluables bajo los filtros.'
            ]}
