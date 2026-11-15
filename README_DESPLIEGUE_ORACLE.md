# FieldShift Yucatán V10 — despliegue en Oracle Cloud

Esta carpeta es una **copia preparada para desplegar**, no una API ya publicada.

**Arquitectura:** Porkbun Static Hosting (frontend) → `https://api.TUDOMINIO.com` (Nginx/HTTPS) → Uvicorn/FastAPI en `127.0.0.1:8000` (Oracle Ubuntu ARM64) → motor Python V10.

## Importante antes de comenzar

- El ZIP conserva el motor, configuración, tests y documentación, pero **NO incluye los datos reales** de `data/` (NASA POWER / SoilGrids) ni tus posibles credenciales. No existe un análisis real funcional hasta descargar/cargar ambos.
- En `config/historial.json` hay una **rotación demostrativa**, no el historial real de un agricultor.
- El análisis cubre **7 muestras** de Yucatán `YUC-01` a `YUC-07`, no coordenadas arbitrarias ni recomendaciones validadas por parcela.
- No cambies `config/suelo.json` para fingir que ya tienes SoilGrids; es un archivo legado.
- Usa **Ubuntu 24.04 ARM64** y la instancia **VM.Standard.A1.Flex** marcada como **Always Free elegible**, ajustada a los límites de tu cuenta. Oracle puede no tener capacidad A1 y puede reclamar instancias inactivas. Comprueba todos los recursos y su precio antes de crear.
- No subas contraseñas, llaves privadas SSH ni el archivo de configuración real `/etc/fieldshift/fieldshift.env` al repositorio o a Porkbun.

## 1. Validar localmente en Windows — PowerShell

Abre PowerShell en la carpeta donde descomprimiste **este** proyecto. No tienes que utilizar `.venv`: ya instalaste Conda.

```powershell
conda activate fieldshift
python --version
python -m pytest -q
python -m uvicorn api:app --host 127.0.0.1 --port 8000
```

Consulta `http://127.0.0.1:8000/health` o `http://127.0.0.1:8000/docs` en el navegador. Para detenerlo, pulsa `Ctrl+C`.

**Prueba de datos**: desde PowerShell ejecuta estas líneas en la carpeta raíz del proyecto:

```powershell
Get-ChildItem .\data\
python main.py descargar
python main.py descargar-suelo
python main.py analizar --mes 6 --punto YUC-06
```

Las descargas requieren Internet. Si ya tienes los CSV/JSON **reales** en otra copia de FieldShift, cópialos de `data/` a `data/` sin borrarlos ni sobrescribirlos a ciegas. Si hay errores por fuentes externas, comprueba primero si existen `data/power_yucatan_2020_2026.csv` (o `data/power_yucatan_2023_2025.csv`) y `data/suelo_soilgrids_yucatan.json`.

**Atención:** el punto `YUC-06` necesita existir entre las muestras SoilGrids descargadas. Los datos 2026 pueden estar parciales.

Para iniciar otra vez la API después de añadir datos:

```powershell
python -m uvicorn api:app --host 127.0.0.1 --port 8000
```

En `http://127.0.0.1:8000/docs`, prueba `GET /ready` (debe devolver `200`) y luego `POST /analizar` con:

```json
{"mes": 6, "zona": "YUC-06"}
```

Si `/ready` devuelve `503`, **faltan datos reales**; `/health` solo verifica que está vivo el proceso.

## 2. Crear VM Always Free en Oracle Cloud (navegador)

