from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import pandas as pd
import pytest
from auditoria_io import frame_payload,restore_frame
from flujo_acciones import analysis_from_snapshot
from seguimiento_store import Store,TTL
from seguimiento_fuentes import CachedYahoo
from seguimiento_metricas import quarter_series,summarize,cohort_stats,discount_color
from seguimiento_servicio import Service,search_companies
from tests.test_v7_integrada import archived


def test_store_unicode_persistence_duplicates_preferences_and_failure_keeps_last_valid(tmp_path):
    path=tmp_path/'Álvaro 日本';store=Store(path,clock=lambda:1000)
    assert store.add('msft','Microsoft','NASDAQ') and not store.add('MSFT')
    p=archived('MSFT');r,_=analysis_from_snapshot(p);m=summarize(p,r)
    store.save('MSFT',p,m);store.set_preferences(['Ticker','PER actual TTM'])
    store.failed('MSFT','SSL failed')
    loaded=Store(path).entry('MSFT')
    assert loaded['payload']==p and loaded['metrics']==m and loaded['updated']==1000
    assert loaded['error']=='SSL failed' and Store(path).preferences()==['Ticker','PER actual TTM']
    store.remove('MSFT');assert store.entries()==[]


def test_failure_before_first_analysis_is_persisted(tmp_path):
    s=Store(tmp_path);s.add('MISSING');s.failed('MISSING','offline')
    assert s.entry('MISSING')['payload'] is None and s.entry('MISSING')['error']=='offline'


def test_cache_ttl_separate_components_errors_and_frame_roundtrip(tmp_path):
    now=[0];s=Store(tmp_path,clock=lambda:now[0]);calls=[]
    frame=pd.DataFrame({'net':[1.,2.]},index=pd.to_datetime(['2026-03-31','2026-06-30']));frame.attrs={'audit':True}
    def fetch():calls.append(True);return frame
    pd.testing.assert_frame_equal(s.cached('financial',fetch,TTL['financial']),frame)
    s.cached('financial',fetch,TTL['financial']);assert len(calls)==1
    now[0]=TTL['quote']+1;s.cached('financial',fetch,TTL['financial']);assert len(calls)==1
    now[0]=TTL['financial']+1;s.cached('financial',fetch,TTL['financial']);assert len(calls)==2
    def fail():raise ConnectionError('offline')
    with pytest.raises(ConnectionError):s.cached('financial',fail,TTL['financial'],True)
    assert s.errors_since(0)
    pd.testing.assert_frame_equal(s.cached('financial',fetch,TTL['financial']),frame)
    assert TTL['quote']<TTL['financial']<TTL['peers']<TTL['history']


def test_yahoo_proxy_does_not_repeat_search_or_statements(tmp_path):
    calls=[]
    class YF:
        def Search(self,*a,**k):calls.append('search');return SimpleNamespace(quotes=[{'symbol':'ABC'}])
        def Ticker(self,*a,**k):
            class T:
                @property
                def quarterly_income_stmt(self):calls.append('financial');return pd.DataFrame({'x':[1.]})
            return T()
    y=CachedYahoo(YF(),tmp_path,'ABC')
    assert y.Search('abc').quotes==y.Search('abc').quotes
    assert y.Ticker('ABC').quarterly_income_stmt.equals(y.Ticker('ABC').quarterly_income_stmt)
    assert calls==['search','financial']


def test_history_cache_roundtrip_preserves_dst_timezones_and_financial_columns(tmp_path):
    index=pd.date_range('2025-01-01',periods=365,tz='America/New_York',name='Date')
    frame=pd.DataFrame({'Close':range(365)},index=index)
    s=Store(tmp_path);result=s.cached('DST',lambda:frame,TTL['history'])
    pd.testing.assert_frame_equal(result,frame)
    statements=pd.DataFrame([[100.,120.]],columns=pd.DatetimeIndex(['2025-06-30','2026-06-30'],name='Date'))
    pd.testing.assert_frame_equal(s.cached('statement',lambda:statements,TTL['financial']),statements)


def test_empty_history_has_no_fabricated_multiple_and_is_not_cached(tmp_path):
    from historico_acciones import historical_multiples
    p=archived('MSFT');annual=restore_frame(p['frames']['annual'])
    h=historical_multiples(annual,pd.DataFrame(),'USD','USD','2026-11-12')
    assert h['PER histórico'].isna().all() and not h['Base acción conciliada'].any()
    s=Store(tmp_path)
    with pytest.raises(ValueError,match='vacía'):s.cached('history',pd.DataFrame,TTL['history'])


