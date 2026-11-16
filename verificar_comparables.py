"""Prueba con fuentes reales, sin ejecutar la valoración completa ni inventar datos.

python verificar_comparables.py --tickers MSFT 000660.KS JNJ JPM NVDA --outdir Resultados/comparables
Devuelve 2 si alguna empresa no reúne cinco pares; conserva todo el diagnóstico.
"""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import pandas as pd
from auditoria_io import clean
from comparables_inteligentes import (discover_candidates,economic_seeds,selected_candidates,
    basic_peer_row,score_and_filter)
from seguimiento_metricas import informative_peers
from seguimiento_fuentes import CachedYahoo
from entorno_ejecucion import configure_runtime


def run(ticker,outdir,budget=55):
    import yfinance
    configure_runtime()
    yf=CachedYahoo(yfinance,str(outdir/'cache'),ticker)
    info=yf.Ticker(ticker).get_info()
    if not info.get('longBusinessSummary'):
        raise ValueError('Sin descripción de actividad del objetivo')
    regions={'South Korea':'KR','Taiwan':'TW','Japan':'JP','United Kingdom':'GB','Germany':'DE'}
    candidates,errors=discover_candidates(yf,ticker,info,region=regions.get(info.get('country'),'US'),max_candidates=85)
    for symbol in economic_seeds(ticker):
        candidates[symbol]={'Ticker':symbol,'Origen candidatos':'Semilla económica; evaluar actividad','Prioridad origen':-5}
    for symbol in selected_candidates(ticker):
        candidates[symbol]={'Ticker':symbol,'Origen candidatos':'Manual; evaluar actividad','Prioridad origen':-10}
    rows=[];profiles={};trace=[]
    ordered=sorted(candidates.values(),key=lambda r:r['Prioridad origen'])[:budget]
    for candidate in ordered:
        symbol=candidate['Ticker']
        try:
            profile=yf.Ticker(symbol).get_info()
            if not profile.get('longBusinessSummary'):
                raise ValueError('Perfil sin actividad')
            profiles[symbol]=profile
            rows.append(basic_peer_row(symbol,profile,candidate['Origen candidatos']))
            trace.append({**candidate,'Estado':'DESCARGADO'})
            if len(rows)>=10 and len(rows)%5==0:
                from comparables_inteligentes import select_display_peers
                if len(select_display_peers(pd.DataFrame(rows),info))>=5:
                    break
        except Exception as exc:
            trace.append({**candidate,'Estado':'ERROR','Detalle':type(exc).__name__})
            if type(exc).__name__=='YFRateLimitError':
                errors.append('Yahoo limita consultas; no se insiste y se conserva la cobertura parcial')
                break
    frame=pd.DataFrame(rows)
    *_,universe=score_and_filter(frame,ticker,target_info=info,return_universe=True)
    result=informative_peers(universe,info)
    output={'ticker':ticker,'captured_at':datetime.now(timezone.utc).isoformat(),
        'status':'CINCO_CON_DATOS' if len(result['rows'])==5 else 'COBERTURA_INSUFICIENTE',
        'provider_keys_configured':__import__('os').environ.get('FMP_API_KEY') is not None or __import__('os').environ.get('FINNHUB_API_KEY') is not None,
        'result':result,'discovery_errors':errors,'discovery':trace,
        'target_profile':info,'peer_profiles':profiles}
    (outdir/(ticker+'.json')).write_text(json.dumps(clean(output),ensure_ascii=False,allow_nan=False,indent=2),encoding='utf-8')
    pd.DataFrame(result['rows']).to_csv(outdir/(ticker+'.csv'),index=False)
    print(ticker,output['status'],[r['Ticker'] for r in result['rows']],flush=True)
    return output


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tickers',nargs='+',default=['MSFT','000660.KS','JNJ','JPM','NVDA'])
    parser.add_argument('--outdir',default='Resultados/comparables')
    parser.add_argument('--budget',type=int,default=55)
    args=parser.parse_args();out=Path(args.outdir);out.mkdir(parents=True,exist_ok=True)
    states=[]
    for ticker in args.tickers:
        try:
            states.append(run(ticker.upper(),out,args.budget)['status'])
        except Exception as exc:
            states.append('ERROR');print(ticker,type(exc).__name__,str(exc)[:180],flush=True)
    raise SystemExit(0 if states and all(s=='CINCO_CON_DATOS' for s in states) else 2)