1. Entra en la [consola de Oracle Cloud](https://cloud.oracle.com/). Ve a Compute → Instances → Create instance.
2. Nombre sugerido: `fieldshift-api`. Imagen Ubuntu 24.04 (arquitectura **aarch64/ARM64**). Shape `VM.Standard.A1.Flex`, con configuración que muestre claramente Always Free; propuesta: **1 OCPU + 6 GB RAM** si está disponible dentro de la cuota, o 2 OCPU + 12 GB si tu cuenta lo permite. Boot volume ~50 GB dentro del almacenamiento gratuito.
3. Red pública con salida a Internet y **IPv4 pública**. Si creas VCN, utiliza subnet pública e Internet Gateway.
4. Genera o sube la **clave pública SSH** (no la privada). Guarda la clave privada de forma segura en tu PC. Si Oracle genera las llaves, descarga la privada al crear la instancia.
5. Revisa la pantalla final: **no aceptes servicios de pago ni discos adicionales fuera de Always Free**. Apunta la IPv4 pública.
6. En la lista de seguridad del subnet o Network Security Group, permite las entradas TCP **22 desde tu IP pública**, **80** y **443** desde Internet; **NO abras 8000**. Asegura las reglas de salida necesarias.

Si Oracle no tiene capacidad ARM, no selecciones otra VM pagada solo para continuar; primero revisa la elegibilidad/capacidad.

## 3. Conectarte por SSH — PowerShell de Windows

En PowerShell, comprueba:

```powershell
ssh -V
```

Si aún no creaste una clave SSH:

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\.ssh"
ssh-keygen -t ed25519 -f "$env:USERPROFILE\.ssh\oracle_fieldshift"
Get-Content "$env:USERPROFILE\.ssh\oracle_fieldshift.pub"
```

Copia el **texto de la clave pública** al crear la VM. No compartas el archivo sin `.pub`.

Tras crear la VM, reemplaza `TU_IP_PUBLICA` por su dirección:

```powershell
ssh -i "$env:USERPROFILE\.ssh\oracle_fieldshift" ubuntu@TU_IP_PUBLICA
```

Si Oracle te dio su propia clave privada, cambia la ruta del parámetro `-i` al archivo que descargaste.

## 4. Copiar el ZIP a Oracle — PowerShell de Windows

En una **segunda** ventana PowerShell, sitúate en la carpeta donde descargaste `FieldShift_Oracle_Listo.zip`:

```powershell
scp -i "$env:USERPROFILE\.ssh\oracle_fieldshift" ".\FieldShift_Oracle_Listo.zip" ubuntu@TU_IP_PUBLICA:/home/ubuntu/
```

En la **sesión SSH de Ubuntu** (los comandos a partir de aquí son **Linux, NO PowerShell**):

```bash
sudo apt-get update
sudo apt-get install -y unzip
cd /home/ubuntu
unzip FieldShift_Oracle_Listo.zip
mv FieldShift_Oracle_Listo fieldshift
cd /home/ubuntu/fieldshift
ls
```

No ejecutes `mv` si ya existe `/home/ubuntu/fieldshift` de un despliegue anterior; en ese caso actualiza la carpeta cuidadosamente y preserva `data/`.

## 5. Instalar dependencias y comprobar tests — SSH Ubuntu

Dentro de `/home/ubuntu/fieldshift`, ejecuta:

```bash
bash deploy/instalar_dependencias_oracle.sh
```

El script instala Nginx/Certbot, Miniforge **para ARM64**, un entorno Conda Python 3.12 y ejecuta el conjunto de pruebas. **No borra tus datos** y no publica el servicio todavía.

Si falla algún paquete de Conda, conserva el error exacto para revisar versiones/compatibilidad ARM. No cambies dependencias geoespaciales aleatoriamente.

## 6. Incorporar datos reales — Ubuntu y/o Windows

Revisa los archivos necesarios:

```bash
ls -lh /home/ubuntu/fieldshift/data/
```

### Opción A (preferida si ya descargaste en Windows)

Desde **PowerShell de Windows**, copia tu carpeta local `data` completa a la carpeta `fieldshift` de Oracle. Ajusta la ruta local a la **carpeta del proyecto que contiene tus datos reales**:

```powershell
scp -i "$env:USERPROFILE\.ssh\oracle_fieldshift" -r "C:\RUTA\A\TU\FIELDShift\data" ubuntu@TU_IP_PUBLICA:/home/ubuntu/fieldshift/
```

Comprueba que los CSV/JSON quedaron directamente en `/home/ubuntu/fieldshift/data/`, no en `data/data/`.

### Opción B (si todavía no tienes datos)

En **Ubuntu por SSH**:

```bash
cd /home/ubuntu/fieldshift
/home/ubuntu/miniforge3/envs/fieldshift/bin/python main.py descargar
/home/ubuntu/miniforge3/envs/fieldshift/bin/python main.py descargar-suelo
```

NASA POWER y SoilGrids requieren disponibilidad externa; Meteomatics solo se consulta con credenciales y NDVI puede ser complementario. **No se rellenan datos faltantes con valores fabricados.** Si fallan descargas, revisa la salida antes de seguir.

### Comprobación real del motor

```bash
cd /home/ubuntu/fieldshift
/home/ubuntu/miniforge3/envs/fieldshift/bin/python main.py analizar --mes 6 --punto YUC-06
```

Si se genera `results/recomendaciones_yucatan_mes_06.json` y el resumen corresponde a datos reales, ya puedes iniciar la API.

## 7. Registrar servicio Systemd — SSH Ubuntu

```bash
sudo mkdir -p /etc/fieldshift
sudo cp deploy/fieldshift-api.service /etc/systemd/system/fieldshift-api.service
sudo systemctl daemon-reload
sudo systemctl enable --now fieldshift-api
sudo systemctl status fieldshift-api --no-pager
```

Prueba desde la misma VM:

```bash
curl -i http://127.0.0.1:8000/health
curl -i http://127.0.0.1:8000/ready
```

Ambos deben devolver `200 OK`. Si `/ready` da `503`, faltan datos o la API se inició antes de copiarlos. Comprueba datos y reinicia el servicio:

```bash
sudo systemctl restart fieldshift-api
sudo journalctl -u fieldshift-api -n 60 --no-pager
```

## 8. Activar Nginx y HTTPS — Porkbun y SSH Ubuntu

En **Porkbun → DNS**, añade o edita SOLO este registro de tu dominio:

| Tipo | Host | Respuesta |
| --- | --- | --- |
| A | `api` | `TU_IP_PUBLICA` |

No reemplaces los registros `@` o `www` del frontend en Porkbun Static Hosting.

En **Ubuntu SSH**, define tu dominio base (sin `https://` ni `api.`):

```bash
DOMINIO="tudominio.com"
sed "s/api.TUDOMINIO.com/api.$DOMINIO/g" deploy/nginx-fieldshift.conf.template | sudo tee /etc/nginx/sites-available/fieldshift-api > /dev/null
sudo ln -s /etc/nginx/sites-available/fieldshift-api /etc/nginx/sites-enabled/fieldshift-api
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx
```

Cuando el DNS `api.tudominio.com` apunte a tu VM, obtén TLS de Let's Encrypt:

```bash
sudo certbot --nginx -d "api.$DOMINIO" --redirect
sudo certbot renew --dry-run
```

Si Certbot falla por DNS o por puertos 80/443, verifica las reglas de entrada en **Oracle VCN/NSG** y el firewall de Ubuntu. Nginx comunica internamente con Uvicorn; **no abras TCP 8000 al público**.

Verifica desde tu computadora:

```powershell
Invoke-RestMethod "https://api.tudominio.com/health"
Invoke-RestMethod "https://api.tudominio.com/ready"
$datos = @{mes=6; zona="YUC-06"} | ConvertTo-Json
Invoke-RestMethod -Uri "https://api.tudominio.com/analizar" -Method Post -ContentType "application/json" -Body $datos
```

## 9. Permitir el dominio de Porkbun en CORS — Ubuntu SSH

Es obligatorio para que la web (otro origen) pueda llamar a FastAPI desde el navegador.

```bash
sudo mkdir -p /etc/fieldshift
printf 'FIELDSHIFT_ALLOWED_ORIGINS=https://%s,https://www.%s\n' "$DOMINIO" "$DOMINIO" | sudo tee /etc/fieldshift/fieldshift.env > /dev/null
sudo chmod 600 /etc/fieldshift/fieldshift.env
sudo systemctl restart fieldshift-api
```

El archivo `deploy/fieldshift.env.example` es **solo una plantilla**: no pongas secretos allí. Si el frontend está servido en otro subdominio o puerto, incluye el **origen real exacto**.

En el código del frontend:

```javascript
const API_URL = "https://api.tudominio.com";
const respuesta = await fetch(`${API_URL}/analizar`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ mes: 6, zona: "YUC-06" }),
});
if (!respuesta.ok) throw new Error(`API: ${respuesta.status}`);
const resultado = await respuesta.json();
console.log(resultado.cultivos, resultado.rotaciones);
```

**CORS no es autenticación**: no ocultes claves en el JavaScript público. Nginx impone un límite básico de solicitudes; si el prototipo pasa a producción institucional se necesitarán controles adicionales (identidad, registros, supervisión, límites de concurrencia y pruebas de carga).

## 10. Verificación final / problemas comunes

- `[ ]` `python -m pytest -q` termina sin fallos en Windows y Ubuntu
- `[ ]` `python main.py analizar --mes 6 --punto YUC-06` usa archivos reales
- `[ ]` `GET /health` = 200 (`proceso` funcionando)
- `[ ]` `GET /ready` = 200 (`clima` y `suelo` presentes)
- `[ ]` `POST /analizar` devuelve el JSON del modelo (no de tests)
- `[ ]` `sudo systemctl status fieldshift-api` está activo y reinicia después de reboot
- `[ ]` `https://api.tudominio.com/docs` abre bajo HTTPS válido
- `[ ]` `fetch()` desde el dominio real de Porkbun funciona sin error CORS
- `[ ]` Solo puertos 22 (acceso restringido), 80 y 443 tienen entrada habilitada desde las fuentes previstas
- `[ ]` Ninguna credencial o llave privada está en la web, ZIP público o repositorio

Para revisar errores por SSH:

```bash
sudo journalctl -u fieldshift-api -n 100 --no-pager
sudo nginx -t
sudo tail -n 100 /var/log/nginx/error.log
```

**Conservación de datos:** el ZIP del código no es un backup de las descargas; conserva copias de `data/` y verifica permisos antes de reiniciar servicios. Si la IP pública cambia, actualiza el registro DNS. Oracle Always Free no garantiza disponibilidad empresarial 24/7.
