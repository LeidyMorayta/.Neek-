"""Pruebas offline de parcelas (NO consultan NASA o SoilGrids en Internet)."""
import json
from pathlib import Path

from fastapi.testclient import TestClient
import api
from fieldshift.parcel import InvalidParcel, validate_parcel, run_parcel_analysis, parcel_soil

POINTS = [[-89.62,20.85],[-89.60,20.85],[-89.60,20.83],[-89.62,20.83]]


def test_matriz_geojson_misma_parcela():
    polygon, hectares, point = validate_parcel(points=POINTS)
    g, g_ha, g_pt = validate_parcel(geojson={
        'type':'Feature', 'properties':{'nombre':'Prueba'},
        'geometry': {'type':'Polygon','coordinates':[POINTS + [POINTS[0]]]},
    })
    assert abs(hectares - 460.93) < 0.1
    assert hectares == g_ha
    assert polygon.equals(g)
    assert polygon.covers(point) and g.covers(g_pt)


def test_invalidez_y_fuera_de_yucatan():
    bad_inputs = [
        {'points':[[-99.1,19.4],[-99.0,19.4],[-99.0,19.5]]},
        {'points':[[-89.62,20.85],[-89.60,20.83],[-89.60,20.85],[-89.62,20.83]]},
        {'points':[[20.85,-89.62],[20.85,-89.60],[20.83,-89.60]]},
        {'points':[[-89.62,20.85],[-89.60,20.83]]},
        {'geojson':{'type':'Point','coordinates':POINTS[0]}},
        {'points':POINTS,'geojson':{'type':'Polygon','coordinates':[POINTS]}},
    ]
    for item in bad_inputs:
        try:
            validate_parcel(**item)
            assert False, f'Se aceptó un polígono inválido: {item}'
        except InvalidParcel:
            pass


def test_poligono_pequeno_y_rfc7946():
    points = [[-89.611,20.841],[-89.6105,20.841],[-89.6105,20.8405]]
    geometry, area, interior = validate_parcel(points=points)
    assert 0 < area < 2
    assert geometry.covers(interior)


def test_soil_grids_cache_id_distinto_ubicacion():
    from shapely.geometry import Point
    calls = []
    def wcs(prop, lat, lon, sample_id):
        calls.append((prop, lat, lon, sample_id))
        return {'phh2o':7.1, 'sand':66.0, 'silt':20.0, 'clay':14.0}[prop]
    one = parcel_soil(Point(-89.61,20.84),get_layer=wcs)
    two = parcel_soil(Point(-89.61,20.84),get_layer=wcs)
    other = parcel_soil(Point(-89.6105,20.8405),get_layer=wcs)
    assert len(calls) == 12
    assert one['id'] == two['id'] != other['id']
    assert one['depth_cm'] is None
    assert one['raster_interval_cm'] == [0,5]
    assert one['ph'] == 7.1


def test_api_parcela_validacion_antes_de_solicitar_clima(monkeypatch,tmp_path):
    client = TestClient(api.app)
    response = client.post('/analizar-parcela',json={'mes':6,'puntos':[[0,0],[1,0],[1,1]]})
    assert response.status_code == 422
    monkeypatch.setattr(api,'POWER',tmp_path/'clima_faltante.csv')
    response = client.post('/analizar-parcela',json={'mes':6,'puntos':POINTS})
    assert response.status_code == 503
    assert 'NASA POWER' in json.dumps(response.json(),ensure_ascii=False)
    assert client.get('/ready-parcela').status_code == 503


def test_api_llama_el_motor_para_el_poligono(monkeypatch,tmp_path):
    climate = tmp_path/'clima.csv'
    climate.touch()
    monkeypatch.setattr(api,'POWER',climate)
    args = []
    def fake(geom,area,point,month,filename,catalog,history,**kwargs):
        assert callable(kwargs['get_climate'])
        assert kwargs['management']['water_system'] == 'sin_declarar'
        args.append((area,month,filename,geom.covers(point)))
        return {'prueba':'resultado_del_motor; no datos ficticios en producción'}
    monkeypatch.setattr(api,'run_parcel_analysis',fake)
    res = TestClient(api.app).post('/analizar-parcela',json={'mes':6,'puntos':POINTS})
    assert res.status_code == 200
    assert len(args) == 1
    assert args[0][0] > 400 and args[0][1] == 6 and args[0][3]


