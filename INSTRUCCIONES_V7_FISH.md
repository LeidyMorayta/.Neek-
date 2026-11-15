# FieldShift Yucatán V7 — integración de suelos (fish / CachyOS)

## Qué cambió

**Una sola entrada geográfica:** `geojson/yucatan_estado.geojson`, igual que en V6.
Se agregaron siete puntos interiores de muestreo de **ISRIC SoilGrids**.
En cada punto se obtiene una predicción de pH, porcentaje de arena/limo/arcilla
(0–5 cm) y clase textural **simplificada**; no se inventa profundidad efectiva.

No se reemplazan tus archivos de clima de NASA POWER, Meteomatics ni Planetary Computer.
Tampoco se utiliza el suelo simulado de `config/suelo.json` al analizar.

## Pasos exactos

1. Abre la carpeta actual del proyecto (el nombre V4 sigue siendo correcto):

   ```fish
   cd ~/Documentos/Hackathon/FieldShift_Yucatan_v4
   ```

2. Haz una copia de seguridad de tu código y datos:

   ```fish
   cp -a . ../FieldShift_Yucatan_respaldo_antes_V7
   ```

3. Instala el parche y las dependencias en el entorno virtual de Python:

   ```fish
   unzip -o ~/Descargas/FieldShift_PARCHE_V6_a_V7.zip -d .
   python -m pip install -r requirements.txt
   python -m pytest -q
   ```

4. Descarga los datos estimados de suelo de siete puntos con el GeoJSON estatal:

   ```fish
   python main.py descargar-suelo
   ```

   Esta consulta **no** utiliza tu usuario/contraseña de Meteomatics.
   Se conecta al servicio WCS público de ISRIC. Los archivos quedan en:

   - `data/suelo_soilgrids_yucatan.json`: muestras y fuente.
   - `data/cache_soilgrids/`: pequeños GeoTIFF descargados y reutilizables.
   - `results/puntos_suelo_yucatan.geojson`: puntos para visualizar en mapa.

5. Ejecuta el semáforo para el punto `YUC-01` y siembra de junio:

   ```fish
   python main.py analizar --mes 6 --punto YUC-01
   ```

   Para otro punto ya descargado, por ejemplo:

   ```fish
   python main.py analizar --mes 6 --punto YUC-02
   ```

6. Consulta un resumen breve del resultado (sin imprimir todo el JSON):

   ```fish
   python ver_resumen.py --mes 6
   ```

7. Consulta todos los puntos y su pH estimado:

   ```fish
   python -c 'import json; d=json.load(open("data/suelo_soilgrids_yucatan.json")); [print(p["id"],p["ph"],p["texture"]) for p in d["muestras"]]'
   ```


8. Si usas Git, evita subir recortes GeoTIFF de SoilGrids:

   ```fish
   cat GITIGNORE_V7_ADICIONES.txt >> .gitignore
   ```

## Cuando tengas mediciones de profundidad

El modelo **no puede deducir la profundidad efectiva del suelo** a partir de
SoilGrids. Por seguridad, mientras `depth_cm` sea desconocido no mostrará
cultivos verdes. Si mides la profundidad efectiva hasta la roca en un punto,
regístrala en `config/profundidad_campo.json`:

```json
{
  "mediciones": {
    "YUC-01": {"depth_cm": 60, "fuente": "medicion_campo"}
  }
}
```

**60 cm es únicamente un ejemplo de estructura; no copies ese número sin medirlo.**
Deja `"mediciones": {}` si todavía no cuentas con mediciones.

## Advertencias de interpretación

- SoilGrids tiene resolución nominal ~250 m. Sus valores son **estimaciones**, no mediciones de parcela. ISRIC no recomienda utilizarlos directamente para diagnóstico a nivel de finca.
- Los puntos `YUC-01` a `YUC-07` **no forman polígonos de zona** ni abarcan toda la heterogeneidad de Yucatán.
- SoilGrids es un mapa estático; solo el clima usado por FieldShift corresponde a 2023–2025.
- El clima NASA POWER usado en las siete muestras sigue siendo el **promedio regional** que descargaste anteriormente. No representa el clima preciso de cada punto.
- Las clasificaciones y rotaciones continúan siendo **exploratorias**, sujetas a verificación agronómica. El historial `config/historial.json` es todavía demostrativo si no lo modificaste.
- Las pruebas locales usan datos sintéticos y **no prueban que el servidor WCS esté accesible** desde tu computadora. Si ISRIC no responde, se reporta un error, sin fabricar valores de suelo.

## Fuentes

- SoilGrids y restricciones: https://isric.org/explore/soilgrids
- Servicio WCS y ejemplos: https://docs.isric.org/globaldata/soilgrids/wcs.html
- Unidades SoilGrids: https://docs.isric.org/globaldata/soilgrids/SoilGrids_faqs_01.html
- INEGI Edafología Serie II (alternativa para futura validación): https://www.inegi.org.mx/app/biblioteca/ficha.html?upc=702825235789
