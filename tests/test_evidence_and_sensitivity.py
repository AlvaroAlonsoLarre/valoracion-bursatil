from copy import deepcopy
import json
import numpy as np
import pandas as pd
import pytest
from multiple_evidence import validate_multiple,digest,attach_observed_evidence
from tests.multiple_fixtures import with_evidence
from comparables_inteligentes import score_and_filter
from dcf_audit import audit_dcf
from filing_review import review_filings,components_reconciliation


def frame():
    return pd.DataFrame([{'Ticker':t,'Emisor id':t,'PER forward':10.,'EV/EBITDA':8.,
        'PER periodo':'NTM','PER base':'GAAP','EV/EBITDA periodo':'NTM','Perímetro deuda':'Financiera sin leases',
        'Descripción actividad':'enterprise software cloud applications business services',
        'Industria clave':'software','Sector clave':'technology','Margen operativo (%)':20.} for t in ['A','B','C']])


def proven():return with_evidence(frame(),'2026-11-12')

def validate(row,method='PER'):return validate_multiple(row,method,'2026-11-12','GAAP')


def test_labels_are_not_evidence_and_both_ratios_are_reconstructed():
    assert not validate(frame().iloc[0])[0]
    row=proven().iloc[0]
    assert validate(row)[1]==10.
    assert validate(row,'EV/EBITDA')[1]==8.
    broken=deepcopy(row);broken['Evidencia múltiplos']['payload']['forecasts']['PER']['eps']=20
    assert 'Hash' in validate(broken)[2][0]


@pytest.mark.parametrize('change', ['FY1','adjusted','date','currency','ADR','EPS','future','future_forecast'])
def test_incompatible_forward_definitions_stay_blocked(change):
    row=deepcopy(proven().iloc[0]);ev=row['Evidencia múltiplos'];p=ev['payload'];f=p['forecasts']['PER']
    if change=='FY1':f['end']='2027-06-30'
    elif change=='adjusted':f['accounting_basis']='ADJUSTED'
    elif change=='date':p['market']['date']=None
    elif change=='currency':f['currency']='KRW' # No documented FX.
    elif change=='ADR':p['market']['share_basis']='ADR'
    elif change=='EPS':f['eps_definition']='adjusted_eps'
    elif change=='future':p['market']['date']='2026-11-13'
    elif change=='future_forecast':f['date']='2026-11-13'
    ev['sha256']=digest(p)
    assert not validate(row)[0]


def test_ev_lease_and_da_bridge_and_three_issuers_are_required():
    row=deepcopy(proven().iloc[0]);ev=row['Evidencia múltiplos'];ev['payload']['balance']['debt_perimeter']='including_leases';ev['sha256']=digest(ev['payload'])
    assert not validate(row,'EV/EBITDA')[0]
    row=deepcopy(proven().iloc[0]);ev=row['Evidencia múltiplos'];ev['payload']['forecasts']['EV/EBITDA']['da']*=2;ev['sha256']=digest(ev['payload'])
    assert not validate(row,'EV/EBITDA')[0]
    info={'valuation_accounting_basis':'GAAP','industryKey':'software','sectorKey':'technology',
          'longBusinessSummary':'enterprise software cloud applications business services'}
    assert score_and_filter(proven(),'OTHER',target_info=info,as_of='2026-11-12')[1:3]==(10,8)
    assert np.isnan(score_and_filter(proven().head(2),'OTHER',target_info=info,as_of='2026-11-12')[1])


def test_sdk_observation_records_forecasts_without_inventing_ntm_basis_or_quote_date():
    class Ticker:
        def get_earnings_estimate(self,as_dict=False):return {'+1y':{'avg':10.,'numberOfAnalysts':3}}
    class YF:
        def Ticker(self,ticker):return Ticker()
    result,records=attach_observed_evidence(frame().head(1),YF(),'2026-11-12')
    evidence=result.iloc[0]['Evidencia múltiplos']
    assert evidence['sha256']==digest(evidence['payload'])
    assert evidence['payload']['market']['date'] is None
    assert evidence['payload']['forecasts']['PER']['accounting_basis']=='UNKNOWN'
    assert not validate(result.iloc[0])[0] and records[0]['Estado']=='NO_VERIFICADO'


