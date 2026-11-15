"""Pruebas offline para actualización histórica 2020-2026."""
import json
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlparse

import pytest

from fieldshift.climate import summary_by_crop
from fieldshift.history import (latest_power_day, merge_rows, observed_range,
                                first_unfetched_day, full_year_missing)
from fieldshift.meteomatics import build_url
from fieldshift.power import save_csv, read_csv
from fieldshift.geo import read_state


def weather(first, last, rain=4.0):
    rows=[]
    day=first
    while day<=last:
        rows.append({'date':day,'T2M':27.,'T2M_MIN':22.,'T2M_MAX':35.,
                     'PRECTOTCORR':rain,'RH2M':70.,'ALLSKY_SFC_SW_DWN':20.})
        day+=timedelta(days=1)
    return rows


def test_six_full_years_plus_complete_2026():
    rows=weather(date(2020,1,1),date(2026,11,4))
    summary=summary_by_crop(rows,6,120)
    assert summary['years_used']==[2020,2021,2022,2023,2024,2025,2026]
    assert summary['years_excluded']==[]


def test_partial_2026_excludes_cycle_even_if_90_percent_present():
    rows=weather(date(2020,1,1),date(2026,11,4))
    # 2026 October + 40 días termina en noviembre: aunque la cobertura
    # sobrepase el 90%, no hay observación del final del ciclo.
    summary=summary_by_crop(rows,10,40)
    assert 2026 not in summary['years_used']
    assert 2026 in summary['years_excluded']
    assert all(year in summary['years_used'] for year in range(2020,2026))


def test_crossyear_2025_uses_2026_if_cycle_ended():
    rows=weather(date(2020,1,1),date(2026,11,4))
    summary=summary_by_crop(rows,11,120)
    assert 2025 in summary['years_used']
    assert 2026 in summary['years_excluded']


def test_merging_does_not_replace_valid_with_none():
    a=[{'date':date(2023,2,1),'T2M':28.,'RH2M':70.}]
    b=[{'date':'2023-02-01','T2M':None,'PRECTOTCORR':7.},
       {'date':'2026-01-01','T2M':26.}]
    merged=merge_rows(a,b)
    assert merged[0]['T2M']==28.
    assert merged[0]['PRECTOTCORR']==7.
    assert observed_range(merged)['anios_presentes']==[2023,2026]


def test_solar_cutoff_and_incremental_2026():
    cutoff=latest_power_day(date(2026,11,14))
    assert cutoff==date(2026,11,4)
    entries=weather(date(2026,1,1),date(2026,11,3))
    assert first_unfetched_day(entries,2026,cutoff)==cutoff
    assert not full_year_missing(weather(date(2024,1,1),date(2024,12,31)),2024)


def test_meteomatics_dates_not_from_future():
    url=build_url(20.6,-89.2,2026,first_day=date(2026,11,1),last_day=date(2026,11,12))
    assert '2026-11-02T06:00:00Z--2026-11-13T06:00:00Z:P1D' in url


def test_refresh_nasa_only_missing_periods(tmp_path,monkeypatch):
    import fieldshift.refresh as refresh
    monkeypatch.setattr(refresh,'POWER',tmp_path/'power_2020_2026.csv')
    monkeypatch.setattr(refresh,'POWER_OLD',tmp_path/'power_2023_2025.csv')
    save_csv(weather(date(2023,1,1),date(2025,12,31)),refresh.POWER_OLD)
    called=[]
    def fake_region(geom,out,start=2023,end=2025,start_date=None,end_date=None):
        called.append((start,end,start_date,end_date))
        a=start_date or date(start,1,1)
        b=end_date or date(end,12,31)
        save_csv(weather(a,b),out)
        return {'numero_muestras':7}
    status=refresh.refresh_power(read_state(),today=date(2026,11,14),regional_fetcher=fake_region)
    assert called==[(2020,2022,None,None),(2026,2026,date(2026,1,1),date(2026,11,4))]
    assert status['estado']=='actualizado'
    assert len(read_csv(refresh.POWER))==len(weather(date(2020,1,1),date(2026,11,4)))
    assert len(read_csv(refresh.POWER_OLD))==1096  # legacy remains unchanged
    called.clear()
    again=refresh.refresh_power(read_state(),today=date(2026,11,14),regional_fetcher=fake_region)
    assert called==[] and again['estado']=='ya_disponible'


def test_refresh_nasa_failure_keeps_existing_data(tmp_path,monkeypatch):
    import fieldshift.refresh as refresh
    monkeypatch.setattr(refresh,'POWER',tmp_path/'expanded.csv')
    monkeypatch.setattr(refresh,'POWER_OLD',tmp_path/'old.csv')
    save_csv(weather(date(2023,1,1),date(2025,12,31)),refresh.POWER_OLD)
    def fail(*a,**k):
        raise RuntimeError('Servicio temporalmente no disponible')
    response=refresh.refresh_power(read_state(),today=date(2026,11,14),regional_fetcher=fail)
    assert response['estado']=='parcial' and response['errores']
    assert len(read_csv(refresh.POWER))==1096


def test_partial_meteomatics_does_not_query_current_day(tmp_path,monkeypatch):
    import fieldshift.refresh as refresh
    monkeypatch.setenv('METEOMATICS_USERNAME','test')
    monkeypatch.setenv('METEOMATICS_PASSWORD','test')
    monkeypatch.setattr(refresh,'METEO',tmp_path/'expanded.csv')
    monkeypatch.setattr(refresh,'METEO_OLD',tmp_path/'old.csv')
    from fieldshift.meteomatics import write_meteomatics_csv
    write_meteomatics_csv(weather(date(2020,1,1),date(2025,12,31)),refresh.METEO_OLD)
    calls=[]
    def fake_meteo(lat,lon,start,end,first_day=None,last_day=None):
        calls.append((start,end,first_day,last_day))
        return weather(first_day,last_day)
    response=refresh.refresh_meteo(read_state(),today=date(2026,11,14),meteomatics_fetcher=fake_meteo)
    assert calls==[(2026,2026,date(2026,1,1),date(2026,11,12))]
    assert response['estado']=='actualizado'
    assert response['cobertura']['ultima_fecha']=='2026-11-12'


def test_ndvi_uses_existing_scenes_when_updating(tmp_path,monkeypatch):
    import fieldshift.refresh as refresh
    monkeypatch.setattr(refresh,'NDVI',tmp_path/'ndvi_new.json')
    monkeypatch.setattr(refresh,'NDVI_OLD',tmp_path/'ndvi_old.json')
    refresh.NDVI_OLD.write_text(json.dumps({'intervalo':'2023-2025',
        'escenas':[{'fecha':'2024-07-01','escena':'cached','ndvi_medio':0.4}],
        'errores_lectura':[]}),encoding='utf8')
    called=[]
    def fake_ndvi(patch,start,end,month,months,cloud,scenes,end_date=None):
        called.append((start,end,end_date))
        return {'escenas':[{'fecha':f'{start}-07-01','escena':f'{start}-new','ndvi_medio':0.5}],
                'errores_lectura':[]}
    response=refresh.refresh_ndvi(read_state(),today=date(2026,11,14),ndvi_fetcher=fake_ndvi)
    assert called==[(2020,2022,date(2026,11,4)),(2026,2026,date(2026,11,4))]
    assert response['anios_consultados']==list(range(2020,2027))
    assert 'cached' in [s['escena'] for s in json.loads(refresh.NDVI.read_text())['escenas']]
