"""Actualizaciones explícitas: datos, búsquedas y análisis V7 persistidos."""
from copy import deepcopy
from difflib import SequenceMatcher
import json
import re
import time
from pathlib import Path
import os,subprocess,sys,tempfile
from entorno_ejecucion import child_environment
import unicodedata
import pandas as pd
from auditoria_io import restore_frame
from entorno_ejecucion import configure_runtime,network_diagnostic
from flujo_acciones import analysis_from_snapshot
from seguimiento_store import Store,TTL,ticker_key
from seguimiento_metricas import summarize,quarter_series


ROOT=Path(__file__).resolve().parent


def load_v7_capture(ticker,quarters,contact,cache_dir=None,force=False):
    if not re.fullmatch(r'[A-Z0-9][A-Z0-9.\-^=]{0,24}',ticker):raise ValueError('Ticker no válido')
    if contact and not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+',contact):raise ValueError('Contacto SEC no válido')
    with tempfile.TemporaryDirectory(prefix='fundamental_ui_') as folder:
        env=child_environment()
        if cache_dir:
            env['VALUACION_SOURCE_CACHE']=str(cache_dir)
            env['VALUACION_SOURCE_FORCE']='1' if force else '0'
        if contact:env['SEC_CONTACT_EMAIL']=contact
        args=[sys.executable,str(ROOT/'ejecutar_analisis.py'),'--ticker',ticker,'--num-quarters',str(quarters),'--outdir',folder]
        proc=subprocess.run(args,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=1500)
        snapshot=Path(folder)/(ticker+'_inputs.json')
        execution=Path(folder)/(ticker+'_ejecucion.log')
        detail=execution.read_text(encoding='utf-8',errors='replace') if execution.exists() else (proc.stderr or proc.stdout)
        if cache_dir:
            logs=Path(cache_dir)/'logs';logs.mkdir(exist_ok=True)
            (logs/(ticker+'.log')).write_text(detail,encoding='utf-8')
        if proc.returncode not in (0,2) or not snapshot.exists():raise RuntimeError(detail[-1800:])
        return snapshot.read_text(encoding='utf-8')



def normalized(value):return ''.join(c for c in unicodedata.normalize('NFKD',str(value).casefold()) if not unicodedata.combining(c))


def search_companies(query,store,yf=None):
    query=query.strip()
    if not 2<=len(query)<=100:raise ValueError('Escribe entre 2 y 100 caracteres del nombre o ticker')
    if yf is None:
        configure_runtime();import yfinance as yf
    def fetch():
        response=yf.Search(query,max_results=12,news_count=0,lists_count=0,enable_fuzzy_query=True,timeout=15)
        return response.quotes or []
    raw=store.cached('watch-search:'+normalized(query),fetch,TTL['search'])
    rows={}
    for r in raw:
        if r.get('quoteType')!='EQUITY' or not r.get('symbol'):continue
        try:key=ticker_key(r['symbol'])
        except ValueError:continue
        name=r.get('longname') or r.get('shortname') or key
        rows[key]={'ticker':key,'name':name,'exchange':r.get('exchDisp') or r.get('exchange') or 'Bolsa sin identificar'}
    def score(row):
        key=normalized(query);text=normalized(row['name'])
        return (3 if key==normalized(row['ticker']) else 1 if key in text else 0)+SequenceMatcher(None,key,text).ratio()
    return sorted(rows.values(),key=score,reverse=True)


def quote(ticker,store,yf=None,force=False):
    configure_runtime()
    if yf is None:import yfinance as yf
    obj=yf.Ticker(ticker)
    def fetch():
        h=obj.history(period='5d',interval='1d',auto_adjust=False)
        if h is None or h.empty or 'Close' not in h:raise ValueError('Yahoo no devuelve cotización fechada')
        values=pd.to_numeric(h['Close'],errors='coerce').dropna();values=values[values>0]
        if values.empty:raise ValueError('Yahoo no devuelve un precio positivo')
        date=pd.Timestamp(values.index[-1]).date().isoformat()
        return {'price':float(values.iloc[-1]),'date':date,'currency':obj.fast_info.get('currency'),
                'market_cap':obj.fast_info.get('market_cap'),'shares':obj.fast_info.get('shares'),'source':'Yahoo history 1d / fast_info'}
    return store.cached('watch-quote:'+ticker,fetch,TTL['quote'],force)