def test_integracion_con_datos_de_prueba_aislados():
    """Fixture SIMULADO usada EXCLUSIVAMENTE en pruebas; no se despliega en data/."""
    g, a, point = validate_parcel(points=POINTS)
    root = Path(__file__).resolve().parents[1]
    catalog = json.loads((root/'config/cultivos_demo.json').read_text())
    history = json.loads((root/'config/historial.json').read_text())
    def soil(_):
        return {'id':'fixture','ph':7.1,'texture':'franco-arenosa',
                'sand_pct':65,'silt_pct':20,'clay_pct':15,'depth_cm':None,
                'source':'ISRIC SoilGrids WCS (test offline)'}
    result = run_parcel_analysis(g,a,point,6,root/'tests/fixtures/clima_SIMULADO_2023_2025.csv',catalog,history,get_soil=soil)
    assert len(result['cultivos']) == 8
    assert 1 <= len(result['rotaciones']['estrategias']) <= 3
    assert result['suelo']['estado_calidad'] == 'informacion_parcial'
    assert result['clima']['humedad_suelo'] is None
    assert result['parcela']['superficie_ha'] == a


def test_parcel_does_not_use_shared_demo_history():
    g, a, point = validate_parcel(points=POINTS)
    catalog = json.loads(Path('config/cultivos_demo.json').read_text())
    history = json.loads(Path('config/historial.json').read_text())
    soil = lambda _: {'id':'fixture','ph':7.1,'texture':'franco-arenosa',
                      'sand_pct':65,'silt_pct':20,'clay_pct':15,'depth_cm':None,
                      'source':'ISRIC SoilGrids (offline test)'}
    result = run_parcel_analysis(g,a,point,6,'tests/fixtures/clima_SIMULADO_2023_2025.csv',catalog,history,get_soil=soil)
    assert result['rotaciones']['historial_declarado'] is False
    assert all(r['tipo'] == 'sugerida' for r in result['rotaciones']['estrategias'])


def test_location_climate_drives_field_recommendations():
    from fieldshift.power import read_csv
    g,a,point=validate_parcel(points=POINTS)
    catalog=json.loads(Path('config/cultivos_demo.json').read_text())
    soil=lambda _: {'id':'fixture','ph':7.1,'texture':'franco-arenosa','sand_pct':65,
                    'silt_pct':20,'clay_pct':15,'depth_cm':None,'source':'ISRIC offline test'}
    file='tests/fixtures/clima_SIMULADO_2023_2025.csv'
    baseline=run_parcel_analysis(g,a,point,6,file,catalog,None,get_soil=soil)
    def drought(actual_point, reference):
        assert actual_point.equals(point)
        rows=read_csv(reference)
        for row in rows:
            row['PRECTOTCORR']=0
        return rows,{'fuente':'Offline location test','es_promedio_estatal':False}
    dry=run_parcel_analysis(g,a,point,6,file,catalog,None,get_soil=soil,get_climate=drought)
    assert baseline['rotaciones']['estrategias']
    assert not dry['rotaciones']['estrategias']
    assert dry['clima']['fuente']=='Offline location test'
    assert dry['clima']['reciente_30_dias']['lluvia_acumulada_mm']==0


def test_api_rejects_invalid_water_management_before_queries():
    client=TestClient(api.app)
    assert client.post('/analizar-parcela',json={'puntos':POINTS,'manejo':{'water_system':'inventado'}}).status_code==422
    assert client.post('/analizar-parcela',json={'puntos':POINTS,'manejo':{'priorities':{'water_saving':9}}}).status_code==422
