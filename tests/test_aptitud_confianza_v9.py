"""Pruebas con datos sintéticos: separacion de aptitud y calidad de evidencia."""
from datetime import date, timedelta
import json
from pathlib import Path

from fieldshift.climate import summary_by_crop
from fieldshift.engine import evaluate, evaluate_data_confidence
from fieldshift.rotation import compare_rotations


def mock_rows():
    day=date(2023,1,1)
    end=date(2025,12,31)
    result=[]
    while day<=end:
        result.append({'date':day,'T2M':27,'T2M_MIN':22,'T2M_MAX':33,
                       'PRECTOTCORR':4,'RH2M':66,'ALLSKY_SFC_SW_DWN':20})
        day+=timedelta(days=1)
    return result


def crop():
    return {'name':'Cultivo prueba','cycle_days':100,'temperature_c':[20,30],
            'rainfall_mm':[300,500],'soil_ph':[6,8],'textures':['franca'],
            'min_depth_cm':30,'humidity_pct':[40,80],'solar_mj_m2_day':[15,25],
            'management':['Considerar necesidades locales.'], '_planting_month':6}


def summary():
    return summary_by_crop(mock_rows(),6,100)


def test_without_depth_can_remain_green_but_low_confidence():
    soil={'ph':7,'texture':'franca','depth_cm':None,'source':'ISRIC SoilGrids WCS'}
    result=evaluate(crop(),soil,summary())
    assert result['estado']=='verde'
    assert result['aptitud']['color']=='verde'
    assert result['confianza_datos']=='baja'
    assert result['componentes']['depth'] is None
    assert 'depth' in result['componentes_no_evaluados']
    assert result['resultado_condicionado_por_datos_pendientes']
    assert result['cobertura_ponderada_de_componentes']==.91
    assert any('DESCONOCIDA' in s for s in result['riesgos_historicos'])
    assert not any('Verde bloqueado' in s for s in result['riesgos_historicos'])


def test_inegi_interval_informs_confidence_and_risk_not_exact_depth():
    soil={'ph':7,'texture':'franca','depth_cm':None,'depth_interval_cm':[0,10],
          'source':'ISRIC SoilGrids WCS'}
    result=evaluate(crop(),soil,summary())
    assert result['estado']=='verde'
    assert result['confianza_datos']=='media'
    assert result['profundidad_cartografica']['riesgo']=='alto_riesgo_cartografico'
    assert result['componentes']['depth'] is None
    assert result['profundidad_cartografica']['es_medicion'] is False


def test_known_critical_remains_red_even_if_depth_unknown():
    soil={'ph':11,'texture':'franca','depth_cm':None,'source':'ISRIC SoilGrids WCS'}
    result=evaluate(crop(),soil,summary())
    assert result['estado']=='rojo'
    assert result['confianza_datos']=='baja'
    assert result['restricciones_criticas']


def test_field_depth_and_estimated_ph_texture_only_media():
    soil={'ph':7,'texture':'franca','depth_cm':50,'depth_source':'medicion_campo',
          'source':'ISRIC SoilGrids WCS'}
    result=evaluate(crop(),soil,summary())
    assert result['estado']=='verde'
    assert result['confianza_datos']=='media'
    assert result['componentes']['depth']==100


def test_data_quality_high_requires_explicit_verification():
    soil={'ph':7,'texture':'franca','depth_cm':50,
          'depth_source':'medicion_campo','ph_source':'laboratorio',
          'texture_source':'laboratorio','source':'laboratorio'}
    s=summary()
    assert evaluate_data_confidence(soil,s)[0]=='media'
    s['clima_local_validado']=True
    assert evaluate_data_confidence(soil,s)[0]=='alta'


def test_simulated_soil_stays_low_even_with_depth():
    soil={'ph':7,'texture':'franca','depth_cm':50,
          'source':'SIMULACION','depth_source':'medicion_campo'}
    assert evaluate_data_confidence(soil,summary())[0]=='baja'


def test_rotations_report_worst_data_confidence_without_color_cap():
    soil={'ph':7,'texture':'franca','depth_cm':None,'source':'ISRIC SoilGrids WCS'}
    catalog=json.loads(Path('config/cultivos_demo.json').read_text(encoding='utf-8'))
    history=json.loads(Path('config/historial.json').read_text(encoding='utf-8'))
    result=compare_rotations(mock_rows(),soil,catalog,6,history)
    assert len(result['estrategias'])>=1
    assert all(item['confianza_datos']=='baja' for item in result['estrategias'])
    assert all(all(s['confianza_datos']=='baja' for s in item['ciclos']) for item in result['estrategias'])
