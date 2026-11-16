from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import json
import pandas as pd
import pytest
from auditoria_io import frame_payload,restore_frame
from flujo_acciones import analysis_from_snapshot
from seguimiento_store import Store,TTL
from seguimiento_servicio import Service
from seguimiento_ev import fiscal_history,yahoo_ratio
from seguimiento_metricas import summarize,informative_peers
from seguimiento_incremental import filing_fingerprint,local_stamp,quote_ttl,merge_history
from tests.test_v7_integrada import archived


def fy_payload(split=False,years=1):
    a=pd.DataFrame([{'Fecha cierre fiscal':f'{y}-06-30','EPS diluido':2.,'Acciones diluidas medias':10.,'Acciones fuente presentado':f'{y}-08-01','EPS fuente presentado':f'{y}-08-01',
        'Beneficio neto':20.,'Deuda total':30.,'Efectivo':10.,'Beneficio operativo':80.,'D&A':20.,'Definición D&A':'D&A consolidada','Origen deuda':'Deuda financiera completa','Deuda incluye arrendamientos':False} for y in range(2026-years,2026)],index=range(2026-years,2026))
    dates=pd.to_datetime(a['Fecha cierre fiscal'].tolist()+(['2026-01-15'] if split else []))
    prices=pd.DataFrame({'Close':[10.*(i+1) for i in range(years)]+([10.] if split else []),'Stock Splits':[0.]*years+([2.] if split else [])},index=dates)
    return {'frames':{'annual':frame_payload(a)},'kwargs':{'as_of':'2026-03-01' if split else '2026-07-01','financial_currency':'USD','quote_currency':'USD','info':{}},'historical':{'Precios y splits':frame_payload(prices)}}


def test_fiscal_ev_uses_fy_price_debt_cash_ebitda_and_split_basis():
    p=fy_payload();r=fiscal_history(p)
    # Cap 10 × 10 = 100; EV 100 + 30 − 10 = 120; EBITDA 80 + 20 = 100.
    assert r['last']==pytest.approx(1.2) and r['n']==1
    assert r['rows'][0]['Tipo']=='Histórico aproximado' and r['rows'][0]['Confianza']=='Baja'
    p=fy_payload(split=True);r=fiscal_history(p)
    assert r['rows'][0]['Factor split']==2. and r['last']==pytest.approx(2.2)


@pytest.mark.parametrize('field,value,reason',[('Deuda total',None,'Deuda financiera'),('Efectivo',None,'Efectivo'),('D&A',None,'D&A'),('Definición D&A','D&A y otros ajustes','mezcla'),('Beneficio operativo',-100.,'no positivo')])
def test_incomplete_fiscal_data_never_invents_zero(field,value,reason):
    p=fy_payload();a=restore_frame(p['frames']['annual']);a.loc[2025,field]=value;p['frames']['annual']=frame_payload(a)
    r=fiscal_history(p);assert r['last'] is None and reason in r['rows'][0]['Advertencias']


def test_historical_fx_and_adr_not_current_fx_guesses():
    p=fy_payload();p['kwargs']['quote_currency']='EUR';assert fiscal_history(p)['last'] is None
    p=fy_payload();p['kwargs']['info']={'is_adr':True};assert fiscal_history(p)['last'] is None
    p=fy_payload();p['kwargs'].update(financial_currency='GBP',quote_currency='GBp');assert fiscal_history(p)['last']==pytest.approx(.21)


def test_five_fy_median_does_not_mix_lease_perimeters():
    p=fy_payload(years=5);a=restore_frame(p['frames']['annual']);a.loc[2024:,'Deuda incluye arrendamientos']=True;p['frames']['annual']=frame_payload(a)
    r=fiscal_history(p)
    assert r['n']==2 and r['median']==pytest.approx(4.7) and len(r['rows'])==5


def test_instant_shares_and_pure_da_are_identified_without_claiming_audit():
    p=fy_payload();p['kwargs']['info']['valuation_cik']='123';a=restore_frame(p['frames']['annual']);a['Depreciación y amortización pura']=20.;a['D&A validada']=True;p['frames']['annual']=frame_payload(a)
    facts={'cik':123,'facts':{'us-gaap':{'CommonStockSharesOutstanding':{'units':{'shares':[{'end':'2025-06-30','filed':'2025-08-01','val':12.,'accn':'test-accession'}]}}}}}
    r=fiscal_history(p,facts=facts)
    assert r['last']==pytest.approx(1.4) and 'contrastado' in r['rows'][0]['Tipo']
    assert 'no auditado' in r['rows'][0]['Tipo'] and 'test-accession' in r['rows'][0]['Origen acciones']


