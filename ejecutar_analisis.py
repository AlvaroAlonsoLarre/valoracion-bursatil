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
    env['VALUACION_SNAPSHOT_DIR']=str(out)
    if contact:
        env['VALUACION_SEC_USER_AGENT']=f'StockValuationV5/1.0 (contact: {contact})'
    start=datetime.now(timezone.utc)
    name=re.sub(r'[^A-Za-z0-9._-]','_',ticker)
    with tempfile.TemporaryDirectory(prefix='valoracionV5_') as temp:
        cmd=[sys.executable,'-u',str(Path(__file__).resolve().with_name('valoracion_engine.py'))]
        try:
            p=subprocess.run(cmd,cwd=temp,env=env,capture_output=True,text=True,errors='replace',timeout=1500)
        except subprocess.TimeoutExpired as exc:
            (out/f'{name}_ejecucion.log').write_text('Timeout motor; '+str(exc),encoding='utf-8')
            return save_failure(ticker,out,'Tiempo máximo del motor excedido',start)
        (out/f'{name}_ejecucion.log').write_text(p.stdout+'\n--- STDERR ---\n'+p.stderr,encoding='utf-8')
        files=list(Path(temp).glob(f'valoracion_completa_{name}*.xlsx'))
        if p.returncode!=0 or not files:
            return save_failure(ticker,out,f'Error motor ({p.returncode}); consultar {name}_ejecucion.log',start)
        src=max(files,key=lambda f:f.stat().st_mtime)
        excel=out/f'valoracion_{name}_{start:%Y%m%dT%H%M%SZ}.xlsx'
        excel.write_bytes(src.read_bytes())
    sheets=pd.read_excel(excel,sheet_name=None)
    return save_summary(ticker,out,excel,sheets,start)


