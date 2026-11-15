# .Neek'

A web app that helps farmers in Yucatán, Mexico decide what to plant, when to plant it, and what to rotate it with. The farmer outlines a field on a satellite map and gets ranked crop recommendations, rotation plans, and satellite and climate layers for that exact field.

Built by **Leidy & Co.**

## What it does

- Draw a field on the map, upload a GeoJSON file, or paste coordinates.
- Ranked recommendations for 8 crops, with a traffic-light verdict and the limiting factors.
- Up to 3 multi-season rotation plans.
- Satellite and climate layers over the field: soil moisture (NASA SMAP), plant health (Sentinel-2 NDVI) and its change over time, 30-day rainfall, evapotranspiration, and soil pH, carbon and cation-exchange capacity.
- Bilingual interface (Spanish/English) with voice reading.

## Requirements

- Python 3.12
- An internet connection (the app downloads climate, soil and satellite data from public services)
- [Miniconda / Miniforge](https://github.com/conda-forge/miniforge) (recommended, because `rasterio` and `fiona` install most reliably with conda) or a standard Python virtual environment

## Installation

Clone the repository and enter the folder:

```bash
git clone https://github.com/LeidyMorayta/.Neek-.git
cd .Neek-
```

### Option A: conda (recommended)

```bash
conda env create -f environment.yml
conda activate fieldshift
```

### Option B: venv + pip

Linux / macOS:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Windows (PowerShell):

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Data

A snapshot of the climate and soil data is **already included** in the repository (`data/` and `results/`), so you can run the app right after installing. No download step is needed.

If you want fresher data, you can refresh it at any time (internet required). Existing data is not deleted:

```bash
# Extend the daily NASA POWER climate history up to the latest available date
python main.py descargar

# Refresh the ISRIC SoilGrids soil samples (7 points, used by the /analizar endpoint)
python main.py descargar-suelo
```

## Run the app

Start the API and the web page together:

```bash
python -m uvicorn api:app --host 127.0.0.1 --port 8000
```

Then open:

- App: http://127.0.0.1:8000/
- Interactive API docs: http://127.0.0.1:8000/docs

## How to use it

1. Click **Agregar parcela** and click at least 3 corners on the satellite map, then finish the field. Or upload a GeoJSON file, or paste coordinates.
2. Choose the planting month.
3. Read the crop recommendations, rotation plans and layers. The analysis reruns whenever you change the month or the field.

Coordinates use `[longitude, latitude]` order, for example:

```json
[
  [-89.62, 20.85],
  [-89.60, 20.85],
  [-89.60, 20.83],
  [-89.62, 20.83]
]
```

The field must be inside Yucatán, be a valid polygon, and be between 0.001 and 100,000 hectares.

## Command line

```bash
# Traffic-light, risks and comparison of three rotations for a sample point
python main.py analizar --mes 6 --punto YUC-01
```

`--mes` is the planting month (1 to 12) and `--punto` is a soil sample ID from `YUC-01` to `YUC-07`.

## Run the tests

```bash
python -m pytest -q
```

## API endpoints

| Method | Path | Description |
| --- | --- | --- |
| GET | `/health` | Basic health check |
| GET | `/ready` | Checks that all required data is available |
| GET | `/ready-parcela` | Checks the data needed for field analysis |
| GET | `/catalogo` | Crop catalog |
| POST | `/analizar-parcela` | Analyze a field (GeoJSON or coordinate array) |
| POST | `/capas/{capa}` | Satellite and climate layer for a field |

Example request:

```http
POST /analizar-parcela
Content-Type: application/json

{"mes": 6, "puntos": [[-89.62, 20.85], [-89.60, 20.85], [-89.60, 20.83], [-89.62, 20.83]]}
```

## Configuration

- `web/config.js` sets `window.NEEK_API_BASE`. Leave it as `''` when the site and API run on the same server. If you host `web/` separately, set it to the public HTTPS URL of the API.
- `FIELDSHIFT_ALLOWED_ORIGINS` (environment variable): comma-separated list of web origins allowed to call the API, needed only when the web page is hosted on a different domain.
- `METEOMATICS_USERNAME` and `METEOMATICS_PASSWORD` (optional): only needed to download the Meteomatics cross-check data.

Never commit secrets. `.env` files and keys are already in `.gitignore`.

## Deployment

The `deploy/` folder contains an example `systemd` service, an nginx configuration template and an environment file example for running the app on a Linux server (we used Oracle Cloud).

## Data sources

- [NASA POWER](https://power.larc.nasa.gov/docs/services/api/temporal/daily/): daily climate
- NASA GIBS SMAP L4: soil moisture
- Sentinel-2 L2A through Microsoft Planetary Computer: vegetation
- [ISRIC SoilGrids](https://docs.isric.org/globaldata/soilgrids/SoilGrids_faqs_02.html): soil properties (CC BY 4.0)
- FAO ECOCROP: crop requirements
- INEGI: soil maps
- Esri World Imagery: satellite basemap

## Limitations

- The recommendation engine is an explainable heuristic, not a yield forecast.
- Layer resolutions are limited: SMAP is about 9 km, soil data about 250 m, and Sentinel-2 about 10 m.
- Missing data is reported as missing; the app never invents values.
