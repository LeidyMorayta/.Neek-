from datetime import date, timedelta
from pathlib import Path
import pytest
from shapely.geometry import Point
from fieldshift.local_climate import point_climate, recent_rain, recent_et0, reference_et0
from fieldshift.power import read_csv, COLS


def test_climate_cache_is_separate_by_field_and_not_a_statewide_fallback(tmp_path):
    calls=[]
    def fetch(lat,lon,**kwargs):
        calls.append((lat,lon))
        rows=[]
        for i in range(31):
            r={k:1 for k in COLS}
            r['date']=(date(2024,1,1)+timedelta(days=i)).isoformat()
            r['PRECTOTCORR']=3 if lon < -89 else 8
            rows.append(r)
        return rows
    reference='tests/fixtures/clima_SIMULADO_2023_2025.csv'
    a,ma=point_climate(Point(-89.6,20.8),reference,fetcher=fetch,cache_dir=tmp_path)
    b,mb=point_climate(Point(-88.3,20.4),reference,fetcher=fetch,cache_dir=tmp_path)
    repeated,_=point_climate(Point(-89.6,20.8),reference,fetcher=fetch,cache_dir=tmp_path)
    assert len(calls)==2
    assert ma['cache_id'] != mb['cache_id']
    assert not ma['es_promedio_estatal']
    assert recent_rain(a)['lluvia_acumulada_mm']==90
    assert recent_rain(b)['lluvia_acumulada_mm']==240
    assert repeated==a


def test_missing_rain_day_does_not_become_dry_or_zero_rain():
    rows=read_csv('tests/fixtures/clima_SIMULADO_2023_2025.csv')[-30:]
    rows[10]['PRECTOTCORR']=None
    result=recent_rain(rows)
    assert result['dias_validos']==29
    assert result['lluvia_acumulada_mm'] is None
    assert result['racha_seca_max_dias'] is None


def test_reference_et0_validity_and_missing_temperature():
    d=date(2024,6,15)
    assert 3 < reference_et0(d,20.8,25,20,30) < 7
    assert reference_et0(d,20.8,25,None,30) is None
    assert reference_et0(d,20.8,25,30,20) is None
    rows=read_csv('tests/fixtures/clima_SIMULADO_2023_2025.csv')[-30:]
    rows[5]['T2M_MIN']=None
    assert recent_et0(rows,20.8)['et0_media_mm_dia'] is None


def test_failed_download_never_uses_shared_climate(tmp_path):
    def unavailable(*args,**kwargs):
        raise RuntimeError('provider unavailable')
    with pytest.raises(RuntimeError):
        point_climate(Point(-89.6,20.8),'tests/fixtures/clima_SIMULADO_2023_2025.csv',fetcher=unavailable,cache_dir=tmp_path)
    assert not list(tmp_path.glob('*.csv'))