def save_failure(ticker,out,message,start):
    from auditoria_io import provenance
    payload={'schema_version':'v7.0','ticker':ticker,'generado_utc':start.isoformat(),
        'provenance':provenance(),'estado_tecnico':'ERROR','detail':message,
        'auditoria':{'estado_financiero':'BLOQUEO','publicable':False,'exit_code':1}}
    (out/f'{ticker}_resumen.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2))
    print(message,file=sys.stderr)
    return 1


def save_summary(ticker,out,excel,sheets,start):
    import pandas as pd
    from auditoria_io import assess,provenance
    summary={'schema_version':'v7.0','ticker':ticker,'generado_utc':start.isoformat(),
        'excel':excel.name,'fuente':'Yahoo Finance + SEC/IR con cobertura explícita',
        'provenance':provenance(),'estado_tecnico':'COMPLETADO'}
    keep=['General','Control modelo','Actualidad resultados','Referencia comparables',
          'Comparables depurados','Universo comparables','Comparables requisitos','Fuentes comparables','Revision filings','Componentes CAPEX DA','DCF sensibilidad','DCF validacion','Valoracion fundamental','Base TTM y balance',
          'Supuestos fundamentales','Resumen Yahoo SEC','Registro valoraciones','Escenarios EPS PER',
          'Escenarios FCF','Estadisticas crecimiento','Parametros riesgo','ROIC TTM capital medio','Fuentes fundamentales','Conciliacion TTM','Pendientes fundamentales','Contraste IR','Extraordinarios IR']
    for sheet in keep:
        if sheet in sheets:summary[sheet]=safe_records(sheets[sheet],len(sheets[sheet]))
    summary['auditoria']=assess(sheets)
    peers=sheets.get('Comparables depurados')
    summary['auditoria']['comparables_elegibles']=int(peers['Elegible'].fillna(False).sum()) if peers is not None and 'Elegible' in peers else 0
    summary['auditoria']['total_candidatos']=len(sheets.get('Universo comparables',[]))
    definitions=sheets.get('Comparables requisitos',pd.DataFrame())
    for method,key in [('PER','definiciones_per_completas'),('EV/EBITDA','definiciones_ev_ebitda_completas')]:
        summary['auditoria'][key]=int((definitions['Método'].eq(method)&definitions['Definición completa'].eq(True)).sum()) if 'Método' in definitions else 0
    snapshot=out/f'{ticker}_inputs.json'
    if snapshot.exists():
        import hashlib
        summary['input_sha256']=hashlib.sha256(snapshot.read_bytes()).hexdigest()
    (out/f'{ticker}_resumen.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    print('Excel:',excel)
    print('Resumen JSON:',out/f'{ticker}_resumen.json')
    print('Auditoría:',summary['auditoria'])
    return summary['auditoria']['exit_code']


def replay(snapshot,outdir):
    """Reproduce un snapshot propio en JSON; no consulta red ni evalúa código."""
    import pandas as pd
    from auditoria_io import read_snapshot,restore_frame,valuation_registry
    from modelo_fundamental import build_fundamental_model
    annual,peers,kwargs,payload=read_snapshot(snapshot)
    if kwargs.get('share_schedule'):kwargs['share_schedule']={int(k):v for k,v in kwargs['share_schedule'].items()}
    # Sólo parámetros consumidos por el modelo; el snapshot no modifica rutas, UA ni credenciales.
    allowed=['TIPO_LIBRE_RIESGO','PRIMA_RIESGO_MERCADO','RIESGO_PAIS','WACC','BETA','COSTE_DEUDA',
      'PARAMETROS_MONEDA','ERP_INCLUYE_PAIS','TASA_IMPOSITIVA','CRECIMIENTO_VENTAS',
      'VAR_CAPITAL_TRABAJO_PCT','CRECIMIENTO_ACCIONES','PAGOS_ACCIONISTAS_SOBRE_VENTAS',
      'CRECIMIENTO_TERMINAL','EMPRESA_CICLICA','MARGEN_NORMALIZADO','COMPARABLES','MODO_COMPARABLES']
    keys={'VALUACION_'+key for key in allowed}
    for key in ['TIPO_LIBRE_RIESGO','PRIMA_RIESGO_MERCADO','BETA','COSTE_DEUDA']:
        keys.update('VALUACION_'+key+suffix for suffix in ['_FECHA','_FUENTE','_CADUCIDAD'])
    previous={k:os.environ.get(k) for k in keys}
    try:
        for key in keys:
            value=payload.get('assumption_environment',{}).get(key)
            if value is None:os.environ.pop(key,None)
            else:os.environ[key]=value
        result=build_fundamental_model(annual,peers,**kwargs)
        from dcf_audit import audit_dcf
        sensitivity,validation=audit_dcf(annual,peers,kwargs,result)
    finally:
        for key,value in previous.items():
            if value is None:os.environ.pop(key,None)
            else:os.environ[key]=value
    ticker=kwargs['ticker'];out=Path(outdir).resolve();out.mkdir(parents=True,exist_ok=True)
    historical={k:restore_frame(v) for k,v in payload.get('historical',{}).items()}
    eps=historical.get('Escenarios EPS PER',pd.DataFrame());fcf=historical.get('Escenarios FCF',pd.DataFrame())
    registry=valuation_registry(result.valuation,eps,fcf,as_of=kwargs['as_of'],fy_date=kwargs['fiscal_end_date'],
        ttm_date=result.assumptions.set_index('Supuesto').loc['Fecha base TTM','Valor'],currency=kwargs['quote_currency'],
        source=kwargs.get('source','N/D'),freshness=(kwargs.get('recent_results_check') or {}).get('status','NO_VERIFICADO'))
    sheets={'Registro valoraciones':registry,'Valoracion fundamental':result.valuation,'Control modelo':result.checks,
      'Base TTM y balance':result.base_ttm,'Proyeccion negocio':result.projected,'DCF detalle':result.dcf_detail,
      'Supuestos fundamentales':result.assumptions,'Comparables depurados':result.peers,
      'Universo comparables':result.peer_universe,'Referencia comparables':result.peer_reference,
      'Parametros riesgo':result.risk_parameters,'ROIC TTM capital medio':result.roic_ttm,'Comparables requisitos':result.peer_definitions,'Escenarios EPS PER':eps,'Escenarios FCF':fcf}
    sheets['Fuentes comparables']=pd.DataFrame(payload.get('evidence',{}).get('peer_sources',[]))
    from filing_review import components_reconciliation
    sheets['DCF sensibilidad'],sheets['DCF validacion']=sensitivity,validation
    sheets['Revision filings']=pd.DataFrame(payload.get('evidence',{}).get('filing_review',[]))
    sheets['Componentes CAPEX DA']=components_reconciliation(kwargs.get('quarterly'))
    evidence=payload.get('evidence',{}).get('ir',{})
    fundamentals=payload.get('evidence',{}).get('official_fundamentals',{})
    sheets['Fuentes fundamentales']=pd.DataFrame(fundamentals.get('changes',[])).drop(columns=['Componentes'],errors='ignore')
    from fuentes_fundamentales import ttm_reconciliation
    sheets['Conciliacion TTM']=ttm_reconciliation(kwargs['quarterly'],annual,kwargs['as_of'],kwargs['fiscal_end_date'])
    sheets['Pendientes fundamentales']=pd.DataFrame({'Incidencia':fundamentals.get('issues',[])})
    sheets['Contraste IR']=pd.DataFrame(evidence.get('comparisons',[]))
    sheets['Extraordinarios IR']=pd.DataFrame(evidence.get('extraordinary',[]))
    excel=out/f'valoracion_{ticker}_replay.xlsx'
    with pd.ExcelWriter(excel,engine='openpyxl') as writer:
        for name,table in sheets.items():table.to_excel(writer,sheet_name=name,index=False)
    (out/f'{ticker}_inputs.json').write_bytes(Path(snapshot).read_bytes())
    (out/f'{ticker}_ejecucion.log').write_text('Replay offline del snapshot '+str(Path(snapshot).resolve()),encoding='utf-8')
    return save_summary(ticker,out,excel,sheets,datetime.now(timezone.utc))


def main():
    ap=argparse.ArgumentParser(description='Ejecuta y audita valoración V5')
    ap.add_argument('--ticker')
    ap.add_argument('--snapshot',help='Reproducir entradas JSON offline (sin --ticker)')
    ap.add_argument('--outdir',default='Resultados')
    ap.add_argument('--num-quarters',type=int,default=12)
    ap.add_argument('--sec-email',default=os.environ.get('SEC_CONTACT_EMAIL',''))
    args=ap.parse_args()
    if args.num_quarters<4 or args.num_quarters>24:
        ap.error('Selecciona de 4 a 24 trimestres')
    if not args.ticker and not args.snapshot:ap.error('Indica --ticker o --snapshot')
    if args.ticker and args.snapshot:ap.error('Selecciona --ticker o --snapshot, no ambos')
    try:return replay(args.snapshot,args.outdir) if args.snapshot else run(args.ticker,args.outdir,args.num_quarters,args.sec_email)
    except Exception as e:
        print(f'FALLO: {type(e).__name__}: {e}',file=sys.stderr)
        return 1

if __name__=='__main__':sys.exit(main())
