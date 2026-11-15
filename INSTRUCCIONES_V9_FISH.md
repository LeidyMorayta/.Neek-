# FieldShift V9 — Aptitud y confianza por separado (fish)

## Instalación del parche en CachyOS

Desde el proyecto existente (con Conda `fieldshift` activo):

```fish
cd ~/Documentos/Hackathon/FieldShift_Yucatan_v4
unzip -o ~/Descargas/FieldShift_PARCHE_V8_a_V9.zip -d .
python -m pytest -q
```

## Uso (no hay que descargar los datos de nuevo)

```fish
python main.py analizar --mes 6 --punto YUC-05
python ver_resumen.py --mes 6
```

Repetir con `--punto YUC-06` para comparar los intervalos de INEGI.

## Interpretación

- **Aptitud** verde/amarillo/rojo: compatibilidad *preliminar* obtenida con los componentes evaluables. Las restricciones críticas documentadas se siguen aplicando. Un verde NO confirma que se pueda sembrar.
- **Confianza de datos** baja/media/alta: indicador cualitativo de procedencia y completitud de la evidencia, no probabilidad estadística ni exactitud demostrada.
- Sin profundidad real: se omite `depth` de la puntuación, se renormalizan los pesos y se conserva el aviso de medición pendiente. El color no se cambia por la mera ausencia de ese dato.
- Con intervalo INEGI: se muestra el riesgo de limitación por roca. **No** se convierte el intervalo cartográfico en profundidad medida.
- En este prototipo: sin profundidad ni intervalo cartográfico la confianza será **baja**; con intervalo INEGI interpretable, **media**. Una medición de profundidad en campo también permite **media**, pero `alta` exige además análisis local de pH/textura y clima local validado.
- Las tres rotaciones muestran la confianza más baja entre sus ciclos, y su clasificación no se confunde con esa confianza.

Salida JSON: `results/recomendaciones_yucatan_mes_06.json`. Los cultivos contienen `aptitud`, `estado`, `confianza_datos`, `factores_confianza`, `riesgos_historicos`, `profundidad_cartografica` y `componentes_no_evaluados`.

**No se han cambiado los datos descargados, el GeoJSON, los perfiles FAO ni los pesos numéricos.**
