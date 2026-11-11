# -*- coding: utf-8 -*-
"""Ejecución reproducible desde terminal, GitHub Actions o ChatGPT Codex/Work.

Ejemplo: python ejecutar_analisis.py --ticker MSFT --outdir Resultados
Genera Excel, resumen JSON, registro y código de salida no-cero si falla.
"""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile


def safe_records(df,max_rows=100):
    if df is None or df.empty:return []
    import pandas as pd
    values=df.head(max_rows).where(pd.notna(df.head(max_rows)),None)
    output=[]
    for row in values.to_dict('records'):
        clean={}
        for k,v in row.items():
            if v is None:clean[k]=None
            elif hasattr(v,'isoformat'):clean[k]=v.isoformat()
            elif hasattr(v,'item'):
                val=v.item()
                clean[k]=(val if not isinstance(val,float) or math.isfinite(val) else None) if isinstance(val,(str,int,float,bool,type(None))) else str(val)
            elif isinstance(v,float):clean[k]=v if math.isfinite(v) else None
            elif isinstance(v,(str,int,bool)):clean[k]=v
            else:clean[k]=str(v)
        output.append(clean)
    return output


def run(ticker,outdir,quarters,contact):
    import pandas as pd
    ticker=ticker.strip().upper()
    if not re.fullmatch(r'[A-Z0-9][A-Z0-9.\-^=]{0,24}',ticker):
        raise ValueError('Ticker Yahoo no válido')
    out=Path(outdir).resolve();out.mkdir(parents=True,exist_ok=True)
    env=os.environ.copy()
    env['VALUACION_TICKER']=ticker
    env['VALUACION_NUM_TRIMESTRES']=str(quarters)
    if contact:
        env['VALUACION_SEC_USER_AGENT']=f'StockValuationV5/1.0 (contact: {contact})'
    start=datetime.now(timezone.utc)
    name=re.sub(r'[^A-Za-z0-9._-]','_',ticker)
    with tempfile.TemporaryDirectory(prefix='valoracionV5_') as temp:
        cmd=[sys.executable,'-u',str(Path(__file__).resolve().with_name('valoracion_engine.py'))]
        p=subprocess.run(cmd,cwd=temp,env=env,capture_output=True,text=True,errors='replace',timeout=1500)
        (out/f'{name}_ejecucion.log').write_text(p.stdout+'\n--- STDERR ---\n'+p.stderr,encoding='utf-8')
        files=list(Path(temp).glob(f'valoracion_completa_{name}*.xlsx'))
        if p.returncode!=0 or not files:
            raise RuntimeError(f'Error motor ({p.returncode}); revisar {name}_ejecucion.log: '+(p.stderr or p.stdout)[-900:])
        src=max(files,key=lambda f:f.stat().st_mtime)
        excel=out/f'valoracion_{name}_{start:%Y%m%dT%H%M%SZ}.xlsx'
        excel.write_bytes(src.read_bytes())
    sheets=pd.read_excel(excel,sheet_name=None)
    summary={'schema_version':'v5.0','ticker':ticker,'generado_utc':start.isoformat(),
             'excel':excel.name,'fuente':'Yahoo Finance + SEC si está disponible'}
    keep={'General':60,'Control modelo':60,'Actualidad resultados':10,
          'Referencia comparables':10,'Comparables depurados':25,
          'Valoracion fundamental':40,'Base TTM y balance':40,
          'Supuestos fundamentales':90,'Resumen Yahoo SEC':25}
    for sheet,n in keep.items():
        if sheet in sheets: summary[sheet]=safe_records(sheets[sheet],n)
    summary['auditoria']={
        'comparables_elegibles':int(sheets['Comparables depurados']['Elegible'].sum())
            if 'Comparables depurados' in sheets and 'Elegible' in sheets['Comparables depurados'] else 0,
        'total_candidatos':len(sheets.get('Universo comparables',[])),
        'errores_bloqueantes':sum(x.get('Estado')=='BLOQUEO' for x in summary.get('Control modelo',[])),
    }
    (out/f'{name}_resumen.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    print('Excel:',excel)
    print('Resumen JSON:',out/f'{name}_resumen.json')
    print('Auditoría:',summary['auditoria'])
    return 0


def main():
    ap=argparse.ArgumentParser(description='Ejecuta y audita valoración V5')
    ap.add_argument('--ticker',required=True)
    ap.add_argument('--outdir',default='Resultados')
    ap.add_argument('--num-quarters',type=int,default=12)
    ap.add_argument('--sec-email',default=os.environ.get('SEC_CONTACT_EMAIL',''))
    args=ap.parse_args()
    if args.num_quarters<4 or args.num_quarters>24:
        ap.error('Selecciona de 4 a 24 trimestres')
    try:return run(args.ticker,args.outdir,args.num_quarters,args.sec_email)
    except Exception as e:
        print(f'FALLO: {type(e).__name__}: {e}',file=sys.stderr)
        return 1

if __name__=='__main__':sys.exit(main())
