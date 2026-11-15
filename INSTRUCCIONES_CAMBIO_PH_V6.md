# FieldShift Yucatán V6 — actualización local del pH del chile habanero

## Qué cambia

- Se conservan **sin modificar** los rangos de FAO ECOCROP: pH óptimo 6.0–6.5 y pH absoluto 5.3–7.0 para *Capsicum chinense*.
- Un pH **mayor que 7.0 y hasta 7.7**, en el contexto del prototipo de Yucatán, activa una **advertencia local** en vez de rojo automático **únicamente para chile habanero**. El límite superior 7.7 procede del pH máximo documentado en suelos donde se cultiva habanero en Yucatán, NO de un ensayo de tolerancia. **No es un nuevo rango óptimo**.
- El puntaje de pH según FAO **permanece en 0** cuando se supera 7.0; el puntaje global sigue incluyendo calor, lluvia, sequía, etc. La excepción **nunca produce verde automáticamente** y otras restricciones críticas siguen provocando rojo.
- El resultado JSON registra `pH_evaluacion`, `advertencias_locales` y las recomendaciones de diagnóstico de suelo. También incluye referencias de evidencia local y de FAO.
- Los otros siete cultivos no se modifican.

## Instalar el parche en fish, sin perder descargas ni configuración

Ejecuta desde la terminal en tu sistema CachyOS:

```fish
cd ~/Documentos/Hackathon/FieldShift_Yucatan_v4
cp fieldshift/engine.py fieldshift/engine.py.bak
cp config/cultivos_demo.json config/cultivos_demo.json.bak
cp main.py main.py.bak
unzip -o ~/Descargas/FieldShift_PARCHE_V5_a_V6.zip -d .
python -m pytest -q
python main.py analizar --mes 6
```

No elimines `data/`, `config/suelo.json` ni `config/historial.json`. No hace falta volver a ejecutar `descargar`.

## Consultar solo el chile habanero

```fish
python -c 'import json; d=json.load(open("results/recomendaciones_yucatan_mes_06.json")); c=next(x for x in d["cultivos"] if x["cultivo"]=="Chile habanero"); print(json.dumps({k:c[k] for k in ("estado","puntaje_provisional","pH_evaluacion","advertencias_locales","restricciones_criticas")},ensure_ascii=False,indent=2))'
```

**Precaución:** si `config/suelo.json` utiliza `"source": "SIMULACION"`, las clasificaciones son solo una prueba informática. No inferir aptitud real para una parcela con suelos no medidos.

## Referencias

- FAO ECOCROP, ficha *Capsicum chinense*: https://ecocrop.apps.fao.org/ecocrop/srv/en/dataSheet?id=4178
- Estudio de suelos con habanero en Yucatán (Agrociencia, 2014): https://www.scielo.org.mx/scielo.php?pid=S1405-31952014000400001&script=sci_arttext
