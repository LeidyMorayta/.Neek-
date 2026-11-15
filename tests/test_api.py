"""Pruebas locales sin acceso a servicios externos ni datos agrícolas simulados."""
from fastapi.testclient import TestClient
import api

client = TestClient(api.app)


def test_health_no_requiere_datos():
    response = client.get('/health')
    assert response.status_code == 200
    assert response.json()['estado'] == 'activo'


def test_ready_faltan_datos(monkeypatch, tmp_path):
    monkeypatch.setattr(api, 'POWER', tmp_path / 'sin_clima.csv')
    monkeypatch.setattr(api, 'SOIL_FILE', tmp_path / 'sin_suelo.json')
    response = client.get('/ready')
    assert response.status_code == 503
    assert len(response.json()['detail']['faltantes']) == 2


def test_ready_con_archivos(monkeypatch, tmp_path):
    clima = tmp_path / 'power.csv'
    suelo = tmp_path / 'soil.json'
    clima.write_text('archivo solo para prueba de presencia', encoding='utf-8')
    suelo.write_text('{}', encoding='utf-8')
    monkeypatch.setattr(api, 'POWER', clima)
    monkeypatch.setattr(api, 'SOIL_FILE', suelo)
    response = client.get('/ready')
    assert response.status_code == 200


def test_validacion_parametros_antes_del_modelo():
    assert client.post('/analizar', json={'mes':13,'zona':'YUC-01'}).status_code == 422
    assert client.post('/analizar', json={'mes':6,'zona':'PARCELA-01'}).status_code == 422


def test_analizar_llama_motor_sin_guardar(monkeypatch, tmp_path):
    clima = tmp_path / 'clima.csv'
    suelo = tmp_path / 'soil.json'
    clima.touch()
    suelo.touch()
    monkeypatch.setattr(api, 'POWER', clima)
    monkeypatch.setattr(api, 'SOIL_FILE', suelo)
    argumentos = []
    def fake_analizar(**kwargs):
        argumentos.append(kwargs)
        return {'prueba': 'respuesta simulada, no análisis científico'}
    monkeypatch.setattr(api, 'analizar', fake_analizar)
    response = client.post('/analizar', json={'mes':6,'zona':'YUC-06'})
    assert response.status_code == 200
    assert response.json()['prueba'].startswith('respuesta simulada')
    assert argumentos == [{'mes':6,'zona':'YUC-06','guardar_resultado':False,'mostrar_resumen':False}]
