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
from auditoria_io import restore_frame,frame_payload
from entorno_ejecucion import configure_runtime,network_diagnostic
from flujo_acciones import analysis_from_snapshot
from seguimiento_store import Store,TTL,ticker_key
from seguimiento_metricas import summarize,quarter_series,informative_peers
from seguimiento_incremental import quote_ttl,filing_fingerprint,fingerprint,merge_history,normalized_prices


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


def quote(ticker,store,yf=None,force=False,market_zone=None):
    configure_runtime()
    if yf is None:import yfinance as yf
    obj=yf.Ticker(ticker)
    def fetch():
        store.set_meta('last_quote_query',{'at':store.clock(),'ticker':ticker,'status':'consultando'})
        h=obj.history(period='5d',interval='1d',auto_adjust=False)
        if h is None or h.empty or 'Close' not in h:raise ValueError('Yahoo no devuelve cotización fechada')
        values=pd.to_numeric(h['Close'],errors='coerce').dropna();values=values[values>0]
        if values.empty:raise ValueError('Yahoo no devuelve un precio positivo')
        date=pd.Timestamp(values.index[-1]).date().isoformat()
        warnings=[]
        def optional(key):
            try:return obj.fast_info.get(key)
            except Exception as exc:
                warnings.append(key+': '+network_diagnostic(exc,'Yahoo'));return None
        result={'price':float(values.iloc[-1]),'date':date,'currency':obj.fast_info.get('currency'),
                'market_cap':optional('market_cap'),'shares':optional('shares'),'source':'Yahoo history 1d / fast_info','warnings':warnings,'queried_at':store.clock(),
                'history_tail':frame_payload(normalized_prices(h))}
        store.set_meta('last_quote_query',{'at':store.clock(),'ticker':ticker,'status':'recibido'});return result
    try:return store.cached('watch-quote:'+ticker,fetch,quote_ttl(store.clock(),market_zone),force)
    except Exception:
        store.set_meta('last_quote_query',{'at':store.clock(),'ticker':ticker,'status':'fallo'});raise


def provider_profile(ticker,store,force=False):
    configure_runtime()
    def fetch():
        import yfinance as yf
        info=yf.Ticker(ticker).get_info()
        if not isinstance(info,dict) or not info:raise ValueError('Perfil/ratios Yahoo incompleto')
        return {'info':info,'queried_at':store.clock()}
    return store.cached('provider-profile:'+ticker,fetch,3600,force)


def _cik(payload):
    k=payload['kwargs'];a=restore_frame(payload['frames']['annual'])
    value=(k.get('info') or {}).get('valuation_cik') or (a['CIK SEC'].dropna().iloc[-1] if 'CIK SEC' in a and a['CIK SEC'].notna().any() else None)
    return str(value).split('.')[0].zfill(10) if value else None


def check_revision(payload,store,force=False):
    cik=_cik(payload);day=str(pd.Timestamp.now(tz='UTC').date())
    if cik:
        from sec_historical import _get_json,SEC_FACTS_URL,SEC_SUBMISSIONS_URL
        url=SEC_SUBMISSIONS_URL.format(cik=cik)
        prior_submission=store.peek('SEC:'+url)
        submission=store.cached('SEC:'+url,lambda:_get_json(url,'StockValuationProject/1.0'),TTL['submissions'],force)
        if str(submission.get('cik','')).lstrip('0')!=cik.lstrip('0'):raise ValueError('CIK submissions distinto')
        filings=filing_fingerprint(submission,day)
        changed_filing=prior_submission is not None and filing_fingerprint(prior_submission,day)['hash']!=filings['hash']
        url=SEC_FACTS_URL.format(cik=cik)
        facts=store.cached('SEC:'+url,lambda:_get_json(url,'StockValuationProject/1.0'),TTL['financial'],force or changed_filing)
        if str(facts.get('cik','')).lstrip('0')!=cik.lstrip('0'):raise ValueError('CIK CompanyFacts distinto')
        return {'hash':fingerprint([filings['hash'],fingerprint(facts)]),'filings':filings['filings'],'source':'SEC accession/fecha + contenido CompanyFacts','facts':facts}
    # Sin SEC: comparar contenidos, no sólo la fecha del último cierre.
    import yfinance as yf
    from seguimiento_fuentes import CachedYahoo
    obj=CachedYahoo(yf,str(store.path),payload['kwargs']['ticker'],force).Ticker(payload['kwargs']['ticker'])
    frames=[obj.quarterly_income_stmt,obj.income_stmt,obj.quarterly_balance_sheet,obj.balance_sheet,obj.quarterly_cashflow,obj.cashflow]
    return {'hash':fingerprint([frame_payload(f) for f in frames]),'source':'Contenido de estados Yahoo','filings':[],'facts':None}


