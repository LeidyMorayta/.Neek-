# NEEK / FieldShift Yucatán — Web integrada, mapa satelital y polígonos (V11)

**Fusiona el proyecto original del motor** (`FieldShift_Oracle_Listo.zip`) **con el dashboard original** (`el mero bueno 1.zip`) preservando la estética de neek'. Código listo para ejecutar; las descargas reales no venían en ninguno de los ZIP originales.

## Lo que ahora funciona

- **Mapa satelital** con Leaflet 1.9.4 y mosaicos World Imagery de Esri (se necesita Internet). El límite de Yucatán aparece sobre el mapa, con zoom al polígono cargado.
- Crear un polígono haciendo clic; cargar `Polygon` / `MultiPolygon` en **GeoJSON RFC 7946**; ingresar matriz de coordenadas en texto o JSON.
- Envía el polígono a **`POST /analizar-parcela`** mediante FastAPI; valida ubicación, cruces de aristas, área y orden de coordenadas `[longitud, latitud]`.
- Consulta **una muestra ISRIC SoilGrids WCS** en un punto interior de la parcela para obtener **pH y textura** superficiales (0–5 cm; resolución estimada ~250 m). Usa caché local de consultas para no repetirlas.
- Reutiliza el motor **V10** con NASA POWER histórico regional, FAO ECOCROP y recomendaciones de **8 cultivos y hasta 3 rotaciones**. La vista informa aptitud y confianza en datos por separado.
- Capas visibles: **Humedad del suelo, Salud de la planta y Calidad del suelo**. Se quitaron Calor y Zonas de helada **de la interfaz**; el motor V10 conserva sus reglas climáticas de estrés térmico para la aptitud. Las capas disponibles y su resolución se detallan al final de esta guía. El filtro de erosión se retiró.
- Interfaz ES / EN, letra adaptable, lectura por voz y diseño original conservados.

## Requisitos y ejecución local (CachyOS / fish)

> **Importante:** Si ya tienes datos reales en otro proyecto FieldShift, COPIA `data/` de ese proyecto a este sin perder la copia anterior. Este ZIP no contiene los CSV/JSON reales de `data/`, `.env` ni claves. El `results/puntos_suelo_yucatan.geojson` heredado del proyecto anterior es solo una referencia cartográfica; la API no lo usa como fuente de suelo.

```fish
cd /ruta/a/NEEK_Integrado
conda activate fieldshift
python -m pip install -r requirements.txt
python -m pytest -q

# Si no tienes el historial real, descárgalo (con Internet):
python main.py descargar
# Sólo para el endpoint de 7 puntos, además:
python main.py descargar-suelo

# Ejecutar la página y API juntas:
python -m uvicorn api:app --host 127.0.0.1 --port 8000
```

Abre **http://127.0.0.1:8000/**. `http://127.0.0.1:8000/docs` permite probar los endpoints; `GET /ready-parcela` requiere el CSV real de NASA POWER; `GET /ready` exige además las muestras descargadas de los 7 puntos. La página carga sin datos, pero avisará que falta NASA POWER cuando intentes analizar una parcela.

Si usas la **misma web en Oracle**, mantén `web/config.js` con `window.NEEK_API_BASE = ''` y entra al dominio que apunta al servidor. Si hospedas `web/` por separado, por ejemplo en **Porkbun Static Hosting**, configura en `web/config.js` la URL pública **HTTPS** de la API, y en Oracle define `FIELDSHIFT_ALLOWED_ORIGINS` con el origen de la web. No incluyas secretos en `config.js`.

## Cómo indicar una parcela

**Alternativa 1:** **Agregar parcela** → haz clic en al menos 3 vértices en la foto satelital → **Terminar parcela**.

**Alternativa 2:** **Subir GeoJSON** que tenga `Polygon`, `MultiPolygon` o un `Feature/FeatureCollection` con estas geometrías en WGS 84. El archivo se interpreta como una parcela delimitada, no como mapa de aptitud.

**Alternativa 3:** **Matriz de puntos** → escribe por línea `longitud, latitud` (por ejemplo `-89.62, 20.85`), o pega JSON:

```json
[
  [-89.62, 20.85],
  [-89.60, 20.85],
  [-89.60, 20.83],
  [-89.62, 20.83]
]
```

**También acepta** `[ {"longitud":-89.62,"latitud":20.85}, ...]` (objetos por vértice). No inviertas el orden `latitud,longitud` en las listas. La parcela debe estar en Yucatán, ser válida y tener entre 0.001 y 100,000 hectáreas. Se admiten 500 vértices aprox.

