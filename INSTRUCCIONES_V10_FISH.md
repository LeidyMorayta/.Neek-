# FieldShift Yucatán V10 — historial 2020–2026 (fish / CachyOS)

**Objetivo:** usar seis años completos (2020–2025) y los ciclos que ya hayan terminado en 2026. No entrena una red neuronal: aplica el modelo de aptitud/rotación a temporadas históricas válidas.

## 1. Actualizar la instalación que ya tienes

Ejecuta en **fish**:

```fish
cd ~/Documentos/Hackathon/FieldShift_Yucatan_v4
conda activate fieldshift
unzip -o ~/Descargas/FieldShift_PARCHE_V9_a_V10.zip -d .
python -m pytest -q
```

No borres `data/`, `config/` ni `results/`. El parche **no contiene esas carpetas** y conserva tus archivos descargados de NASA POWER, Meteomatics, SoilGrids e INEGI, así como el historial y la configuración.

## 2. Obtener el historial faltante

Comprueba que sigan disponibles las variables de Meteomatics en esta misma terminal. No imprimas tu contraseña:

```fish
python -c 'import os; print({k:bool(os.getenv(k)) for k in ("METEOMATICS_USERNAME", "METEOMATICS_PASSWORD")})'
```

Si aparecen `False`, configura nuevamente las credenciales:

```fish
set -gx METEOMATICS_USERNAME "TU_USUARIO"
read --silent --prompt-str "Contraseña Meteomatics: " METEOMATICS_PASSWORD
set -gx METEOMATICS_PASSWORD $METEOMATICS_PASSWORD
```

Descarga y combina:

```fish
python main.py descargar
```

Se crearán, según disponibilidad:

- `data/power_yucatan_2020_2026.csv` — fuente principal, unión por fecha con el 2023–2025 original.
- `data/meteomatics_yucatan_2020_2026.csv` — contraste climático puntual.
- `data/ndvi_muestra_yucatan_2020_2026.json` — muestra de imágenes Sentinel-2, no promedio estatal.
- `data/estado_descargas_2020_2026.json` — estados y posibles errores por proveedor.

Solo se solicitan periodos que falten. Si algún proveedor falla, el JSON lo indicará como `parcial`. No se inventan fechas ni se borra lo que ya tengas. **No necesitas repetir `descargar-suelo` ni `importar-edafologia`.**

**Corte de datos 2026:** NASA POWER consulta hasta 10 días antes de la fecha actual (margen conservador por retraso de productos solares); Meteomatics hasta 2 días antes. No se confunden estas observaciones con un pronóstico. El NDVI se consulta como muestra de junio–agosto, cuando esas fechas ya están disponibles.

## 3. Analizar y verificar

```fish
python main.py analizar --mes 6 --punto YUC-06
python ver_resumen.py --mes 6
```

Para verificar qué años efectivamente evaluó el maíz:

```fish
python -c 'import json; d=json.load(open("results/recomendaciones_yucatan_mes_06.json")); c=next(x for x in d["cultivos"] if x["cultivo"]=="Maíz"); print("Años usados:",c["anios_utilizados"]); print("Años excluidos:",c["anios_descartados"])'
```

En noviembre de 2026, el ciclo de maíz iniciado en junio (aprox. 120 días) **podría** incluir 2026, siempre que NASA POWER haya devuelto registros suficientes. Uno iniciado cerca de noviembre debe excluirse hasta que termine.

## 4. Si aparecen datos incompletos

- Revisa `data/estado_descargas_2020_2026.json`. Una fuente puede devolver errores de cuota, permisos o retrasos en publicación.
- Puedes volver a ejecutar `python main.py descargar`: el sistema conserva los datos previos y descarga solamente los rangos pendientes.
- Si no se completó 2026, el análisis seguirá utilizando los años completos disponibles y mostrará `anios_descartados`.
- El semáforo y la confianza **siguen siendo estimaciones preliminares**, no una recomendación agrícola validada para una parcela específica.

## Archivos principales modificados

`main.py` (flujo), `fieldshift/refresh.py` (nuevas descargas incrementales), `fieldshift/history.py` (unión y rangos), `fieldshift/power.py`, `regional.py`, `meteomatics.py`, `planetary.py` (consultas 2020–2026), `fieldshift/climate.py` (años automáticos y exclusión de ciclos incompletos), `ver_resumen.py` (etiqueta temporal). El motor agrícola, las rotaciones y los datos del suelo permanecen con su lógica V9.
