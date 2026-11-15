from datetime import date,timedelta
import json
from pathlib import Path
from fieldshift.geo import read_state
from fieldshift.regional import sample_points, daily_aggregate, fetch_region, sample_ndvi_geometry


def test_yucatan_real_geometry():
    geom=read_state()
    assert geom.is_valid and -90.42<geom.bounds[0]<-90.41
    assert -87.53<geom.bounds[2]<-87.52
    assert len(sample_points(geom))>=3
    assert geom.covers(sample_ndvi_geometry(geom))


def test_aggregate_daily():
    sets=[[{'date':'2023-01-01','T2M':t,'T2M_MIN':20,'T2M_MAX':34,'PRECTOTCORR':3,'RH2M':60,'ALLSKY_SFC_SW_DWN':20}]
          for t in [21,27,30]]
    days=daily_aggregate(sets)
    assert days[0]['T2M']==26
    assert days[0]['PRECTOTCORR']==3


def test_region_no_network(tmp_path):
    def fake_fetch(lat,lon,start,end):
        assert start==2023 and end==2025
        day=date(2023,1,1)
        rows=[]
        while day<=date(2025,12,31):
            rows.append({'date':day.strftime('%Y-%m-%d'), 'T2M':28,'T2M_MIN':22,'T2M_MAX':34,
                         'PRECTOTCORR':4, 'RH2M':70,'ALLSKY_SFC_SW_DWN':20})
            day+=timedelta(days=1)
        return rows
    dest=tmp_path/'test.csv'
    metadata=fetch_region(read_state(),dest,fetcher=fake_fetch)
    assert dest.exists() and metadata['numero_muestras']>=3
    assert len(dest.read_text().splitlines())==1097
    assert Path(str(dest)+'.meta.json').exists()