Selecciona el **mes de siembra**; el frontend envía automáticamente la petición al terminar de delimitar o importar la parcela. Se puede repetir con **Analizar esta parcela**. La descarga de SoilGrids por primera vez puede tardar y requiere Internet. La página mostrará un error explícito si falta un servicio; **no inventa resultados para simular éxito**.

## API de análisis de parcela

```http
POST /analizar-parcela
Content-Type: application/json
```

GeoJSON:

```json
{"mes":6,"geojson":{"type":"Polygon","coordinates":[[[-89.62,20.85],[-89.60,20.85],[-89.60,20.83],[-89.62,20.83],[-89.62,20.85]]]}}
```

O matriz:

```json
{"mes":6,"puntos":[[-89.62,20.85],[-89.60,20.85],[-89.60,20.83],[-89.62,20.83]]}
```

Ambas formas producen el mismo resultado científico; no es necesario incluir el primer punto repetido al final en la modalidad de matriz. El modelo responde con `parcela`, `suelo`, `clima`, `cultivos`, `rotaciones` y `advertencias`.

## Límites científicos importantes

1. La forma de la parcela es geográfica y **se valida**, pero **el clima NASA POWER sigue siendo la media regional de 7 muestras**; no se calculó un promedio de NASA POWER dentro del polígono.
2. **SoilGrids se consulta en un punto interior**, con información superficial de **0–5 cm**; no existe mapa de calidad integral del suelo ni evaluación de cada píxel. Los valores requieren revisión en campo.
3. El indicador **Calidad del suelo** muestra pH, textura y la falta de medidas necesarias. **No califica fertilidad global** ni calcula una puntuación inventada. Profundidad efectiva, nutrientes, carbono y compactación siguen pendientes.
4. Las superposiciones usan SMAP L4 (~9 km), Sentinel-2 NDVI (~10 m) y SoilGrids pH (~250 m). No cambian los puntajes del motor agrícola. La base Esri es una imagen para ubicación.
5. El análisis de parcela no usa el historial demostrativo compartido. Sin historial declarado, propone hasta dos alternativas sin inventar una rotación actual. La CLI conserva su configuración de historial.
6. El motor es **heurístico**, no una red neuronal entrenada ni un pronóstico. Las reglas internas de exposición a calor siguen presentes en V10 aunque retiramos esa *capa del dashboard*.
7. La gráfica 2015–2025 del dashboard original sigue marcada como **ilustrativa** y no se usa para polígonos reales.

## Fuentes y créditos

- Clima NASA POWER: https://power.larc.nasa.gov/docs/services/api/temporal/daily/
- ISRIC SoilGrids (WCS y licencia CC BY 4.0): https://docs.isric.org/globaldata/soilgrids/SoilGrids_faqs_02.html
- Base cartográfica World Imagery: Esri, Maxar, Earthstar Geographics y comunidad GIS: https://doc.arcgis.com/en/data-appliance/2025/maps/world-imagery.htm
- Leaflet: https://leafletjs.com/download
- GeoJSON RFC 7946: https://datatracker.ietf.org/doc/html/rfc7946
- FAO ECOCROP: catálogo y perfiles en `config/cultivos_demo.json` (cambios locales documentados).

Conserva las atribuciones de los proveedores visibles en el mapa y revisa las condiciones de uso y cuotas del proveedor de imágenes antes de publicar para un tráfico amplio. Ningún mosaico Esri se presenta como si fuera una imagen NASA.

## Capas raster de parcela

`POST /capas/{capa}` recibe el mismo GeoJSON o matriz que el análisis; no exige el CSV climático.

- `moisture`: imagen original NASA GIBS SMAP L4 de humedad volumétrica superficial, última fecha publicada. Es un análisis satélite/modelo a **9 km**, no detalle de parcela ni un raster numérico descargable; conserva leyenda NASA y se recorta al contorno.
- `vegetation`: NDVI por píxel de Sentinel-2 L2A, escenas recientes (180 días), calibración por metadatos/baseline, exclusión de nubes, sombras y agua con SCL. Resolución aproximada 10 m; se reduce para áreas extensas. No es diagnóstico de enfermedades.
- `soil`: pH estimado SoilGrids a ~250 m y 0–5 cm; no fertilidad integral. Las parcelas pequeñas pueden mostrar un solo píxel.
El filtro `erosion` se eliminó de la interfaz y del endpoint.

