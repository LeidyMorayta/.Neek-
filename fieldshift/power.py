"""Descarga y lectura de la API diaria NASA POWER (datos reales, no generados)."""
import csv
from datetime import datetime, date
import json
from pathlib import Path
import requests

API = 'https://power.larc.nasa.gov/api/temporal/daily/point'
PARAMS = ('T2M', 'T2M_MIN', 'T2M_MAX', 'PRECTOTCORR', 'RH2M', 'ALLSKY_SFC_SW_DWN')
COLS = ('date',) + PARAMS


def power_to_rows(payload):
    try:
        p = payload['properties']['parameter']
        items = p['T2M']
    except (KeyError, TypeError) as exc:
        raise ValueError('NASA POWER devolvió un formato inesperado.') from exc
    rows = []
    for d in sorted(items):
        row = {'date': datetime.strptime(d, '%Y%m%d').date().isoformat()}
        for param in PARAMS:
            val = p.get(param, {}).get(d)
            try:
                num = float(val) if val is not None else None
                row[param] = num if num is not None and num > -900 else None
            except (ValueError, TypeError):
                row[param] = None
        rows.append(row)
    return rows


def fetch_power(lat, lon, start=2023, end=2025, start_date=None, end_date=None):
    first = start_date or date(start, 1, 1)
    last = end_date or date(end, 12, 31)
    if not date(1981,1,1) <= first <= last <= date.today():
        raise ValueError('Periodo NASA POWER inválido o con fechas futuras.')
    params = {'latitude': lat, 'longitude': lon, 'start': first.strftime('%Y%m%d'),
              'end': last.strftime('%Y%m%d'), 'community': 'AG', 'parameters': ','.join(PARAMS),
              'format': 'JSON', 'time-standard': 'LST'}
    try:
        response = requests.get(API, params=params, timeout=120, headers={'User-Agent': 'FieldShift-Hackathon/0.1'})
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise RuntimeError(f'No se pudo descargar NASA POWER: {exc}') from exc
    rows = power_to_rows(payload)
    if not rows:
        raise ValueError('NASA POWER no devolvió registros.')
    return rows


def save_csv(rows, path):
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open('w', newline='', encoding='utf-8') as fh:
        writer = csv.DictWriter(fh, fieldnames=COLS)
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path):
    rows = []
    with Path(path).open(newline='', encoding='utf-8') as fh:
        reader = csv.DictReader(fh)
        if not set(COLS).issubset(reader.fieldnames or []):
            raise ValueError('El CSV climático debe incluir date y los 6 parámetros NASA POWER.')
        for raw in reader:
            d = date.fromisoformat(raw['date'])
            row = {'date': d}
            for key in PARAMS:
                try:
                    val = float(raw[key])
                    row[key] = val if val > -900 else None
                except (ValueError, TypeError):
                    row[key] = None
            rows.append(row)
    rows.sort(key=lambda x: x['date'])
    if not rows:
        raise ValueError('Archivo climático vacío.')
    dates = [r['date'] for r in rows]
    if len(set(dates)) != len(dates):
        raise ValueError('El CSV climático contiene fechas duplicadas.')
    return rows