def test_provider_ev_is_separate_and_period_is_not_invented():
    r=yahoo_ratio({'enterpriseToEbitda':15.},'2026-11-16')
    assert r['value']==15. and r['period']=='Periodo no informado por proveedor'
    assert 'no reconciliado' in r['confidence']
    assert yahoo_ratio({},'2026-11-16')['value'] is None


def test_informative_peers_allow_one_observation_and_keep_forward_separate():
    p=archived('MSFT');r,_=analysis_from_snapshot(p)
    universe=r.universe.head(1);b=informative_peers(universe,p['kwargs']['info'])
    assert len(b['rows'])==1
    assert b['stats']['PER TTM Yahoo']['n']==1 and b['stats']['PER TTM Yahoo']['mean'] is not None
    assert 'NTM' in b['rows'][0]['Periodo PER'] and 'no acreditado' in b['rows'][0]['Periodo PER']
    assert b['stats']['PER TTM Yahoo']['mean']!=b['stats']['PER forward Yahoo']['mean']
    ticker=universe.iloc[0]['Ticker']
    b=informative_peers(universe,p['kwargs']['info'],{ticker:{'mostRecentQuarter':pd.Timestamp('2026-09-30',tz='UTC').timestamp()}})
    assert b['rows'][0]['Cierre reportado Yahoo']=='2026-09-30'


def test_filings_accessions_amendments_and_incomplete_data():
    d={'filings':{'recent':{'form':['10-K'],'accessionNumber':['0001'],'filingDate':['2026-02-01'],'reportDate':['2025-12-31']}}}
    first=filing_fingerprint(d,'2026-11-16');d['filings']['recent']['accessionNumber'][0]='0002'
    assert first['hash']!=filing_fingerprint(d,'2026-11-16')['hash']
    with pytest.raises(ValueError):filing_fingerprint({'filings':{}},'2026-11-16')


def test_non_sec_revision_detects_quarterly_cashflow_correction(tmp_path,monkeypatch):
    from seguimiento_servicio import check_revision
    import yfinance as yf
    p=deepcopy(archived('000660.KS'));p['kwargs']['info'].pop('valuation_cik',None)
    a=restore_frame(p['frames']['annual']).drop(columns=['CIK SEC'],errors='ignore');p['frames']['annual']=frame_payload(a)
    frame=pd.DataFrame({'2026-09-30':[1.]},index=['fixture'])
    obj=SimpleNamespace(**{k:frame.copy() for k in ['quarterly_income_stmt','income_stmt','quarterly_balance_sheet','balance_sheet','quarterly_cashflow','cashflow']})
    monkeypatch.setattr(yf,'Ticker',lambda *a,**k:obj)
    store=Store(tmp_path);before=check_revision(p,store,True)['hash']
    obj.quarterly_cashflow.iloc[0,0]=2.
    assert check_revision(p,store,True)['hash']!=before


def test_new_sec_accession_refreshes_facts_even_when_daily_cache_is_fresh(tmp_path,monkeypatch):
    from seguimiento_servicio import check_revision,_cik
    from sec_historical import SEC_SUBMISSIONS_URL,SEC_FACTS_URL
    p=archived('MSFT');cik=_cik(p);store=Store(tmp_path);calls=[]
    submission={'cik':int(cik),'filings':{'recent':{'form':['10-K'],'accessionNumber':['old'],'filingDate':['2026-08-01'],'reportDate':['2026-06-30']}}}
    store.put('SEC:'+SEC_SUBMISSIONS_URL.format(cik=cik),submission,-1)
    store.put('SEC:'+SEC_FACTS_URL.format(cik=cik),{'cik':int(cik),'version':'old'},TTL['financial'])
    amended=deepcopy(submission);amended['filings']['recent']['accessionNumber'][0]='amended'
    def get(url,*a,**k):calls.append(url);return amended if 'submissions' in url else {'cik':int(cik),'version':'new'}
    monkeypatch.setattr('sec_historical._get_json',get)
    result=check_revision(p,store)
    assert result['facts']['version']=='new' and len(calls)==2


def test_utc_storage_local_display_and_market_open_boundary():
    epoch=pd.Timestamp('2026-11-16 14:00:00',tz='UTC').timestamp()
    assert '15:00:00' in local_stamp(epoch,'Europe/Madrid') and '14:00:00' in local_stamp(epoch,'UTC')
    assert quote_ttl(epoch,'America/New_York')==1800
    assert quote_ttl(epoch+45*60,'America/New_York')==900
    assert quote_ttl(pd.Timestamp('2026-11-14 12:00',tz='UTC').timestamp(),'America/New_York')==21600


