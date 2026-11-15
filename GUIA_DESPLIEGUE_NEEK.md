# Actualización de despliegue NEEK

La guía `README_DESPLIEGUE_ORACLE.md` pertenece a la API V10 original. Para esta versión V11:

1. En la VM Oracle, preserva los CSV y JSON reales de `data/`, especialmente NASA POWER. Despliega el nuevo código y copia `web/` y `fieldshift/parcel.py`.
2. Usa el `api.py` V11 y el Nginx actualizado `deploy/nginx-fieldshift.conf.template` (aumenta tamaño de carga y timeout para SoilGrids).
3. Mantén `uvicorn api:app --host 127.0.0.1 --port 8000` bajo Systemd (1 worker es suficiente para la demo); reinicia `sudo systemctl restart fieldshift-api`.
4. En modo integrado la web aparece en `https://api.TUDOMINIO.com/`, usando el mismo servidor que la API. Comprueba `https://api.TUDOMINIO.com/health`.
5. Si la web se publica por separado: sube el contenido de `web/` a tu hosting estático, cambia **solo** `window.NEEK_API_BASE` a `https://api.TUDOMINIO.com` en `web/config.js`, añade su origen HTTPS a `FIELDSHIFT_ALLOWED_ORIGINS` en el servicio y reinicia.
6. Asegura conexión saliente de Oracle hacia `maps.isric.org` y que el navegador pueda cargar los mosaicos Esri y Leaflet. Ajusta el límite de solicitudes según uso y revisa licencias de terceros.
7. Para evitar posibles cargos, revisa la elegibilidad y límites del nivel gratuito de Oracle antes de activar nuevos recursos.

Consulta `README.md` para los endpoints y límites científicos.