def test_full_sensitivity_is_separate_and_inputs_are_unchanged(model_inputs,build):
    args=dict(model_inputs);annual=args.pop('annual');peers=args.pop('peers')
    original=annual.copy(deep=True);q=args['quarterly'].copy(deep=True)
    base=build();sens,checks=audit_dcf(annual,peers,args,base)
    assert len(sens)==27
    table=sens[sens['Horizonte (años)']==1].set_index('Experimento')['Precio condicional']
    target=base.valuation.query("Escenario=='Base' and `Horizonte (años)`==1 and Método.str.contains('DCF')",engine='python').iloc[0]['Precio objetivo (divisa cotización)']
    assert table['Base']==target
    assert table['WACC +1 pp']<table['Base']<table['WACC -1 pp']
    assert table['CAPEX/ventas +1 pp']<table['Base']<table['CAPEX/ventas -1 pp']
    pd.testing.assert_frame_equal(annual,original);pd.testing.assert_frame_equal(q,args['quarterly'])
    assert not checks['Estado'].eq('VERIFICADO').any()
    assert build().valuation.equals(base.valuation)


def test_shocks_cannot_fill_missing_flows_or_bypass_discount_controls(build,model_inputs):
    q=model_inputs['quarterly'].copy();q.attrs['invalid_flows']=['CAPEX']
    assert build(quarterly=q,sensitivity_shocks={'capex_sales':-.01}).valuation.empty
    assert build(sensitivity_shocks={'terminal_growth':.19}).valuation.empty
    with pytest.raises(ValueError):build(sensitivity_shocks={'target_price':100.})


def test_official_review_excludes_future_filings_and_does_not_call_6k_us_gaap():
    class Response:
        def __init__(self,payload=None,html=''):self.payload=payload;self.content=html.encode();self.text=html
        def raise_for_status(self):pass
        def json(self):return self.payload
    payload={'cik':'2120882','name':'SK hynix Inc.','filings':{'recent':{
        'filingDate':['2026-11-13','2026-10-28'],'form':['6-K','6-K'],
        'accessionNumber':['future','0001193125-26-434994'],'primaryDocument':['future.htm','results.htm']}}}
    urls=[]
    def fetch(url,**kwargs):
        urls.append(url)
        return Response(payload) if url.endswith('.json') else Response(html='<html>Preliminary consolidated earnings. No cash-flow statement.</html>')
    rows=review_filings({'cik':'2120882','period_end':'2026-09-30'},'2026-11-12',requests_get=fetch)
    assert len(rows)==1 and not any('future' in url for url in urls)
    assert rows[0]['Estado']=='SIN_ESTADO_CASHFLOW_EN_DOCUMENTO'


def test_ppe_alone_never_completes_capex_and_da_definitions_stay_separate():
    q=pd.DataFrame([{'CAPEX PP&E':12670e9,'CAPEX intangibles':np.nan,'CAPEX':np.nan,
        'D&A cash flow':4335e9,'D&A operativa':4341e9}],index=pd.to_datetime(['2026-09-30']))
    row=components_reconciliation(q).iloc[0]
    assert not row['CAPEX completo'] and pd.isna(row['Residual CAPEX'])
    assert row['Diferencia D&A CFO-operativa']==-6e9


def test_consolidation_and_ev_nonordinary_claims_need_documentation():
    for field,value in [('consolidation_perimeter','parent_only'),('noncontrolling_interests',1.),('preferred_equity',None)]:
        row=deepcopy(proven().iloc[0]);ev=row['Evidencia múltiplos']
        ev['payload']['balance'][field]=value;ev['sha256']=digest(ev['payload'])
        assert not validate(row,'EV/EBITDA')[0]
    row=deepcopy(proven().iloc[0]);row['Evidencia múltiplos']['payload']=[]
    row['Evidencia múltiplos']['sha256']=digest([])
    assert not validate(row)[0]


def test_replay_sensitivity_uses_snapshot_assumptions_not_ambient_environment(tmp_path,model_inputs,monkeypatch):
    from auditoria_io import write_snapshot
    from ejecutar_analisis import replay
    args=dict(model_inputs);annual=args.pop('annual');peers=args.pop('peers')
    monkeypatch.setenv('VALUACION_WACC','.12')
    target=tmp_path/'inputs.json';write_snapshot(target,annual,peers,args)
    expected,_=audit_dcf(annual,peers,args)
    monkeypatch.setenv('VALUACION_WACC','.20')
    assert replay(target,tmp_path/'replayed')==0
    actual=pd.read_excel(tmp_path/'replayed/valoracion_OTHER_replay.xlsx',sheet_name='DCF sensibilidad')
    np.testing.assert_allclose(actual['Precio condicional'],expected['Precio condicional'],rtol=1e-12)
    import os
    assert os.environ['VALUACION_WACC']=='.20'
