"""NEEK: interfaz y API FastAPI para FieldShift Yucatán V10."""
import json
import logging
import os
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from main import analizar, POWER, CATALOG, HISTORY
from fieldshift.soilgrids import SOIL_FILE, read_soil_samples
from fieldshift.parcel import InvalidParcel, validate_parcel, run_parcel_analysis

logger = logging.getLogger(__name__)
WEB_DIR = Path(__file__).resolve().parent / 'web'
app = FastAPI(
    title='NEEK — FieldShift API',
    description='Exploración agrícola: polígono real, clima regional y muestra puntual SoilGrids.',
    version='11.0-web',
)

origins = [v.strip().rstrip('/') for v in os.getenv('FIELDSHIFT_ALLOWED_ORIGINS','').split(',') if v.strip()]
if origins:
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=False,
                       allow_methods=['GET','POST'], allow_headers=['Content-Type'])


class SolicitudAnalisis(BaseModel):
    mes: int = Field(default=6, ge=1, le=12)
    zona: str = Field(default='YUC-01', pattern=r'^YUC-0[1-7]$')


class Prioridades(BaseModel):
    soil_health: int = Field(default=3, ge=1, le=5)
    water_saving: int = Field(default=3, ge=1, le=5)
    pest_break: int = Field(default=3, ge=1, le=5)


class ManejoParcela(BaseModel):
    water_system: Literal['sin_declarar','temporal','riego'] = 'sin_declarar'
    previous_crop: str | None = None
    priorities: Prioridades = Field(default_factory=Prioridades)


class SolicitudParcela(BaseModel):
    mes: int = Field(default=6, ge=1, le=12)
    geojson: dict | None = None
    puntos: list | None = Field(default=None, max_length=500)
    historial: dict | None = None
    manejo: ManejoParcela = Field(default_factory=ManejoParcela)
    comparison_days: int = Field(default=30, ge=15, le=180)


def _faltantes(need_soil_samples=True):
    missing = []
    if not POWER.is_file():
        missing.append("Clima NASA POWER: ejecuta 'python main.py descargar'.")
    if need_soil_samples and not SOIL_FILE.is_file():
        missing.append("Suelo para siete muestras: ejecuta 'python main.py descargar-suelo'.")
    return missing


def _exigir_datos(need_soil_samples=True):
    missing = _faltantes(need_soil_samples)
    if missing:
        raise HTTPException(status_code=503, detail={'mensaje':'Datos NASA/SoilGrids faltantes', 'faltantes':missing})


@app.get('/')
def home():
    return FileResponse(WEB_DIR / 'index.html')


@app.get('/health')
def health():
    return {'estado':'activo', 'api':'NEEK / FieldShift', 'version':'11.0-web'}


@app.get('/ready')
def ready():
    _exigir_datos()
    return {'estado':'listo','clima':POWER.name,'suelo':SOIL_FILE.name}


@app.get('/ready-parcela')
def ready_parcela():
    _exigir_datos(False)
    return {'estado':'listo', 'clima':POWER.name,
            'suelo':'Se consultará SoilGrids al analizar una parcela; requiere Internet.'}


@app.get('/puntos')
def puntos():
    _exigir_datos()
    try:
        samples = read_soil_samples()['muestras']
    except (ValueError, KeyError, OSError) as exc:
        logger.exception('No se pudieron leer muestras')
        raise HTTPException(status_code=503, detail='Datos de suelo inválidos.') from exc
    return {'puntos':[{'id':p['id'],'latitud':p['latitud'],'longitud':p['longitud']} for p in samples],
            'alcance':'Siete muestras; no representan parcelas agrícolas.'}


@app.post('/analizar')
def analizar_punto(solicitud: SolicitudAnalisis):
    _exigir_datos()
    try:
        return analizar(mes=solicitud.mes,zona=solicitud.zona,
                       guardar_resultado=False,mostrar_resumen=False)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (RuntimeError, OSError, KeyError) as exc:
        logger.exception('Falló análisis muestra')
        raise HTTPException(status_code=503,detail='Error en análisis; consulta logs.') from exc


@app.post('/analizar-parcela')
def analizar_parcela(solicitud: SolicitudParcela):
    # Primero validar geometría para responder 422 incluso cuando no haya datos locales.
    try:
        geom, hectares, interior = validate_parcel(geojson=solicitud.geojson,points=solicitud.puntos)
    except InvalidParcel as exc:
        raise HTTPException(status_code=422,detail=str(exc)) from exc
    _exigir_datos(False)
    try:
        catalog = json.loads(CATALOG.read_text(encoding='utf-8'))
        history = solicitud.historial
        from fieldshift.local_climate import point_climate
        if solicitud.manejo.previous_crop and solicitud.manejo.previous_crop not in {c['name'] for c in catalog}:
            raise HTTPException(status_code=422, detail='Cultivo anterior no reconocido.')
        return run_parcel_analysis(geom, hectares, interior, solicitud.mes, POWER, catalog, history,
                                   get_climate=point_climate, management=solicitud.manejo.model_dump())
    except (ValueError, RuntimeError, OSError, KeyError) as exc:
        logger.exception('Falló muestreo real de parcela')
        raise HTTPException(status_code=503, detail=(
            'No se pudo obtener el análisis real. Revisa los archivos NASA POWER, la conexión a '+
            'SoilGrids WCS y los logs. No se sustituyeron por datos simulados.')) from exc


@app.get('/catalogo')
def catalogo_cultivos():
    catalog = json.loads(CATALOG.read_text(encoding='utf-8'))
    return {'cultivos':[{'nombre':c['name'], 'familia':c['rotation']['family']} for c in catalog]}


@app.post('/capas/{capa}')
def capa_parcela(capa: str, solicitud: SolicitudParcela):
    from fieldshift.layers import get_layer
    if capa not in ('moisture', 'vegetation', 'soil', 'change', 'rainfall', 'evapotranspiration', 'carbon', 'cec'):
        raise HTTPException(status_code=422, detail='Capa no reconocida.')
    try:
        geom, _, _ = validate_parcel(geojson=solicitud.geojson, points=solicitud.puntos)
    except InvalidParcel as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        return get_layer(geom, capa, comparison_days=solicitud.comparison_days)
    except Exception as exc:
        logger.exception('No se pudo cargar el raster %s', capa)
        raise HTTPException(status_code=503, detail='Capa no disponible: ' + str(exc)[:350]) from exc


# Servicio único: localhost:8000/ muestra la web y los endpoints siguen disponibles.
app.mount('/', StaticFiles(directory=WEB_DIR, html=True), name='web')