def test_merge_history_overlap_revisions_and_split_detection():
    old=pd.DataFrame({'Close':[100.,101.],'Stock Splits':[0.,0.]},index=pd.to_datetime(['2026-11-12','2026-11-13']))
    new=pd.DataFrame({'Close':[102.,26.],'Stock Splits':[0.,4.]},index=pd.to_datetime(['2026-11-13','2026-11-16']))
    d,split=merge_history(old,new)
    assert len(d)==3 and d.loc['2026-11-13','Close']==102. and split


def isolate_io(monkeypatch,p):
    import seguimiento_servicio as m
    monkeypatch.setattr(m,'quote',lambda *a,**k:{'price':500.,'currency':'USD','date':str(pd.Timestamp.now(tz='UTC').date()),'queried_at':200000.,'source':'fixture','market_cap':None,'shares':None})
    monkeypatch.setattr(m,'provider_profile',lambda *a,**k:{'info':{},'queried_at':200000.})
    monkeypatch.setattr(m,'update_history',lambda *a,**k:(restore_frame(p['historical']['Precios y splits']),False,'reutilizado'))
    monkeypatch.setattr(m,'refresh_validated_peers',lambda p,*a:(restore_frame(p['frames']['peers']),[]))
    return m


def test_unchanged_filings_reuse_financials_but_revision_loads_v7_once(tmp_path,monkeypatch):
    p=deepcopy(archived('MSFT'));store=Store(tmp_path,clock=lambda:200000.)
    calls=[]
    def load(*a,**k):calls.append(True);return json.dumps(p)
    service=Service(store,load,clock=lambda:200000.);service.save_capture(p,{'scenarios':{'Base':{'pe':20.}},'per_reason':'Persistencia'})
    entry=store.entry('MSFT');entry['metrics'].update(financial_updated=1.,financial_checked=1.,revision_hash='same',peers_updated=199999.)
    store.save('MSFT',entry['payload'],entry['metrics']);m=isolate_io(monkeypatch,p)
    revision={'hash':'same','filings':[],'source':'fixture','facts':None};monkeypatch.setattr(m,'check_revision',lambda *a,**k:revision)
    result=service.refresh('MSFT');assert calls==[] and not result['error']
    result['metrics']['financial_checked']=1.;store.save('MSFT',result['payload'],result['metrics'])
    revision['hash']='amended-same-FY';result=service.refresh('MSFT')
    assert len(calls)==1 and result['payload']['evidence']['stock_model']['settings']['scenarios']['Base']['pe']==20.
    assert result['metrics']['revision_hash']=='amended-same-FY'


def test_new_company_complete_analysis_and_partial_sources_remain_usable(tmp_path,monkeypatch):
    p=deepcopy(archived('MSFT'));store=Store(tmp_path);store.add('MSFT','Microsoft');calls=[]
    m=isolate_io(monkeypatch,p)
    monkeypatch.setattr(m,'check_revision',lambda *a,**k:(_ for _ in ()).throw(ConnectionError('SEC offline')))
    service=Service(store,lambda *a,**k:(calls.append(True) or json.dumps(p)))
    result=service.refresh('MSFT')
    assert len(calls)==1 and result['payload'] is not None and result['error']
    assert result['metrics']['row']['Precio']==500. and len(result['metrics']['targets'])>=6


def test_quote_tail_reuses_existing_request_without_history_download(tmp_path,monkeypatch):
    from seguimiento_servicio import update_history
    p=archived('MSFT');old=restore_frame(p['historical']['Precios y splits']);date=old.index.max()
    tail=pd.DataFrame({'Close':[999.],'Stock Splits':[0.]},index=[date])
    import yfinance as yf
    monkeypatch.setattr(yf,'Ticker',lambda *a:pytest.fail('No consultar otra vez el histórico'))
    new,split,state=update_history('MSFT',p,Store(tmp_path),str(date.date()),quote_tail=frame_payload(tail))
    assert new.loc[date,'Close']==999. and not split and 'reutilizados' in state


