"""Validación sin red de capturas V6 y exportaciones V7.

Extraer evidencias.zip en una carpeta y pasar su ruta como primer argumento.
Ejecutar desde la raíz: python docs/v7_integrada_2026-11-13/validar_evidencias.py RUTA
"""
import json
import math
from pathlib import Path
import sys
import zipfile
import datetime
import pandas as pd
from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from flujo_acciones import analysis_from_snapshot, tables_summary
from auditoria_io import clean


def equal_cell(actual, expected):
    if actual is None and expected in (None, ''):
        return True
    if isinstance(actual, (datetime.datetime, datetime.date)):
        # XLSX/openpyxl redondea las fechas a milisegundos.
        return abs(pd.Timestamp(actual) - pd.Timestamp(expected)) <= pd.Timedelta(milliseconds=1)
    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        return math.isclose(actual, expected, rel_tol=1e-10, abs_tol=1e-10)
    if isinstance(expected, (dict, list)):
        return actual == str(expected)
    return actual == expected


def exports(folder, prefix, inputs, results, excel):
    payload = json.loads((folder / inputs).read_text())
    exported = json.loads((folder / results).read_text())
    r, tables = analysis_from_snapshot(payload)
    replay = tables_summary('MSFT', tables)
    for key in ['Valoracion EPS PER', 'Proyeccion EPS', 'Supuestos EPS PER',
                'Control por metodo', 'Registro valoraciones']:
        assert len(exported[key]) == len(replay[key]), (prefix, key, 'filas replay diferentes')
        for old, new in zip(exported[key], replay[key]):
            assert old.keys() == new.keys()
            for column in old:
                assert equal_cell(old[column], new[column]), (prefix, key, column, 'replay diferente')
    wb = load_workbook(folder / excel, data_only=False)
    table_count = cell_count = 0
    for key, rows in exported.items():
        if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
            continue
        assert key[:31] in wb.sheetnames, (prefix, key, 'hoja ausente')
        sheet = wb[key[:31]]
        headers = [c.value for c in sheet[1]]
        assert headers == list(rows[0]), (prefix, key, 'columnas diferentes')
        assert sheet.max_row == len(rows) + 1, (prefix, key, 'filas diferentes')
        for i, row in enumerate(rows, start=2):
            for j, column in enumerate(headers, start=1):
                actual, expected = sheet.cell(i, j).value, row[column]
                assert equal_cell(actual, expected), (prefix, key, i, column, actual, expected)
                cell_count += 1
        table_count += 1
    if 'Grafico cotizacion' in exported:
        for target in exported['Valoracion EPS PER']:
            if target['Método'] != 'EPS × PER' or target['Precio objetivo'] is None:
                continue
            matches = [row for row in exported['Grafico cotizacion'] if
                       row['Serie'] == target['Escenario'] and
                       pd.Timestamp(row['Fecha']) == pd.Timestamp(target['Fecha objetivo'])]
            assert len(matches) == 1 and equal_cell(matches[0]['Precio'], target['Precio objetivo'])
    if prefix == 'manual':
        assert r.settings['scenarios']['Base']['pe'] == 20.
    return {'caso': prefix, 'tablas_excel_json': table_count, 'celdas': cell_count,
            'base_1y': r.summary['target_1y'], 'base_3y': r.summary['target_3y'],
            'objetivos': int(r.valuation['Precio objetivo'].notna().sum())}


def main(folder):
    comparisons = []
    keys = ['Valoracion EPS PER', 'Proyeccion EPS', 'Supuestos EPS PER',
            'Control por metodo', 'Diagnosticos', 'Disponibilidad metricas']
    for archive in sorted((ROOT / 'docs/economia_final_2026-11-12').glob('ejecuciones_*.zip')):
        with zipfile.ZipFile(archive) as z:
            for name in sorted(z.namelist()):
                if not name.endswith('_inputs.json'):
                    continue
                p = json.loads(z.read(name)); ticker = p['kwargs']['ticker']
                before = json.loads(z.read(name.replace('_inputs.json', '_resumen.json')))
                r, tables = analysis_from_snapshot(p); after = tables_summary(ticker, tables)
                for key in keys:
                    assert before[key] == after[key], (ticker, key, 'cambio automático inesperado')
                comparisons.append({'ticker': ticker, 'sin_cambio_financiero': True,
                                    'base_1y': r.summary['target_1y'], 'base_3y': r.summary['target_3y']})
    assert len(comparisons) == 13
    checks = [exports(folder / 'browser', prefix, prefix + '_inputs.json',
                      prefix + '_resultados.json', prefix + '_export.xlsx')
              for prefix in ['auto', 'manual']]
    live = folder / 'msft_actual'
    meta = json.loads((live / 'MSFT_resumen.json').read_text())
    checks.append(exports(live, 'msft_actual', 'MSFT_inputs.json', 'MSFT_resumen.json', meta['excel']))
    result = clean({'comparacion_13': comparisons, 'exportaciones': checks})
    (folder / 'consistencia_verificada.json').write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    print(json.dumps({'tickers_sin_cambio': len(comparisons), 'exportaciones': checks}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main(Path(sys.argv[1]))
