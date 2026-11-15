"""Pruebas con polígonos SINTÉTICOS: no equivalen a cartografía de Yucatán."""
import json
import zipfile
from pathlib import Path

import fiona
import pytest
from shapely.geometry import box, mapping

from fieldshift.inegi_depth import interpret_key, import_inegi, read_inegi
from fieldshift.engine import analyze
from tests.test_riesgos_v5 import make_weather


def test_only_primary_inegi_soil_is_read():
    assert interpret_key('LPskli+RGeulep/2R')['intervalo_cm']==[0,10]
    assert interpret_key('RGeulep+LPskli/1')['intervalo_cm']==[0,50]
    assert interpret_key('RGeulen/1r')['intervalo_cm']==[50,100]
    assert interpret_key('CMeuar+LPskli/1')['intervalo_cm'] is None
    assert interpret_key('LP/1R')['intervalo_cm'] is None
    assert interpret_key('')['intervalo_cm'] is None


def create_fixture_shapefile(tmp, sample):
    folder=tmp/'edafologia'
    folder.mkdir()
    file=folder/'suelo_serie_ii.shp'
    schema={'geometry':'Polygon','properties':{'Clave_WRB':'str:80'}}
    lon,lat=sample['longitud'],sample['latitud']
    with fiona.open(file,'w',driver='ESRI Shapefile',crs='EPSG:4326',schema=schema,encoding='UTF-8') as dst:
        dst.write({'type':'Feature','properties':{'Clave_WRB':'LPskli+RGeulep/2R'},
                   'geometry':mapping(box(lon-.01,lat-.01,lon+.01,lat+.01))})
    return folder


def test_import_shapefile_zip_and_no_fabricated_depth(tmp_path):
    from fieldshift.soilgrids import download_soils
    from shapely.geometry import shape
    data=json.loads(Path('geojson/yucatan_estado.geojson').read_text())
    from fieldshift import soilgrids
    # Inyectar valores de ensayo sin conexión a SoilGrids
    def layer(prop,*_):
        return {'phh2o':7.3,'sand':50,'silt':25,'clay':25}[prop]
    soiljson=tmp_path/'suelo.json'
    soilgrids.download_soils(shape(data['features'][0]['geometry']),soiljson,layer)
    sample=json.loads(soiljson.read_text())['muestras'][0]
    folder=create_fixture_shapefile(tmp_path,sample)
    output=tmp_path/'inegi.json'
    doc=import_inegi(folder,output,samples_path=soiljson)
    result=doc['muestras'][0]
    assert result['estado']=='coincidencia_unica'
    assert result['evidencia']['intervalo_cm']==[0,10]
    assert result['profundidad_medida_cm'] is None
    assert read_inegi(output)[result['id']]['evidencia']['calificador']=='lítico'
    z=tmp_path/'inegi.zip'
    with zipfile.ZipFile(z,'w') as archive:
        for file in folder.rglob('*'):
            archive.write(file,file.relative_to(tmp_path))
    assert import_inegi(z,tmp_path/'from_zip.json',samples_path=soiljson)['muestras'][0]['evidencia']['intervalo_cm']==[0,10]


def test_missing_layer_rejected(tmp_path):
    from fieldshift.soilgrids import download_soils
    from shapely.geometry import shape
    from fieldshift import soilgrids
    data=json.loads(Path('geojson/yucatan_estado.geojson').read_text())
    def layer(prop,*_):
        return {'phh2o':7.3,'sand':50,'silt':25,'clay':25}[prop]
    soiljson=tmp_path/'suelo.json'
    soilgrids.download_soils(shape(data['features'][0]['geometry']),soiljson,layer)
    bad=tmp_path/'bad.geojson'
    bad.write_text(json.dumps({'type':'FeatureCollection','features':[]}))
    with pytest.raises(ValueError,match='Clave_WRB'):
        import_inegi(bad,tmp_path/'out.json',samples_path=soiljson)


def test_interval_generates_warning_not_fake_depth():
    catalog=json.loads(Path('config/cultivos_demo.json').read_text())
    maize=next(c for c in catalog if c['name']=='Maíz')
    soil={'ph':6.8,'texture':'franca','depth_cm':None,'depth_interval_cm':[0,10],
          'source':'ISRIC SoilGrids'}
    result=analyze(make_weather(),soil,[maize],6)[0]
    assert result['confianza_datos']=='media'
    assert result['componentes']['depth'] is None
    assert result['profundidad_cartografica']['riesgo']=='alto_riesgo_cartografico'
    assert any('INEGI:' in s for s in result['riesgos_historicos'])


def test_measured_depth_has_priority():
    catalog=json.loads(Path('config/cultivos_demo.json').read_text())
    maize=next(c for c in catalog if c['name']=='Maíz')
    soil={'ph':6.8,'texture':'franca','depth_cm':70,'depth_interval_cm':None,
          'source':'ISRIC SoilGrids'}
    result=analyze(make_weather(),soil,[maize],6)[0]
    assert result['componentes']['depth']==100
    assert result['profundidad_cartografica']['riesgo'] is None


def test_missing_prj_requires_explicit_crs(tmp_path):
    from fieldshift.soilgrids import download_soils
    from shapely.geometry import shape as shapely_shape
    from fieldshift import soilgrids
    from pyproj import Transformer
    geo=json.loads(Path('geojson/yucatan_estado.geojson').read_text())
    def layer(prop,*_):
        return {'phh2o':7.3,'sand':50,'silt':25,'clay':25}[prop]
    soiljson=tmp_path/'suelo.json'
    soilgrids.download_soils(shapely_shape(geo['features'][0]['geometry']), soiljson, layer)
    sample=json.loads(soiljson.read_text())['muestras'][0]
    shp=tmp_path/'fuente'/'soil_inegi.shp'
    shp.parent.mkdir()
    to_lcc=Transformer.from_crs(4326,6362,always_xy=True)
    x,y=to_lcc.transform(sample['longitud'],sample['latitud'])
    schema={'geometry':'Polygon','properties':{'Clave_WRB':'str:80'}}
    with fiona.open(shp,'w',driver='ESRI Shapefile',crs='EPSG:6362',schema=schema,encoding='UTF-8') as dst:
        dst.write({'type':'Feature','properties':{'Clave_WRB':'LPskli+RGeulep/2R'},
                   'geometry':mapping(box(x-2000,y-2000,x+2000,y+2000))})
    shp.with_suffix('.prj').unlink()
    z=tmp_path/'sin_prj.zip'
    with zipfile.ZipFile(z,'w') as archive:
        for file in shp.parent.glob('*'):
            archive.write(file,file.name)
    with pytest.raises(ValueError,match='carece de CRS'):
        import_inegi(z,tmp_path/'rejected.json',samples_path=soiljson)
    doc=import_inegi(z,tmp_path/'accepted.json',samples_path=soiljson,crs_faltante='EPSG:6362')
    assert doc['crs_declarado_para_capas_sin_prj']=='EPSG:6362'
    assert doc['muestras'][0]['estado']=='coincidencia_unica'
    assert doc['muestras'][0]['evidencia']['intervalo_cm']==[0,10]
    with pytest.raises(ValueError,match='no ubica ninguna muestra'):
        import_inegi(z,tmp_path/'wrong.json',samples_path=soiljson,crs_faltante='EPSG:4326')
