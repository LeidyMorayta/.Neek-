"""Vista compacta para revisar los resultados sin imprimir todo el JSON."""
import argparse
import json
from pathlib import Path


def main():
    parser=argparse.ArgumentParser(description='Resumen compacto FieldShift V10')
    parser.add_argument('--mes', type=int, default=6)
    args=parser.parse_args()
    if not 1 <= args.mes <= 12:
        parser.error('El mes debe estar entre 1 y 12.')
    file=Path('results')/f'recomendaciones_yucatan_mes_{args.mes:02d}.json'
    if not file.is_file():
        parser.error(f'Archivo no encontrado: {file}. Ejecuta primero main.py analizar.')
    data=json.loads(file.read_text(encoding='utf-8'))
    chosen=data.get('punto_seleccionado', 'no especificado')
    print(f"Punto de muestreo: {chosen} | mes: {args.mes:02d} | periodo climático: {data.get('periodo_clima','sin especificar')}")
    suelo=data.get('suelo_del_punto_seleccionado', {})
    print('Ciclos completos por cultivo:', {c['cultivo']:c.get('anios_utilizados',[]) for c in data['cultivos']})
    print('Profundidad INEGI (intervalo del suelo dominante):', suelo.get('depth_interval_cm') or 'no disponible', 'cm')
    print('Profundidad medida:', suelo.get('depth_cm') if suelo.get('depth_cm') is not None else 'pendiente')
    print('Cultivo                 Aptitud     Puntaje  Confianza  Riesgo profundidad')
    for crop in data['cultivos']:
        pending='pendiente' if crop.get('resultado_condicionado_por_datos_pendientes') else 'considerada'
        riesgo=(crop.get('profundidad_cartografica') or {}).get('riesgo') or pending
        print(f"{crop['cultivo']:<23} {crop['estado']:<11} {str(crop.get('puntaje_provisional','N/D')):<8} {crop.get('confianza_datos', 'N/D'):<10} {riesgo}")
    print('\nRotaciones del punto seleccionado:')
    for rotation in data['rotaciones']['estrategias']:
        print(f"- {rotation['tipo']}: {' -> '.join(rotation['cultivos'])} [aptitud={rotation['estado']}, confianza={rotation.get('confianza_datos', 'N/D')}]")
    print('\nVerde = aptitud preliminar, NO aprobación de siembra. Confianza = calidad cualitativa de datos, NO probabilidad.')
    print('Revisar advertencias de profundidad, pH, calor y lluvia en el JSON.')

if __name__ == '__main__':
    main()
