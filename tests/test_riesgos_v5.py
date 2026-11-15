import json
from datetime import date, timedelta
from pathlib import Path
from fieldshift.climate import summary_by_crop
from fieldshift.engine import analyze, ecocrop_score, heat_screen_for_crop


def make_weather(hot=False, streak=0):
    day=date(2023,1,1)
    out=[]
    while day<=date(2025,12,31):
        dry=(day.month == 6 and day.day <= streak)
        out.append({'date':day,'T2M':29 if hot else 26,
                    'T2M_MIN':24 if hot else 21, 'T2M_MAX':40 if hot else 30,
                    'PRECTOTCORR':0 if dry else 5,
                    'RH2M':65,'ALLSKY_SFC_SW_DWN':20})
        day+=timedelta(days=1)
    return out


def get_maize():
    data=json.loads(Path('config/cultivos_demo.json').read_text(encoding='utf8'))
    return next(c for c in data if c['name']=='Maíz')


def test_fao_limits():
    crop=get_maize()
    assert crop['temperature_c']==[18,33]
    assert crop['soil_ph']==[5,7]
    assert crop['ecocrop']['rainfall_annual_optimal_mm']==[600,1200]
    assert ecocrop_score(7.5,crop['soil_ph'],crop['soil_ph_absolute'])<100


def test_streak_is_consecutive():
    s=summary_by_crop(make_weather(streak=12),6,100)
    assert s['metrics']['dry_streak_max_days']==12
    assert s['metrics']['dry_spells_7plus']>=1
    assert s['years_used']==[2023,2024,2025]


def test_heat_reduces_score():
    maize=get_maize()
    soil={'source':'SIMULACION','ph':6,'texture':'franca','depth_cm':70}
    mild=analyze(make_weather(hot=False),soil,[maize],6)[0]
    hot=analyze(make_weather(hot=True),soil,[maize],6)[0]
    assert hot['componentes']['heat_exposure']<mild['componentes']['heat_exposure']
    assert hot['puntaje_provisional']<mild['puntaje_provisional']


def test_dry_streak_reduces_score():
    maize=get_maize()
    soil={'source':'SIMULACION','ph':6,'texture':'franca','depth_cm':70}
    base=analyze(make_weather(streak=0),soil,[maize],6)[0]
    dry=analyze(make_weather(streak=15),soil,[maize],6)[0]
    assert dry['componentes']['dry_streak']<base['componentes']['dry_streak']
    assert dry['puntaje_provisional']<base['puntaje_provisional']


def test_source_links_all_eight():
    crops=json.loads(Path('config/cultivos_demo.json').read_text(encoding='utf8'))
    assert len(crops)==8
    assert all(c['ecocrop']['url'].startswith('https://ecocrop.apps.fao.org/') for c in crops)
