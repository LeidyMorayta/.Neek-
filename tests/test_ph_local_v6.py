"""Comprueba la excepción de pH observacional de chile habanero en Yucatán."""
import json
from pathlib import Path
from fieldshift.climate import summary_by_crop
from fieldshift.engine import evaluate, analyze, ecocrop_score
from tests.test_riesgos_v5 import make_weather

CAT = json.loads(Path('config/cultivos_demo.json').read_text(encoding='utf-8'))
HABANERO = next(c for c in CAT if c['name'] == 'Chile habanero')
MAIZ = next(c for c in CAT if c['name'] == 'Maíz')


def _soil(ph):
    return {'source': 'SIMULACION', 'ph': ph,
            'texture': 'franca', 'depth_cm': 60}


def _evaluate(crop, ph):
    return analyze(make_weather(), _soil(ph), [crop], 6)[0]


def test_fao_not_overwritten():
    assert HABANERO['soil_ph'] == [6, 6.5]
    assert HABANERO['soil_ph_absolute'] == [5.3, 7]
    assert ecocrop_score(7.5, HABANERO['soil_ph'], HABANERO['soil_ph_absolute']) == 0


def test_yucatan_ph_7_5_conditional_not_critical():
    item = _evaluate(HABANERO, 7.5)
    assert item['pH_evaluacion']['evidencia_local_observacional_aplicable']
    assert item['pH_evaluacion']['fuera_del_limite_fao']
    assert item['componentes']['ph'] == 0
    assert not any('pH fuera' in x for x in item['restricciones_criticas'])
    assert item['advertencias_locales']
    assert item['estado'] in ('amarillo','rojo')
    assert item['estado'] != 'verde'


def test_extreme_high_ph_remains_red():
    item = _evaluate(HABANERO, 8.2)
    assert item['estado'] == 'rojo'
    assert any('pH fuera' in x for x in item['restricciones_criticas'])
    assert not item['pH_evaluacion']['evidencia_local_observacional_aplicable']


def test_low_ph_remains_critical():
    item = _evaluate(HABANERO, 4.8)
    assert item['estado'] == 'rojo'
    assert any('pH fuera' in x for x in item['restricciones_criticas'])


def test_no_ph_exception_for_other_crop():
    item = _evaluate(MAIZ, 9.0)
    assert item['estado'] == 'rojo'
    assert any('pH fuera' in x for x in item['restricciones_criticas'])


def test_another_critical_still_red():
    summary=summary_by_crop(make_weather(),6,HABANERO['cycle_days'])
    crop=dict(HABANERO,_planting_month=6)
    item=evaluate(crop, {'source':'SIMULACION','ph':7.5,'texture':'franca','depth_cm':5}, summary)
    assert item['estado']=='rojo'
    assert any('Profundidad' in x for x in item['restricciones_criticas'])


def test_no_local_exception_inside_fao():
    item=_evaluate(HABANERO, 6.3)
    assert not item['pH_evaluacion']['evidencia_local_observacional_aplicable']
    assert not item['pH_evaluacion']['fuera_del_limite_fao']


def test_observed_max_without_guarantee():
    item=_evaluate(HABANERO, 7.7)
    assert item['pH_evaluacion']['evidencia_local_observacional_aplicable']
    assert item['estado'] != 'verde'


def test_poor_other_scores_can_still_be_red_with_local_exception():
    from fieldshift.engine import WEIGHTS
    w = {k: (1.0 if k == 'ph' else 0.0) for k in WEIGHTS}
    item = analyze(make_weather(), _soil(7.5), [HABANERO], 6, weights=w)[0]
    assert item['estado'] == 'rojo'
    assert item['pH_evaluacion']['evidencia_local_observacional_aplicable']
    assert not item['restricciones_criticas']