class Service:
    def __init__(self,store,load_capture=load_v7_capture,clock=time.time):self.store=store;self.load_capture=load_capture;self.clock=clock

    def save_capture(self,payload,settings=None):
        p=deepcopy(payload)
        if settings is not None:p['evidence']['stock_model']['settings']=deepcopy(settings)
        r,_=analysis_from_snapshot(p);self.store.add(r.summary['ticker'],(p['kwargs'].get('info') or {}).get('longName',''))
        m=summarize(p,r);m['financial_updated']=0  # Captura archivada, no consulta de hoy.
        self.store.save(r.summary['ticker'],p,m)

    def refresh(self,ticker,force=False):
        ticker=ticker_key(ticker);old=self.store.entry(ticker)
        if old is None:raise ValueError('Confirma y añade primero la empresa')
        start=self.clock()
        try:
            financial_at=old['metrics'].get('financial_updated',0)
            full=not old['payload'] or force or start-financial_at>=TTL['financial']
            p=json.loads(self.load_capture(ticker,24,'',cache_dir=str(self.store.path),force=force)) if full else deepcopy(old['payload'])
            if p['kwargs']['ticker']!=ticker:raise ValueError('La captura pertenece a otro ticker')
            if old['payload']:
                p['evidence']['stock_model']['settings']=deepcopy(old['payload'].get('evidence',{}).get('stock_model',{}).get('settings',{}))
            a=restore_frame(p['frames']['annual']);q=restore_frame(p['frames'].get('quarterly')) if p['frames'].get('quarterly') else pd.DataFrame()
            if a.empty and q.empty:raise ValueError('Sin estados financieros utilizables; se conserva el análisis anterior')
            latest=quote(ticker,self.store,force=force);k=p['kwargs'];today=pd.Timestamp.now(tz='UTC').date()
            if not latest.get('currency') or latest['currency']!=k['quote_currency']:raise ValueError('Moneda de la cotización distinta o no acreditada; no se convierte por conjetura')
            if not 0<=(pd.Timestamp(today)-pd.Timestamp(latest['date'])).days<=7:raise ValueError('Cotización futura o caducada')
            k.update(price=latest['price'],as_of=str(today))
            k['info']={**(k.get('info') or {}),'valuation_quote_date':latest['date']}
            k['info'].pop('regularMarketTime',None)  # La fuente acredita fecha, no una hora inventada.
            if latest.get('market_cap'):k['market_cap']=latest['market_cap']
            if latest.get('shares'):k['shares_outstanding']=latest['shares']
            info=k.get('info') or {};facts=None
            cik=info.get('valuation_cik') or (a['CIK SEC'].dropna().iloc[-1] if 'CIK SEC' in a and a['CIK SEC'].notna().any() else None)
            if cik:
                from sec_historical import _get_json,SEC_FACTS_URL
                cik=str(cik).split('.')[0].zfill(10);url=SEC_FACTS_URL.format(cik=cik)
                facts=self.store.cached('SEC:'+url,lambda:_get_json(url,'StockValuationProject/1.0'),TTL['financial'],force)
                if str(facts.get('cik','')).lstrip('0')!=cik.lstrip('0'):raise ValueError('Identidad CompanyFacts incompatible')
            series=quarter_series(q,k['as_of'],facts,k['financial_currency'])
            r,_=analysis_from_snapshot(p);m=summarize(p,r,series)
            m['financial_updated']=start if full else financial_at;m['quote_source']=latest['source']
            errors=self.store.errors_since(start)
            if errors and old['payload']:raise RuntimeError('; '.join(errors))
            self.store.save(ticker,p,m,'; '.join(errors) if errors else None)
        except Exception as exc:
            self.store.failed(ticker,network_diagnostic(exc,'Yahoo/SEC')+' · '+str(exc)[:500])
        return self.store.entry(ticker)