Las capas se solicitan al seleccionarlas, con caché temporal en memoria y botón de reintento ante fallos. No se rellenan nubes ni píxeles sin datos. El clima y la aptitud del motor agrícola conservan su alcance regional y puntual; las capas visuales no cambian esos puntajes.


## Flujo de trabajo por parcela

1. Crear/importar parcela y elegir mes de siembra. Se dispara el análisis automáticamente.
2. Consultar pH/textura del punto interior y evaluar el catálogo contra suelo e histórico climático regional.
3. Mostrar aptitud ordenada por estado y puntaje, con restricciones y confianza; no se usan tarjetas de ejemplo mientras carga o si falla.
4. Calcular alternativas de rotación con compatibilidad de cada ciclo, su fecha y puntaje. No se usa una rotación actual inventada. La API acepta `historial` opcional con `current_rotation`, `previous_crops` y `priorities`; si no existe, no calcula el cambio de familia respecto a un cultivo anterior desconocido.
5. Mostrar señales por parcela: pH/textura, lluvia histórica para el mes elegido, humedad SMAP fechada y media NDVI de píxeles válidos. La humedad y el NDVI se cargan automáticamente y muestran su estado de consulta.
6. Resumir cuatro observaciones: suelo y validación, cultivo mejor evaluado y manejo, rotación propuesta y verificación, profundidad pendiente. Cada observación muestra evidencia y acción.

Las parcelas con datos iguales pueden producir recomendaciones iguales. Una diferencia geográfica no garantiza una diferencia detectable a la resolución disponible. El mes y los resultados se conservan por parcela durante la sesión; no se persisten tras recargar el navegador.

## Contexto individual y nuevas capas

El endpoint de parcela consulta ahora NASA POWER en el punto interior de la parcela. La caché `data/cache_climate/` se distingue por coordenadas y periodo; no se sustituye una consulta fallida con el promedio estatal. La resolución original sigue siendo meteorológica (~0.5° × 0.625°), así que parcelas cercanas pueden compartir celda.

`manejo` acepta `water_system` (`sin_declarar`, `temporal`, `riego`), `previous_crop` (nombre del catálogo o null) y `priorities` (`soil_health`, `water_saving`, `pest_break`, enteros 1–5). La interfaz conserva estas opciones por parcela durante la sesión y recalcula tras cada cambio. Un cultivo anterior declarado excluye propuestas que empiecen con su misma familia. Temporal añade una penalización heurística explicada por demanda hídrica relativa. Declarar riego no agrega agua ficticia ni elimina restricciones de aptitud. El catálogo está disponible en `GET /catalogo`.

Nuevas capas de `POST /capas/{capa}`:

- `change`: NDVI reciente menos una observación anterior separada al menos `comparison_days` (30 por defecto; UI 30/60/90). Muestra ambas fechas y usa únicamente píxeles válidos en ambas escenas. Una disminución no prueba enfermedad ni sequía: puede corresponder a cosecha o cambio de etapa.
- `rainfall`: acumulado de los últimos 30 días disponibles de POWER en la ubicación, con fechas, cobertura y racha seca; no es lluvia medida por píxel de parcela ni un raster IMERG. Si falta un día no presenta un total completo.
- `evapotranspiration`: **ET₀ de referencia Hargreaves–Samani**, estimada con temperatura POWER y radiación extraterrestre por fecha/latitud. No es un producto ECOSTRESS ni evapotranspiración real del cultivo. Es contexto climático regional y no una dosis de riego. Se eligió esta implementación por no disponer de un producto de ET real accesible sin integrar acceso adicional a Earthdata.
- `carbon`: carbono orgánico SoilGrids superficial (g/kg), estimación ~250 m.
- `cec`: capacidad de intercambio catiónico SoilGrids superficial (cmol(c)/kg), estimación ~250 m. No determina disponibilidad de nutrientes ni fertilización.

Las capas de observación no modifican automáticamente los puntajes: las rotaciones dependen del suelo evaluado, clima histórico por ubicación, calendario, cultivo anterior y prioridades. Dos contextos equivalentes pueden tener las mismas propuestas. Las nuevas capas requieren conexión a sus proveedores; los errores muestran reintento sin generar datos artificiales.

ET₀: Hargreaves–Samani con conversión Ra de MJ/m²/día a mm equivalentes (0.408), sin calibración local; referencia FAO-56, ecuaciones 21–25 y 52. Ver https://www.fao.org/4/x0490e/x0490e00.htm
