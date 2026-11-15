from datetime import date, timedelta
from fieldshift.geo import read_state
from fieldshift.power import power_to_rows
from fieldshift.climate import summary_by_crop
from fieldshift.engine import interval_score, evaluate


def mock_rows(start=date(2023,1,1),end=date(2025,12,31)):
    arr=[]
    while start <= end:
        arr.append({'date':start,'T2M':27,'T2M_MIN':22,'T2M_MAX':33,
                    'PRECTOTCORR':4.0,'RH2M':66,'ALLSKY_SFC_SW_DWN':20})
        start += timedelta(days=1)
    return arr


def mock_crop():
    return {'name':'Cultivo prueba','cycle_days':100,'temperature_c':[20,30],
            'rainfall_mm':[300,500],'soil_ph':[6,8], 'textures':['franca'],
            'min_depth_cm':30,'humidity_pct':[40,80], 'solar_mj_m2_day':[15,25],
            'management':['Revisar disponibilidad de agua.'], '_planting_month':6}


def test_geometry():
    g=read_state()
    assert g.area>0


def test_interval():
    assert interval_score(25,[20,30],5)==100
    assert interval_score(35,[20,30],5)==0


def test_complete_years():
    s=summary_by_crop(mock_rows(),6,100)
    assert s['sufficient'] and len(s['years_used'])==3
    assert abs(s['metrics']['rain_total_mm']-400)<.001


def test_cross_year_incomplete():
    s=summary_by_crop(mock_rows(),11,100)
    assert s['years_used']==[2023,2024]
    assert s['sufficient']


def test_missing_soil():
    s=summary_by_crop(mock_rows(),6,100)
    assert evaluate(mock_crop(),{'texture':'franca','depth_cm':50},s)['estado']=='datos_insuficientes'


def test_red_critical():
    s=summary_by_crop(mock_rows(),6,100)
    result=evaluate(mock_crop(),{'ph':10.5,'texture':'franca','depth_cm':5},s)
    assert result['estado']=='rojo' and result['restricciones_criticas']


def test_positive_case():
    s=summary_by_crop(mock_rows(),6,100)
    result=evaluate(mock_crop(),{'ph':7,'texture':'franca','depth_cm':50},s)
    assert result['estado']=='verde' and result['puntaje_provisional']>=80


def test_power_parser():
    payload={'properties':{'parameter':{key:{'20230101':2} for key in ('T2M','T2M_MIN','T2M_MAX','PRECTOTCORR','RH2M','ALLSKY_SFC_SW_DWN')}}}
    assert power_to_rows(payload)[0]['T2M']==2