def update_history(ticker,payload,store,quote_date,force=False,quote_tail=None):
    from historico_acciones import number
    old=restore_frame(payload['historical']['Precios y splits']) if payload.get('historical',{}).get('Precios y splits') else pd.DataFrame()
    old=normalized_prices(old)
    tail=restore_frame(quote_tail) if quote_tail else pd.DataFrame()
    if not force and len(old) and len(tail) and pd.Timestamp(tail.index.min())<=old.index.max()+pd.Timedelta(days=1):
        merged,split=merge_history(old,tail)
        if not split:return merged,False,'cierres recientes reutilizados de la consulta de cotización'
    if not force and len(old) and quote_date and old.index.max()>=pd.Timestamp(quote_date) and tail.empty:return old,False,'reutilizado'
    configure_runtime();import yfinance as yf
    full=force or old.empty or (len(tail)>0 and merge_history(old,tail)[1])
    start=str((old.index.max()-pd.Timedelta(days=5)).date()) if len(old) else None
    kwargs={'period':'max','interval':'1d','auto_adjust':False} if full else {'start':start,'end':str((pd.Timestamp.now(tz='UTC')+pd.Timedelta(days=1)).date()),'interval':'1d','auto_adjust':False}
    key='watch-history:'+ticker+':'+json.dumps(kwargs,sort_keys=True)
    chunk=store.cached(key,lambda:yf.Ticker(ticker).history(**kwargs),TTL['quote'] if not full else TTL['history'],force)
    result,split=merge_history(old,chunk)
    if full:result=normalized_prices(chunk)
    if split and not full:
        # Un split cambia también la base de los precios pasados: recuperar la
        # serie ajustada completa, nunca pegar bases incompatibles.
        chunk=yf.Ticker(ticker).history(period='max',interval='1d',auto_adjust=False)
        if chunk.empty:raise ValueError('Split nuevo sin histórico completo conciliable')
        result=normalized_prices(chunk)
    return result,split,'histórico completo por split' if split else 'descarga completa' if full else 'nuevos cierres / solape de cinco días'


