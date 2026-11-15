# FieldShift Yucatán V8 — Profundidad INEGI (CachyOS / fish)

La V8 conserva NASA POWER, Meteomatics, Planetary Computer, SoilGrids, los ocho cultivos y las tres rotaciones. Solo añade un cruce con la **cartografía vectorial de edafología Serie II de INEGI**. No vuelve a descargar los archivos climáticos ni sustituye los datos de SoilGrids.

## 1. Actualizar el proyecto

Desde tu carpeta habitual de la V7:

```fish
cd ~/Documentos/Hackathon/FieldShift_Yucatan_v4
unzip -o ~/Descargas/FieldShift_PARCHE_V7_a_V8.zip -d .
python -m pip install -r requirements.txt
python -m pytest -q
```

## 2. Conseguir un único archivo de INEGI

1. Entra a la **ficha oficial del conjunto nacional de edafología Serie II**: https://www.inegi.org.mx/app/biblioteca/ficha.html?upc=794551131916
2. Descarga el **archivo vectorial SHP** del *Conjunto de datos vectorial edafológico, escala 1:250 000, Serie II, continuo nacional*.
3. Guarda su ZIP en `~/Descargas/` (por ejemplo, `edafologia_inegi.zip`). **No renombres archivos internos del ZIP.**
4. Si tu ZIP tiene otro nombre, utiliza ese nombre real al ejecutar el siguiente comando.

Esta descarga se hace **manualmente desde INEGI**. No incluimos esos datos en el ZIP de FieldShift y no fingimos haberlos obtenido. La cartografía es de escala 1:250 000; no equivale a una medición exacta de la parcela.

## 3. Importar la cartografía (un comando)

```fish
python main.py importar-edafologia --archivo ~/Descargas/edafologia_inegi.zip
```

El importador buscará el campo `Clave_WRB`, reproyectará los siete puntos y cruzará cada punto con un polígono de suelo. Genera:

`data/profundidad_inegi_yucatan.json`

Si los atributos del archivo muestran otro nombre para `Clave_WRB`, puedes especificarlo con `--campo NOMBRE`, previa verificación de que corresponde a la **clave edafológica**.

El resultado puede ser: **coincidencia_unica**, **sin_calificador_de_profundidad**, **sin_cobertura_en_cartografia** o **coincidencia_ambigua**. No se genera una profundidad numérica cuando no hay evidencia suficiente.

## 4. Analizar y ver el resumen

```fish
python main.py analizar --mes 6 --punto YUC-01
python ver_resumen.py --mes 6
```

Para otro punto cambia `YUC-01` por `YUC-02` hasta `YUC-07`.

Cada resultado muestra si la cartografía señala una posible limitante de profundidad. Los códigos que se interpretan en la **clave del suelo dominante** son:

- `li` (lítico): roca antes de 10 cm.
- `lep` (epiléptico): roca en 0–49 cm.
- `len` (endoléptico): roca entre 50 y 100 cm.

Estos valores **son intervalos cartográficos**, no profundidades reales de campo. Un resultado puede quedar amarillo por no contar con una medición. Nunca se habilita el verde solo por la cartografía. El rojo por clima/pH sigue siendo posible. La clase/textura superficial no permite por sí sola estimar profundidad.

## 5. Si cuentas con una medición real del terreno

El archivo `config/profundidad_campo.json` conserva prioridad sobre el mapa INEGI. Por ejemplo, **solo si se midieron realmente 42 cm en YUC-01**:

```json
{
  "mediciones": {
    "YUC-01": {"fuente": "medicion_campo", "depth_cm": 42}
  }
}
```

Si no hay medición, deja `"mediciones": {}`. **No inventes valores.**

## 6. Limitaciones importantes

- La Serie II tiene cartografía de referencia (no datos diarios de 2023–2025).
- Los polígonos de escala 1:250 000 describen un suelo dominante; puede haber otros suelos dentro del mismo polígono.
- INEGI no ofrece una profundidad precisa para cada punto mediante ese campo, solo calificadores de restricciones.
- SoilGrids continúa proporcionando estimaciones de pH y textura. La profundidad de suelo exacta sigue requiriendo comprobación de campo.
- Este programa **no incluye el SHP real**. Debes descargarlo desde INEGI para ejecutar la integración efectiva.

Referencia técnica INEGI: https://www.inegi.org.mx/contenidos/productos/prod_serv/contenidos/espanol/bvinegi/productos/nueva_estruc/702825231606.pdf