def facts_from_quarters(years=6):
    rows=[]
    for year in range(2020,2020+years):
        vals=[10.,20.,30.,40.];total=0
        for i,end in enumerate([f'{year}-03-31',f'{year}-06-30',f'{year}-09-30',f'{year}-12-31']):
            total+=vals[i]
            rows.append({'start':f'{year}-01-01','end':end,'val':total,'filed':str((pd.Timestamp(end)+pd.Timedelta(days=30)).date()),'form':'10-K' if i==3 else '10-Q','accn':f'{year}-Q{i+1}'})
    return {'cik':123,'facts':{'us-gaap':{'NetIncomeLoss':{'units':{'USD':rows}}}}}


def test_official_twenty_quarters_reconstruct_ytd_without_four_month_periods():
    q=quarter_series(pd.DataFrame(), '2026-02-01',facts_from_quarters())
    assert len(q)==20 and q['QoQ (%)'].notna().sum()==20
    assert q['Beneficio neto'].tolist()==[10.,20.,30.,40.]*5
    assert q.iloc[-1]['Estado']=='SEC diferencia YTD (flujo aditivo)'
    assert q.iloc[-1]['Componentes'][1]['coefficient']==-1
    assert ((pd.to_datetime(q['Cierre'])-pd.to_datetime(q['Inicio'])).dt.days.between(69,104)).all()


def test_qoq_no_fake_four_month_or_zero_negative_base_or_missing_period():
    d=pd.DataFrame({'Beneficio neto':[10.,20.,0.,5.,-3.,2.]},index=pd.to_datetime(['2024-01-31','2024-05-31','2024-08-31','2024-11-30','2025-02-28','2025-05-31']))
    q=quarter_series(d,'2025-06-01')
    assert pd.isna(q.iloc[1]['QoQ (%)']) and 'no consecutivos' in q.iloc[1]['Motivo QoQ']
    assert pd.isna(q.iloc[3]['QoQ (%)']) and pd.isna(q.iloc[5]['QoQ (%)'])
    assert q.iloc[4]['QoQ (%)']==pytest.approx(-160.)


def test_sec_future_filings_and_conflicts_do_not_create_growth():
    facts=facts_from_quarters(1)
    q=quarter_series(pd.DataFrame({'Beneficio neto':[999.]},index=pd.to_datetime(['2020-09-30'])),'2020-11-01',facts)
    assert q['Cierre'].max()==pd.Timestamp('2020-09-30')
    assert pd.isna(q.iloc[-1]['Beneficio neto']) and 'divergencia' in q.iloc[-1]['Estado']
    assert pd.isna(q.iloc[-1]['QoQ (%)'])


def test_peer_means_use_only_homogeneous_unique_valid_issuers():
    p=pd.DataFrame({'Ticker':['A','B','C','A','D'],'Emisor económico':['A','B','C','A','D'],
        'v':[10.,20.,30.,10.,1000.],'ok':[True,True,True,True,False],'cohort':['FY1']*5,'Divisa cotización':['USD']*5})
    stats=cohort_stats(p,'v','ok','cohort',currency='USD')
    assert stats['mean']==20. and stats['median']==20. and stats['n']==3
    p.loc[1,'cohort']='FY2';assert cohort_stats(p,'v','ok','cohort')['mean'] is None
    p.loc[1,'ok']=False;assert cohort_stats(p,'v','ok')['mean'] is None


def test_peer_optional_nan_identity_does_not_merge_unrelated_companies():
    p=pd.DataFrame({'Ticker':['A','B','C'],'Emisor económico':[float('nan')]*3,'Emisor id':['idA','idB','idC'],'v':[10.,20.,30.],'ok':[True]*3})
    stats=cohort_stats(p,'v','ok')
    assert stats['n']==3 and stats['mean']==20.


def test_quote_keeps_valid_price_when_optional_market_cap_is_missing(tmp_path):
    from seguimiento_servicio import quote
    class Fast:
        def get(self,key):
            if key=='currency':return 'USD'
            raise ConnectionError('optional metadata offline')
    yf=SimpleNamespace(Ticker=lambda ticker:SimpleNamespace(history=lambda **k:pd.DataFrame({'Close':[100.]},index=pd.to_datetime(['2026-11-16'])),fast_info=Fast()))
    result=quote('ABC',Store(tmp_path),yf=yf)
    assert result['price']==100. and result['currency']=='USD'
    assert result['market_cap'] is None and result['shares'] is None and len(result['warnings'])==2


@pytest.mark.parametrize('value,expected',[(20.,'#dcfce7'),(-20.,'#fee2e2'),(0.,''),(None,'')])
def test_discount_colors(value,expected):assert expected in discount_color(value)