def refresh_validated_peers(payload,result,store):
    """Reutiliza candidatos/actividad; sólo renueva evidencia con el colector V7."""
    from comparables_ttm import collect_ttm_evidence
    from seguimiento_fuentes import CachedYahoo
    from types import SimpleNamespace
    from sec_historical import _get_json
    import yfinance as yf
    source=restore_frame(payload['frames']['peers']);selected=result.peers
    if selected.empty:return source,[]
    q=restore_frame(payload['frames']['quarterly']);end=q.index.max() if len(q) else None
    def get(url,**kwargs):
        data=store.cached('SEC:'+url,lambda:_get_json(url,'StockValuationProject/1.0'),TTL['financial'])
        return SimpleNamespace(raise_for_status=lambda:None,json=lambda:data)
    renewed,records=collect_ttm_evidence(selected,CachedYahoo(yf,str(store.path),payload['kwargs']['ticker']),payload['kwargs']['as_of'],end,requests_get=get)
    for _,row in renewed.iterrows():
        index=source.index[source['Ticker'].eq(row['Ticker'])]
        for i in index:
            if isinstance(row.get('Evidencia TTM'),dict):source.at[i,'Evidencia TTM']=row['Evidencia TTM']
    return source,records


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
        start=self.clock();p=deepcopy(old['payload']);previous=old['metrics'];errors=[];components={};revision=None;full=False
        financial_at=previous.get('financial_updated') or 0;checked=previous.get('financial_checked') or financial_at
        revision_ttl=TTL['submissions'] if p and _cik(p) else TTL['financial']
        due=not p or force or start-checked>=revision_ttl
        def error(component,exc):
            provider='SEC' if component=='SEC' else 'Yahoo' if component in ['quote','history','provider_ratios','estados_Yahoo'] or component.startswith('peer_B:') else 'V7/SEC/Yahoo'
            detail=network_diagnostic(exc,provider)+' · '+str(exc)[:300]
            errors.append(component+': '+detail);components[component]={'state':'fallo; datos anteriores conservados','detail':detail}
        try:
            need_full=not p or force
            if due and p and not force:
                try:
                    revision=check_revision(p,self.store)
                    need_full=revision['hash']!=previous.get('revision_hash')
                    components['SEC' if _cik(p) else 'estados_Yahoo']={'state':'revisión detectada' if need_full else 'sin cambios de contenido/filings','source':revision['source']}
                    checked=start
                except Exception as exc:
                    error('SEC' if _cik(p) else 'estados_Yahoo',exc);need_full=not financial_at
            if need_full:
                try:
                    candidate=json.loads(self.load_capture(ticker,24,'',cache_dir=str(self.store.path),force=force))
                    if candidate['kwargs']['ticker']!=ticker:raise ValueError('La captura pertenece a otro ticker')
                    if p:candidate['evidence']['stock_model']['settings']=deepcopy(p.get('evidence',{}).get('stock_model',{}).get('settings',{}))
                    p=candidate;full=True;financial_at=start;checked=start
                    components['financial']={'state':'análisis V7 completo; cachés de fuentes respetadas' if not force else 'forzado completo'}
                    try:revision=check_revision(p,self.store)
                    except Exception as exc:error('SEC' if _cik(p) else 'estados_Yahoo',exc)
                except Exception as exc:error('financial',exc)
            else:components['financial']={'state':'reutilizado; sin nueva publicación/revisión' if due else 'reutilizado; comprobación vigente'}
            if p is None:
                self.store.failed(ticker,'; '.join(errors) or 'Sin captura disponible')
                self.store.set_meta('update:'+ticker,{'at':start,'components':components});return self.store.entry(ticker)
            facts=revision.get('facts') if revision else None
            if facts is None and _cik(p):
                from sec_historical import SEC_FACTS_URL
                facts=self.store.peek('SEC:'+SEC_FACTS_URL.format(cik=_cik(p)))
            if facts:
                shares_tag=facts.get('facts',{}).get('us-gaap',{}).get('CommonStockSharesOutstanding')
                if shares_tag:p.setdefault('evidence',{})['watch_fy_shares']={'cik':facts.get('cik'),'facts':{'us-gaap':{'CommonStockSharesOutstanding':deepcopy(shares_tag)}}}
            latest=None;zone=(p['kwargs'].get('info') or {}).get('exchangeTimezoneName')
            fresh=self.store.fresh('watch-quote:'+ticker) and not force
            try:
                latest=quote(ticker,self.store,force=force,market_zone=zone)
                today=pd.Timestamp.now(tz='UTC').date()
                if not 0<=(pd.Timestamp(today)-pd.Timestamp(latest['date'])).days<=7:raise ValueError('Cotización futura/caducada')
                expected=p['kwargs']['quote_currency']
                if expected and latest.get('currency')!=expected:raise ValueError('Moneda de cotización distinta; no se convierte por conjetura')
                if not latest.get('currency'):raise ValueError('Moneda sin acreditar')
                components['quote']={'state':'caché reutilizada' if fresh else 'consultado','queried_at':latest.get('queried_at'),'price_date':latest['date']}
            except Exception as exc:error('quote',exc)
            try:
                h,split,history_state=update_history(ticker,p,self.store,latest['date'] if latest else None,force and not full,quote_tail=latest.get('history_tail') if latest else None)
                if split and not full:
                    candidate=json.loads(self.load_capture(ticker,24,'',cache_dir=str(self.store.path),force=True))
                    candidate['evidence']['stock_model']['settings']=deepcopy(p['evidence']['stock_model'].get('settings',{}))
                    p=candidate;full=True;financial_at=start;components['financial']={'state':'revalidado por split nuevo'}
                p.setdefault('historical',{})['Precios y splits']=frame_payload(h)
                components['history']={'state':history_state,'rows':len(h)}
            except Exception as exc:error('history',exc)
            k=p['kwargs']
            if latest:
                k.update(price=latest['price'],as_of=str(pd.Timestamp.now(tz='UTC').date()),quote_currency=latest['currency'])
                k['info']={**(k.get('info') or {}),'valuation_quote_date':latest['date']};k['info'].pop('regularMarketTime',None)
                if latest.get('market_cap'):k['market_cap']=latest['market_cap']
                if latest.get('shares'):k['shares_outstanding']=latest['shares']
            # Si SEC confirma un cierre posterior y no se incorporó, mantener el
            # bloqueo original V7, aunque el precio y otros datos sean utilizables.
            if revision and not full:
                q0=restore_frame(p['frames']['quarterly']) if p['frames'].get('quarterly') else pd.DataFrame()
                ends=[f['reportDate'] for f in revision['filings'] if f['form'] in ['10-Q','10-K','10-Q/A','10-K/A'] and f.get('reportDate')]
                if ends and (q0.empty or pd.Timestamp(max(ends))>q0.index.max()):k['recent_results_check']={'status':'BLOQUEO','newer_filing_confirmed':True,'detail':'SEC confirma resultados posteriores todavía no incorporados'}
            try:
                profile=provider_profile(ticker,self.store,force)
                p.setdefault('evidence',{})['watch_provider']=profile
                components['provider_ratios']={'state':'disponible','queried_at':profile['queried_at']}
            except Exception as exc:error('provider_ratios',exc)
            r,_=analysis_from_snapshot(p)
            peers_at=previous.get('peers_updated') or (financial_at if full else 0)
            if not full and (force or start-peers_at>=TTL['peers']):
                try:
                    peers,trace=refresh_validated_peers(p,r,self.store);p['frames']['peers']=frame_payload(peers)
                    p['evidence']['peer_ttm_sources']=trace;r,_=analysis_from_snapshot(p);peers_at=start
                    components['peers_A']={'state':'evidencia renovada; candidatos económicos reutilizados'}
                except Exception as exc:error('peers_A',exc)
            else:components['peers_A']={'state':'V7 estricto; candidatos/evidencia guardados'}
            chosen=informative_peers(r.universe,k.get('info') or {})['rows']
            peer_infos=deepcopy(p.get('evidence',{}).get('watch_peer_profiles',{}))
            for peer in chosen:
                try:
                    peer_infos[peer['Ticker']]=provider_profile(peer['Ticker'],self.store,force)
                    components['peer_B:'+peer['Ticker']]={'state':'ratios de proveedor disponibles','queried_at':peer_infos[peer['Ticker']]['queried_at']}
                except Exception as exc:
                    error('peer_B:'+peer['Ticker'],exc)
                    if 'LIMITE' in network_diagnostic(exc,'Yahoo'):break
            p.setdefault('evidence',{})['watch_peer_profiles']=peer_infos
            components['peers_B']={'state':'ratios 1 h; búsqueda/evaluación económica reutilizadas','candidates':len(chosen)}
            q=restore_frame(p['frames']['quarterly']) if p['frames'].get('quarterly') else pd.DataFrame()
            saved=p.get('historical',{}).get('Seguimiento neto trimestral')
            if facts is not None:series=quarter_series(q,k['as_of'],facts,k['financial_currency'],include_predecessor=True)
            elif saved:
                series=restore_frame(saved);series.index=pd.to_datetime(series['Cierre']);series=quarter_series(series,k['as_of'],include_predecessor=True)
            else:series=quarter_series(q,k['as_of'])
            p['historical']['Seguimiento neto trimestral']=frame_payload(series)
            m=summarize(p,r,series)
            if facts:
                from seguimiento_ev import fiscal_history
                m['ev_fy']=fiscal_history(p,facts=facts)
                m['row']['EV/EBITDA último FY']=m['ev_fy']['last'];m['row']['EV/EBITDA mediana 5 FY']=m['ev_fy']['median']
                m['row']['Calidad EV FY']=m['ev_fy']['last_type']+' · '+m['ev_fy']['last_confidence'] if m['ev_fy']['last'] else 'No disponible'
            if latest and latest.get('warnings'):m['row']['Advertencias']+=' · Mercado parcial: '+'; '.join(latest['warnings'])
            pending=deepcopy(previous.get('component_errors',{}))
            for name,trace in components.items():
                if trace['state'].startswith('fallo'):pending[name]=trace.get('detail','Datos parciales')
                elif not (trace['state'].startswith('reutilizado') or trace['state'].startswith('V7 estricto')):pending.pop(name,None)
            if pending:m['row']['Advertencias']+=' · '+'; '.join(name+': '+detail for name,detail in pending.items())
            m.update(financial_updated=financial_at,financial_checked=checked,peers_updated=peers_at,revision_hash=revision['hash'] if revision else previous.get('revision_hash'),
                     quote_queried_at=latest.get('queried_at') if latest else previous.get('quote_queried_at'),components=components,component_errors=pending)
            components['valuation']={'state':'V7 recalculado con datos/supuestos guardados; sin calibración al mercado'}
            self.store.save(ticker,p,m,'; '.join(name+': '+detail for name,detail in pending.items()) if pending else None)
            self.store.set_meta('last_table_update',start);self.store.set_meta('update:'+ticker,{'at':start,'components':components})
        except Exception as exc:self.store.failed(ticker,network_diagnostic(exc,'Yahoo/SEC')+' · '+str(exc)[:500])
        return self.store.entry(ticker)

    def ensure_metrics(self,entry):
        if entry['payload'] and (entry['metrics'].get('schema_version')!=4 or 'methods' not in entry['metrics']):
            p=deepcopy(entry['payload'])
            if entry['metrics'].get('quarters') and 'Seguimiento neto trimestral' not in p.get('historical',{}):
                p.setdefault('historical',{})['Seguimiento neto trimestral']=frame_payload(pd.DataFrame(entry['metrics']['quarters']))
            r,_=analysis_from_snapshot(p);m=summarize(p,r)
            for key in ['financial_updated','financial_checked','revision_hash','quote_queried_at','peers_updated','components','component_errors']:m[key]=entry['metrics'].get(key,{} if key in ('components','component_errors') else 0)
            self.store.upgrade_snapshot(entry['ticker'],p,m);entry={**entry,'payload':p,'metrics':m}
        return entry

    def save_settings(self,ticker,settings):
        entry=self.store.entry(ticker)
        if not entry or not entry['payload']:return
        p=entry['payload'];old=p.get('evidence',{}).get('stock_model',{}).get('settings',{})
        if old==settings:return
        p['evidence']['stock_model']['settings']=deepcopy(settings)
        r,_=analysis_from_snapshot(p);m=summarize(p,r)
        for key in ['financial_updated','financial_checked','revision_hash','quote_queried_at','peers_updated','components','component_errors']:
            if key in entry['metrics']:m[key]=entry['metrics'][key]
        self.store.save(ticker,p,m,entry['error'])
