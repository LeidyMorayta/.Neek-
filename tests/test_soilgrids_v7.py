"""Pruebas sintéticas del lector WCS; NO son valores reales de Yucatán."""
from io import BytesIO
import json
from pathlib import Path
import numpy as np
import pytest
import rasterio
from rasterio.io import MemoryFile
from rasterio.transform import from_origin
from shapely.geometry import shape

from fieldshift.soilgrids import (wcs_params, decode_tiff, build_sample,
                                  download_soils, approximate_texture,
                                  read_soil_samples)
from fieldshift.engine import analyze
from tests.test_riesgos_v5 import make_weather


def fake_tiff(value):
    profile = {'driver':'GTiff','height':2,'width':2,'count':1,
               'dtype':'int16','crs':'EPSG:4326',
               'transform':from_origin(-89,22,.01,.01),'nodata':-32768}
    with MemoryFile() as m:
        with m.open(**profile) as ds:
            ds.write(np.array([[value,-32768],[value,value]],dtype='int16'),1)
        return m.read()


def sample_layer(prop, lat, lon, sid):
    return {'phh2o':7.4,'sand':52.0,'silt':28.0,'clay':20.0}[prop]


def test_wcs_params_have_two_subsets():
    p=wcs_params('phh2o',20.6,-89.7)
    assert len([v for k,v in p if k == 'SUBSET'])==2
    assert ('COVERAGEID','phh2o_0-5cm_mean') in p
    with pytest.raises(ValueError):
        wcs_params('secret',20.6,-89.7)


def test_decode_tiff_units_and_nodata():
    assert decode_tiff(fake_tiff(75)) == pytest.approx(7.5)
    with pytest.raises(ValueError):
        decode_tiff(b'<ServiceException>WCS unavailable</ServiceException>')


def test_sample_actual_fields_no_fabricated_depth():
    s=build_sample({'latitud':20.6,'longitud':-89.7},1,sample_layer)
    assert s['ph']==7.4
    assert s['texture']=='franco-arenosa'
    assert s['depth_cm'] is None
    assert s['source'].startswith('ISRIC')


def test_download_creates_points_and_never_simulates_soil(tmp_path,monkeypatch):
    from fieldshift import soilgrids
    shape_geom=json.loads(Path('geojson/yucatan_estado.geojson').read_text())['features'][0]['geometry']
    monkeypatch.setattr(soilgrids, 'POINTS_GEOJSON', tmp_path/'puntos.geojson')
    doc=download_soils(shape(shape_geom), tmp_path/'suelo.json', sample_layer)
    assert len(doc['muestras']) >= 3
    assert (tmp_path/'puntos.geojson').exists()
    assert len(read_soil_samples(tmp_path/'suelo.json')['muestras'])==len(doc['muestras'])
    assert all(s['depth_cm'] is None for s in doc['muestras'])


def test_no_imaginary_depth_blocks_green():
    from pathlib import Path
    catalog=json.loads(Path('config/cultivos_demo.json').read_text())
    maize=next(c for c in catalog if c['name']=='Maíz')
    s={'ph':6.8,'texture':'franca','depth_cm':None,
       'source':'ISRIC SoilGrids 2.0 WCS (estimación, NO medición local)'}
    result=analyze(make_weather(),s,[maize],6)[0]
    assert result['confianza_datos']=='baja'
    assert result['componentes']['depth'] is None
    assert result['resultado_condicionado_por_datos_pendientes']
    assert 'depth' in result['componentes_no_evaluados']


def test_wcs_outage_must_not_create_fake_soil(tmp_path):
    from shapely.geometry import Polygon
    geom=Polygon([(-89.8,20.5),(-89,20.5),(-89,21.1),(-89.8,21.1)])
    def failure(*args):
        raise RuntimeError('Servicio desconectado')
    with pytest.raises(RuntimeError):
        download_soils(geom,tmp_path/'suelo.json',failure)
    assert not (tmp_path/'suelo.json').exists()
