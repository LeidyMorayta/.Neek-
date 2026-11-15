"""Descarga histórica Meteomatics y convierte a formato compatible con NASA POWER.

Es una fuente de contraste, NO reemplaza los datos NASA usados por el semáforo.
Los valores diarios se agregan para la jornada civil local de Yucatán (UTC-6).
La humedad relativa corresponde a una observación a las 00:00 locales, no media diaria.
"""
from __future__ import annotations

import csv
from datetime import date, datetime, timedelta, timezone
import os
from pathlib import Path

import requests

BASE_URL = 'https://api.meteomatics.com'
PARAMETER_MAP = {
    't_mean_2m_24h:C': 'T2M',
    't_min_2m_24h:C': 'T2M_MIN',
    't_max_2m_24h:C': 'T2M_MAX',
    'precip_24h:mm': 'PRECTOTCORR',
    'relative_humidity_2m:p': 'RH2M',
}
COLS = ('date', 'T2M', 'T2M_MIN', 'T2M_MAX', 'PRECTOTCORR', 'RH2M')


def build_url(lat: float, lon: float, year: int, first_day=None, last_day=None) -> str:
    """Consulta 24h terminadas a las 06Z; cada fila representa el día anterior.

    first_day y last_day son fechas locales INCLUSIVAS. La variante anual se
    conserva para compatibilidad con V9.
    """
    begin = first_day or date(year, 1, 1)
    finish = last_day or date(year, 12, 31)
    if not date(year,1,1) <= begin <= finish <= date(year,12,31):
        raise ValueError('Fechas Meteomatics fuera del año solicitado.')
    first = (begin+timedelta(days=1)).isoformat() + 'T06:00:00Z'
    last = (finish+timedelta(days=1)).isoformat() + 'T06:00:00Z'
    interval = f'{first}--{last}:P1D'
    parameters = ','.join(PARAMETER_MAP)
    return f'{BASE_URL}/{interval}/{parameters}/{lat:.6f},{lon:.6f}/json'


def parse_meteomatics_json(payload, expected_year=None):
    """Comprueba el formato por parámetro, coordenada y fecha, sin interpolar ausencias."""
    if not isinstance(payload, dict) or payload.get('status') not in (None, 'OK'):
        raise ValueError('Respuesta Meteomatics no válida o status distinto de OK.')
    mapped = {}
    for section in payload.get('data', []):
        name = section.get('parameter')
        if name not in PARAMETER_MAP:
            continue
        coords = section.get('coordinates', [])
        if not coords:
            continue
        if len(coords) != 1:
            raise ValueError('Se esperaba una única ubicación en la consulta Meteomatics.')
        for reading in coords[0].get('dates', []):
            try:
                instant = datetime.fromisoformat(reading['date'].replace('Z', '+00:00'))
                if instant.tzinfo is None:
                    raise ValueError('Una fecha Meteomatics carece de zona horaria.')
                # Los datos solicitados corresponden al día local que acaba de concluir.
                local_day = (instant.astimezone(timezone.utc) - timedelta(hours=6, days=1)).date()
                value = reading.get('value')
                value = float(value) if value is not None else None
                if value is not None and not (-1e5 < value < 1e6):
                    value = None
                if expected_year is not None and local_day.year != expected_year:
                    continue
                key = PARAMETER_MAP[name]
                row = mapped.setdefault(local_day, {'date': local_day.isoformat()})
                row[key] = value
            except (ValueError, KeyError, TypeError) as exc:
                raise ValueError('Lectura Meteomatics con fecha/valor inválidos.') from exc
    if not mapped:
        raise ValueError('No llegaron variables reconocidas de Meteomatics.')
    return [mapped[d] for d in sorted(mapped)]


def fetch_meteomatics(lat: float, lon: float, start=2023, end=2025, session=None,
                     first_day=None, last_day=None):
    username = os.environ.get('METEOMATICS_USERNAME', '').strip()
    password = os.environ.get('METEOMATICS_PASSWORD', '')
    if not username or not password:
        raise ValueError('Configura METEOMATICS_USERNAME y METEOMATICS_PASSWORD en tu entorno.')
    if not 2020 <= start <= end <= date.today().year:
        raise ValueError('Período Meteomatics inválido.')
    client = session or requests.Session()
    rows = []
    for year in range(start, end+1):
        year_first = max(date(year,1,1), first_day) if first_day else date(year,1,1)
        year_last = min(date(year,12,31), last_day) if last_day else date(year,12,31)
        if year_first > year_last:
            continue
        try:
            response = client.get(build_url(lat, lon, year, first_day=year_first, last_day=year_last),
                                  auth=(username, password), timeout=120)
            response.raise_for_status()
            rows.extend(parse_meteomatics_json(response.json(), expected_year=year))
        except requests.HTTPError as exc:
            # Evitar incluir en el error URL, cabeceras o credenciales.
            status = getattr(response, 'status_code', 'desconocido')
            raise RuntimeError(f'Meteomatics devolvió HTTP {status} en el año {year}; revisa permisos, cuotas y parámetros.') from exc
        except (requests.RequestException, ValueError) as exc:
            raise RuntimeError(f'Error de consulta Meteomatics para {year}: {type(exc).__name__}.') from exc
    if not rows:
        raise ValueError('Meteomatics no devolvió registros históricos.')
    return rows


def write_meteomatics_csv(rows, filepath):
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='', encoding='utf-8') as fp:
        writer = csv.DictWriter(fp, fieldnames=COLS)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, '') for key in COLS})
    return path


def read_meteomatics_csv(filepath):
    result = []
    with Path(filepath).open(newline='', encoding='utf-8') as fp:
        reader = csv.DictReader(fp)
        if not set(COLS).issubset(reader.fieldnames or []):
            raise ValueError('CSV Meteomatics inválido: requiere columnas '+', '.join(COLS))
        for record in reader:
            row = {'date': date.fromisoformat(record['date'])}
            for key in COLS[1:]:
                raw = record.get(key)
                row[key] = float(raw) if raw not in ('', None, 'None') else None
            row['ALLSKY_SFC_SW_DWN'] = None  # solar se calcula solo desde NASA POWER
            result.append(row)
    result.sort(key=lambda r: r['date'])
    if len({r['date'] for r in result}) != len(result):
        raise ValueError('CSV Meteomatics con fechas repetidas.')
    if not result:
        raise ValueError('CSV Meteomatics vacío.')
    return result