def test_export_import_is_atomic_preserves_settings_and_extended_quarters(tmp_path):
    store=Store(tmp_path/'original');p=deepcopy(archived('MSFT'));settings={'scenarios':{'Base':{'pe':20.}},'per_reason':'Restaurar — á'}
    from tests.test_seguimiento import facts_from_quarters
    from seguimiento_metricas import quarter_series
    series=quarter_series(pd.DataFrame(),'2026-02-01',facts_from_quarters())
    p['historical']['Seguimiento neto trimestral']=frame_payload(series);Service(store).save_capture(p,settings)
    backup=json.dumps(store.export(),ensure_ascii=False);target=Store(tmp_path/'Álvaro 日本')
    assert target.import_list(backup)==1
    assert target.meta('last_table_update')>0
    e=target.entry('MSFT');assert e['payload']['evidence']['stock_model']['settings']==settings
    assert len(e['metrics']['quarters'])==20 and e['metrics']['financial_updated']==0
    bad=store.export();bad['companies'].append({'ticker':'OTHER','payload':p})
    with pytest.raises(ValueError):target.import_list(json.dumps(bad))
    assert len(target.entries())==1


def test_official_fy_shares_survive_import_and_manual_settings_without_network(tmp_path):
    p=deepcopy(archived('MSFT'));a=restore_frame(p['frames']['annual']);row=a.iloc[-1]
    cik=p['kwargs']['info'].get('valuation_cik') or row['CIK SEC']
    p['evidence']['watch_fy_shares']={'cik':str(cik).split('.')[0],'facts':{'us-gaap':{'CommonStockSharesOutstanding':{'units':{'shares':[
        {'end':str(pd.Timestamp(row['Fecha cierre fiscal']).date()),'filed':str(pd.Timestamp(row['Acciones fuente presentado']).date()),'val':float(row['Acciones diluidas medias'])*1.05,'accn':'test-only-official-shares'}]}}}}}
    store=Store(tmp_path/'original');service=Service(store);service.save_capture(p)
    before=store.entry('MSFT')['metrics']['ev_fy']['last'];assert before is not None
    p2=deepcopy(p);p2['evidence'].pop('watch_fy_shares')
    assert fiscal_history(p2)['last']!=before
    service.save_settings('MSFT',{'scenarios':{'Base':{'pe':20.}},'per_reason':'Sensibilidad manual'})
    assert store.entry('MSFT')['metrics']['ev_fy']['last']==before
    target=Store(tmp_path/'restored');target.import_list(json.dumps(store.export()))
    assert target.entry('MSFT')['metrics']['ev_fy']['last']==before
    assert 'test-only-official-shares' in target.entry('MSFT')['metrics']['ev_fy']['rows'][-1]['Origen acciones']


def test_single_chart_saved_company_selection_and_no_network_on_rerun(tmp_path,monkeypatch):
    from streamlit.testing.v1 import AppTest
    store=Store(tmp_path);service=Service(store)
    service.save_capture(archived('MSFT'));service.save_capture(archived('NVDA'))
    monkeypatch.setenv('VALUACION_WATCHLIST_DIR',str(store.path))
    monkeypatch.setattr('seguimiento_ui.Service.refresh',lambda *a,**k:pytest.fail('La selección no descarga fuentes'))
    monkeypatch.setattr('seguimiento_ui.search_companies',lambda *a,**k:pytest.fail('La selección no busca empresas'))
    app=AppTest.from_file(Path(__file__).resolve().parents[1]/'dashboard_app.py').run(timeout=40)
    assert not app.exception and len([c for c in app.get('vega_lite_chart') if json.loads(c.proto.spec).get('mark',{}).get('type')=='line'])==1
    next(s for s in app.selectbox if s.label=='Empresa del gráfico').set_value('NVDA').run(timeout=40)
    assert not app.exception and app.session_state['selected_ticker']=='NVDA' and app.session_state['principal_tabs']=='Mi seguimiento'
    app.run(timeout=40);assert not app.exception and len([c for c in app.get('vega_lite_chart') if json.loads(c.proto.spec).get('mark',{}).get('type')=='line'])==1
    assert store.entry('MSFT')['payload']['evidence']['stock_model']['settings']==archived('MSFT')['evidence']['stock_model']['settings']


@pytest.mark.parametrize('ticker',['MSFT','NVDA','MU','AMZN','META','GOOG','GOOGL','NFLX','JNJ','JPM','000660.KS','SNDK','SPCX'])
def test_informative_overlays_never_change_formal_valuations(ticker):
    p=deepcopy(archived(ticker));r,t=analysis_from_snapshot(p)
    p['evidence']['watch_provider']={'info':{'enterpriseToEbitda':1.,'trailingPE':1.,'forwardPE':2.},'queried_at':123.}
    p['evidence']['watch_peer_profiles']={'FAKE':{'info':{'trailingPE':1.,'enterpriseToEbitda':1.}}}
    r2,t2=analysis_from_snapshot(p);summarize(p,r2)
    for name in ['Valoracion EPS PER','Proyeccion EPS','Supuestos EPS PER','Control por metodo']:pd.testing.assert_frame_equal(t[name],t2[name])