def test_search_fuzzy_multiple_confirmable_matches_and_no_download_on_cache(tmp_path):
    calls=[]
    class YF:
        def Search(self,query,**kw):
            calls.append((query,kw));return SimpleNamespace(quotes=[{'symbol':'MSFT','longname':'Microsoft Corporation','quoteType':'EQUITY','exchDisp':'NASDAQ'},
                {'symbol':'MSTR','shortname':'Strategy','quoteType':'EQUITY','exchange':'NMS'},{'symbol':'ETF','quoteType':'ETF'}])
    store=Store(tmp_path);r=search_companies('Micro',store,YF());assert len(r)==2 and r[0]['ticker']=='MSFT'
    assert calls[0][1]['enable_fuzzy_query'] and r[0]['exchange']=='NASDAQ'
    search_companies('Micro',store,YF());assert len(calls)==1 and store.entries()==[]


@pytest.mark.parametrize('ticker',['MSFT','NVDA','MU','AMZN','000660.KS'])
def test_watch_adapter_preserves_all_valuation_tables_and_assumptions(ticker):
    p=deepcopy(archived(ticker));before=json.dumps(p,sort_keys=True)
    r,t=analysis_from_snapshot(p);m=summarize(p,r)
    r2,t2=analysis_from_snapshot(p)
    for name in ['Valoracion EPS PER','Proyeccion EPS','Supuestos EPS PER','Control por metodo']:
        pd.testing.assert_frame_equal(t[name],t2[name])
    assert json.dumps(p,sort_keys=True)==before
    actual=r.metrics[r.metrics['Indicador'].eq('PER TTM')].iloc[0]['Valor']
    assert m['row']['PER actual TTM']==pytest.approx(actual) if pd.notna(actual) else m['row']['PER actual TTM'] is None
    if ticker=='MSFT':assert r.summary['target_1y']==pytest.approx(696.8406273758014)


def test_refresh_quote_uses_cached_financials_preserves_settings_and_failure(tmp_path,monkeypatch):
    import seguimiento_servicio as module
    s=Store(tmp_path,clock=lambda:2000.);service=Service(s,lambda *a,**kw:pytest.fail('No descargar estados frescos'),clock=lambda:2000.)
    p=deepcopy(archived('MSFT'));p['kwargs']['info'].pop('valuation_cik',None)
    a=restore_frame(p['frames']['annual']);a=a.drop(columns=['CIK SEC'],errors='ignore');p['frames']['annual']=frame_payload(a)
    settings={'scenarios':{'Base':{'pe':20.,'growth':.10}},'per_reason':'Prueba persistencia'}
    service.save_capture(p,settings);entry=s.entry('MSFT');entry['metrics']['financial_updated']=1900.;s.save('MSFT',entry['payload'],entry['metrics'])
    monkeypatch.setattr(module,'quote',lambda *a,**k:{'price':500.,'date':str(pd.Timestamp.now(tz='UTC').date()),'currency':'USD','market_cap':None,'shares':None,'source':'fixture fechada'})
    current=service.refresh('MSFT');assert not current['error'] and current['payload']['kwargs']['price']==500.
    assert current['payload']['evidence']['stock_model']['settings']==settings
    previous=current['payload']
    monkeypatch.setattr(module,'quote',lambda *a,**k:(_ for _ in ()).throw(ConnectionError('offline')))
    failed=service.refresh('MSFT');assert failed['payload']==previous and failed['error']


def test_ui_has_first_tab_and_persists_without_network(tmp_path,monkeypatch):
    from streamlit.testing.v1 import AppTest
    store=Store(tmp_path/'list');service=Service(store,None);service.save_capture(archived('MSFT'))
    monkeypatch.setenv('VALUACION_WATCHLIST_DIR',str(store.path))
    initial=tmp_path/'AMZN_inputs.json';initial.write_text(json.dumps(archived('AMZN')),encoding='utf-8')
    monkeypatch.setenv('VALUACION_DASHBOARD_SNAPSHOT',str(initial))
    app=AppTest.from_file(Path(__file__).resolve().parents[1]/'dashboard_app.py').run(timeout=40)
    assert not app.exception and app.tabs[0].label=='Mi seguimiento' and len(app.tabs)==7
    assert len(store.entries())==1
    app.run(timeout=40);assert not app.exception and len(store.entries())==1
    # Abrir la captura seleccionada restaura el análisis de la misma empresa.
    next(b for b in app.button if b.label=='Abrir análisis V7').click().run(timeout=40)
    assert not app.exception and app.session_state['selected_ticker']=='MSFT'
    assert app.session_state['principal_tabs']=='Resumen'
    assert app.session_state['watch_grid_epoch']==1
