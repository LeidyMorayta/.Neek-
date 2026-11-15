import json
from pathlib import Path
import pytest
from fieldshift.power import read_csv
from fieldshift.rotation import compare_rotations, validate_history

CAT = json.loads(Path('config/cultivos_demo.json').read_text(encoding='utf-8'))
HIST = json.loads(Path('config/historial.json').read_text(encoding='utf-8'))
SOIL = json.loads(Path('tests/fixtures/suelo_demo.json').read_text(encoding='utf-8'))


def test_three_strategies_with_current_first():
    rows = read_csv('tests/fixtures/clima_SIMULADO_2023_2025.csv')
    plans = compare_rotations(rows, SOIL, CAT, 6, HIST)
    assert len(plans['estrategias']) == 3
    assert plans['completas'] is True
    assert plans['estrategias'][0]['tipo'] == 'actual_declarada'
    assert plans['estrategias'][0]['cultivos'] == HIST['current_rotation']
    assert all(s['tipo'] == 'sugerida' for s in plans['estrategias'][1:])
    assert all(len(s['ciclos']) == 3 for s in plans['estrategias'])
    assert all(s['estado'] in ('verde','amarillo') for s in plans['estrategias'][1:])


def test_reject_unknown_current_crop():
    h = dict(HIST, current_rotation=['No existe','Maíz','Frijol'])
    with pytest.raises(ValueError, match='current_rotation'):
        validate_history(h, CAT)


def test_reject_bad_priority():
    h = dict(HIST, priorities={'soil_health':0})
    with pytest.raises(ValueError, match='prioridad'):
        validate_history(h, CAT)


def test_missing_soil_means_no_invented_suggestions():
    rows = read_csv('tests/fixtures/clima_SIMULADO_2023_2025.csv')
    plans = compare_rotations(rows, {'texture':'franca'}, CAT, 6, HIST)
    assert len(plans['estrategias']) == 1
    assert plans['estrategias'][0]['estado'] == 'datos_insuficientes'
    assert plans['completas'] is False


def test_last_crop_affects_family_break():
    rows = read_csv('tests/fixtures/clima_SIMULADO_2023_2025.csv')
    a = compare_rotations(rows, SOIL, CAT, 6, HIST)['estrategias'][0]
    b = compare_rotations(rows, SOIL, CAT, 6, dict(HIST,previous_crops=['Frijol']))['estrategias'][0]
    assert a['indicadores_relativos']['cambio_familia'] < b['indicadores_relativos']['cambio_familia']


def test_suggestions_without_history_do_not_invent_current_rotation():
    rows = read_csv('tests/fixtures/clima_SIMULADO_2023_2025.csv')
    plans = compare_rotations(rows, SOIL, CAT, 6)
    assert plans['historial_declarado'] is False
    assert plans['historial_previos'] == []
    assert len(plans['estrategias']) == 2
    assert all(p['tipo'] == 'sugerida' for p in plans['estrategias'])


def test_soil_changes_rotations_and_unsuitable_soil_removes_them():
    rows = read_csv('tests/fixtures/clima_SIMULADO_2023_2025.csv')
    def plans(ph, texture):
        return compare_rotations(rows, dict(SOIL,ph=ph,texture=texture), CAT, 6)['estrategias']
    acid = plans(5, 'arenosa')
    neutral = plans(7.1, 'franco-arenosa')
    assert acid[0]['cultivos'] != neutral[0]['cultivos']
    assert acid[0]['puntaje_orientativo'] != neutral[0]['puntaje_orientativo']
    assert plans(9.5, 'arcillosa') == []


def test_previous_crop_and_water_management_change_rotation_explanation():
    rows=read_csv('tests/fixtures/clima_SIMULADO_2023_2025.csv')
    base={'water_system':'temporal','previous_crop':'Sorgo','priorities':{'soil_health':3,'water_saving':5,'pest_break':3}}
    plans=compare_rotations(rows,SOIL,CAT,6,management=base)
    by_name={c['name']:c for c in CAT}
    for strategy in plans['estrategias']:
        assert by_name[strategy['cultivos'][0]]['rotation']['family'] != by_name['Sorgo']['rotation']['family']
        assert strategy['penalizacion_temporal'] > 0
    irrigated=compare_rotations(rows,SOIL,CAT,6,management=dict(base,water_system='riego'))
    assert all(s['penalizacion_temporal']==0 for s in irrigated['estrategias'])
    assert plans['prioridades']['water_saving']==5
    assert plans['cultivo_anterior_declarado']=='Sorgo'
