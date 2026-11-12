"""Regresión de decisiones y fórmulas; fixtures exclusivamente sintéticas."""
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import numpy as np
import pandas as pd
import pytest
from analisis_acciones import build_stock_analysis,evaluate_position,validate_settings
from historico_acciones import historical_multiples,historical_statistics
from flujo_acciones import stock_tables,analysis_from_snapshot,excel_bytes
from auditoria_io import write_snapshot,clean,assess,frame_payload
from comparables_ttm import validate_ttm_evidence
from multiple_evidence import digest


@pytest.fixture
def stock_inputs():
    years=list(range(2016,2026));revenue=np.array([400/(1.08)**(2025-y) for y in years])
    a=pd.DataFrame({'Ingresos':revenue,'Beneficio operativo':revenue*.20,'Beneficio antes de impuestos':revenue*.18,
        'Impuestos':revenue*.045,'Beneficio neto':revenue*.135,'Beneficio neto común':revenue*.135,
        'EPS diluido':revenue*.135/10,'Acciones diluidas medias':[10.]*10,
        'Flujo de caja operativo':revenue*.20,'CAPEX':revenue*.07,'D&A':revenue*.04,
        'Flujo de caja libre':revenue*.13,'Deuda total':[50.]*10,'Deuda neta':[20.]*10,
        'Gastos por intereses':[8.]*10,'Tasa fiscal':[.25]*10,
        'Fecha cierre fiscal':[pd.Timestamp(y,12,31) for y in years],
        'EPS fuente presentado':[str(y+1)+'-02-01' for y in years],
        'Acciones fuente presentado':[str(y+1)+'-02-01' for y in years]},index=years)
    q=pd.DataFrame({c:[a.loc[2025,c]/4]*4 for c in a if c not in ['Fecha cierre fiscal','EPS fuente presentado','Acciones fuente presentado']},index=pd.date_range('2025-03-31',periods=4,freq='QE'))
    q['Acciones diluidas medias']=10.;q['Deuda neta']=20.;q['Deuda total']=50.
    # Cierre observado el día hábil anterior; no utilizar una cotización futura.
    price_rows={pd.bdate_range(end=pd.Timestamp(y,12,31),periods=1)[0]:[a.loc[y,'EPS diluido']*15,0.] for y in years}
    prices=pd.DataFrame.from_dict(price_rows,orient='index',columns=['Close','Stock Splits'])
    history=historical_multiples(a,prices,'USD','USD','2026-02-02')
    return dict(annual=a,peers=pd.DataFrame(),quarterly=q,history=history,price=100.,market_cap=1000.,shares_outstanding=10.,
        financial_currency='USD',quote_currency='USD',fx=1.,as_of='2026-02-02',fiscal_end_date='2025-12-31',ticker='TEST',
        info={'beta':1.,'sector':'Technology','valuation_quote_date':'2026-02-02','valuation_accounting_basis':'US_GAAP'},source='Fixture sintética')


def test_eps_formula_from_business_and_primary_is_not_a_dcf(stock_inputs):
    r=build_stock_analysis(**stock_inputs)
    values=r.valuation.query("Método=='EPS × PER' and Escenario=='Base'").set_index('Horizonte (años)')
    # Ventas 400 × 1.08; EBIT 20%, resultado financiero -2%, fiscalidad 25%, 10 acciones.
    assert values.loc[1,'EPS aplicado']==pytest.approx((432*.20-432*.02)*.75/10)
    assert values.loc[1,'Precio objetivo']==pytest.approx(87.48)
    assert values.loc[3,'Precio objetivo']==pytest.approx(400*1.08**3*.18*.75/10*15)
    assert r.summary['fair_value']==pytest.approx(87.48/1.1)
    assert r.summary['confidence']=='Baja'
    assert len(r.valuation[r.valuation['Método'].eq('EPS × PER')])==6
    assert r.methods.set_index('Método').loc['DCF','Estado']=='NO_EJECUTADO'


def test_capex_da_missing_and_optional_failure_do_not_block_eps(stock_inputs):
    q=stock_inputs['quarterly'].copy();q.attrs['invalid_flows']=['CAPEX','D&A']
    args={**stock_inputs,'quarterly':q};r=build_stock_analysis(**args)
    assert r.summary['available_targets']==6
    assert r.methods.set_index('Método').loc['Precio/FCF','Estado']=='NO_REPRESENTATIVO'
    a=args.pop('annual');p=args.pop('peers');h=args.pop('history')
    _,tables=stock_tables(a,p,args,h,{'advanced':True})
    assert assess(tables)['exit_code']==0
    assert tables['Estado metodos'].set_index('Método').loc['DCF','Estado']=='BLOQUEO'
    assert tables['Control opcionales']['Estado'].eq('BLOQUEO').any()


@pytest.mark.parametrize('problem',['gap','fx','cap','negative_eps','missing_tax','missing_diluted'])
def test_critical_requirements_are_retained(stock_inputs,problem):
    args=deepcopy(stock_inputs)
    if problem=='gap':args['quarterly']=args['quarterly'].iloc[[0,2,3]]
    elif problem=='fx':args['fx']=np.nan
    elif problem=='cap':args['market_cap']=3000.
    elif problem=='negative_eps':args['quarterly']['EPS diluido']=-1.
    elif problem=='missing_tax':args['annual']['Impuestos']=np.nan
    else:
        args['quarterly']['Acciones diluidas medias']=np.nan;args['annual']['Acciones diluidas medias']=np.nan
    r=build_stock_analysis(**args)
    assert not r.summary['primary_available']
    assert r.controls['Estado'].eq('BLOQUEO').any()


def test_missing_eps_can_use_sign_of_net_income_but_not_invent_eps(stock_inputs):
    args=deepcopy(stock_inputs);args['quarterly']['EPS diluido']=np.nan
    r=build_stock_analysis(**args)
    assert r.summary['primary_available']
    assert r.base_ttm.set_index('Campo').loc['EPS diluido','Base TTM (unidades)'] is np.nan or pd.isna(r.base_ttm.set_index('Campo').loc['EPS diluido','Base TTM (unidades)'])
    args['quarterly']['Beneficio neto']=-100.
    assert not build_stock_analysis(**args).summary['primary_available']


def test_forward_per_uses_eps_after_target_not_trailing_eps(stock_inputs):
    settings={'per_basis':'NTM','per_reason':'Hipótesis sintética NTM, no consenso',
              'scenarios':{name:{'pe':15.} for name in ['Pesimista','Base','Optimista']}}
    r=build_stock_analysis(**stock_inputs,settings=settings)
    row=r.valuation.query("Método=='EPS × PER' and Escenario=='Base' and `Horizonte (años)`==1").iloc[0]
    assert row['Precio objetivo']==pytest.approx(400*1.08**2*.18*.75/10*15)
    assert 'Año 2' in row['Periodo EPS'] and row['Periodo PER']=='NTM'
    with pytest.raises(ValueError):build_stock_analysis(**stock_inputs,settings={'per_basis':'NTM','per_reason':'Manual','scenarios':{'Base':{'pe':15.}}})


def test_quote_does_not_calibrate_projection_or_multiple(stock_inputs):
    a=build_stock_analysis(**stock_inputs)
    b=build_stock_analysis(**{**stock_inputs,'price':200.,'market_cap':2000.})
    pd.testing.assert_frame_equal(a.assumptions,b.assumptions)
    np.testing.assert_allclose(a.valuation['Precio objetivo'],b.valuation['Precio objetivo'])
    assert a.summary['upside_1y']!=b.summary['upside_1y']


def test_adr_requires_documented_bridge_and_fx(stock_inputs):
    args={**stock_inputs,'info':{**stock_inputs['info'],'is_adr':True},'fx':1.2}
    assert not build_stock_analysis(**args).summary['primary_available']
    r=build_stock_analysis(**args,settings={'adr':{'ordinary_per_quote_share':2.,'source':'https://example.invalid/synthetic/ratio','date':'2026-01-01'}})
    assert r.summary['target_1y']==pytest.approx(87.48*1.2*2)


def test_financial_and_reit_treatment_is_explicit(stock_inputs):
    financial=deepcopy(stock_inputs);financial['info']['sector']='Financial Services';financial['annual']['Beneficio operativo']=np.nan
    r=build_stock_analysis(**financial,settings={'advanced':True})
    assert r.summary['primary_available'] and r.summary['profit_model']=='PBT directo'
    assert r.summary['Atractivo']=='Revisión sectorial'
    assert r.methods.set_index('Método').loc['DCF','Estado']=='NO_EJECUTADO'
    reit={**stock_inputs,'info':{'industry':'REIT - Retail'}}
    r=build_stock_analysis(**reit)
    assert not r.summary['primary_available'] and 'FFO' in r.methods.iloc[0]['Detalle'] or 'REIT' in r.methods.iloc[0]['Detalle']


def test_no_reported_operating_income_uses_declared_pbt_not_fabricated_ebit(stock_inputs):
    args=deepcopy(stock_inputs);args['annual']['Beneficio operativo']=np.nan
    r=build_stock_analysis(**args)
    assert r.summary['profit_model']=='PBT directo' and r.summary['primary_available']
    assert r.summary['target_1y']==pytest.approx(87.48)
    assert any(r.controls['Comprobación'].eq('Margen PBT directo'))


def test_price_fcf_is_equity_multiple_and_representativeness_gate(stock_inputs):
    r=build_stock_analysis(**stock_inputs)
    row=r.valuation[r.valuation['Método'].eq('Precio/FCF')].iloc[0]
    # Precio/FCF histórico, no (precio*acciones + deuda neta)/FCF.
    expected=stock_inputs['history']['Precio/FCF histórico'].tail(5).median()*(400*.13/10)
    assert row['Precio objetivo']==pytest.approx(expected)
    q=stock_inputs['quarterly'].copy();q['Flujo de caja operativo']*=2.;q['Flujo de caja libre']=q['Flujo de caja operativo']-q['CAPEX']
    assert build_stock_analysis(**{**stock_inputs,'quarterly':q}).methods.set_index('Método').loc['Precio/FCF','Estado']=='NO_REPRESENTATIVO'


def test_historical_windows_splits_and_discontinued_scope(stock_inputs):
    a=stock_inputs['annual'].tail(2).copy();dates=pd.to_datetime(['2024-12-31','2025-06-30','2025-12-31'])
    prices=pd.DataFrame({'Close':[a.loc[2024,'EPS diluido']*15/2,100.,a.loc[2025,'EPS diluido']*15],
                        'Stock Splits':[0.,2.,0.]},index=dates)
    a.loc[2024,'EPS fuente presentado']='2025-02-01';a.loc[2024,'Acciones fuente presentado']='2025-02-01'
    h=historical_multiples(a,prices,'USD','USD','2026-02-02')
    assert h.iloc[0]['PER histórico']==pytest.approx(15.)
    a['EPS fuente presentado']=None;a['Acciones fuente presentado']=None
    assert pd.isna(historical_multiples(a,prices,'USD','USD','2026-02-02').iloc[0]['PER histórico'])
    assert historical_multiples(a,prices,'EUR','USD','2026-02-02')['PER histórico'].isna().all()
    a=stock_inputs['annual'].copy();a['EPS continuado diluido']=a['EPS diluido']/2;a['Beneficio neto continuado']=a['Beneficio neto']/2
    market=pd.DataFrame({'Close':[a.iloc[-1]['EPS diluido']*15],'Stock Splits':[0.]},index=[pd.Timestamp('2025-12-31')])
    h=historical_multiples(a.tail(1),market,'USD','USD','2026-02-02')
    assert h.iloc[-1]['PER histórico']==pytest.approx(30.) and h.iloc[-1]['Definición EPS histórico']=='Continuado diluido'
    stats=historical_statistics(stock_inputs['annual'],stock_inputs['history'])
    assert stats.query("Indicador=='PER histórico'")['Observaciones'].tolist()==[5,10]


def ttm_row():
    q=pd.DataFrame({'eps':[1.]*4,'shares':[10.]*4,'common_net':[10.]*4,'revenue':[50.]*4,'normalized_net':[10.]*4},index=pd.date_range('2025-03-31',periods=4,freq='QE'))
    p={'issuer_id':'SYNTHETIC','accounting_basis':'US_GAAP','basis_source':'https://data.sec.gov/api/xbrl/companyfacts/CIK0000000001.json',
       'share_basis':'ordinary','financial_currency':'USD','quote_currency':'USD','quote_date':'2026-01-30','price':40.,'quarters':frame_payload(q)}
    return {'Ticker':'TEST','Emisor id':'SYNTHETIC','Evidencia TTM':{'schema':'reported-ttm-v1','payload':p,'sha256':digest(p),'retrieved_at':'2026-02-02'}}


def test_ttm_evidence_is_separate_and_rejects_period_profit_currency_mismatch():
    row=ttm_row();assert validate_ttm_evidence(row,'2026-02-02','2025-12-31','US_GAAP')[1]==pytest.approx(10.)
    for mutation in ['currency','end','definition','profit','hash']:
        row=deepcopy(ttm_row());p=row['Evidencia TTM']['payload'];target='2025-12-31'
        if mutation=='currency':p['financial_currency']='KRW'
        elif mutation=='end':target='2025-09-30'
        elif mutation=='definition':p['accounting_basis']='ADJUSTED'
        elif mutation=='profit':p['quarters']['data'][0][2]=30.
        else:p['price']=100.
        if mutation!='hash':row['Evidencia TTM']['sha256']=digest(p)
        assert not validate_ttm_evidence(row,'2026-02-02',target,'US_GAAP')[0]


def test_uncertainty_and_position_change_signals_not_prices():
    summary={'fair_value':150.,'price':100.,'annual_return_3y':.20,'pessimistic_1y':110.,'scenario_spread':.1,'confidence':'Media','sector_type':'OPERATIVA'}
    low=evaluate_position(summary,{'uncertainty_penalty':0.},position={'shares':1.,'portfolio_value':10000.,'cost_price':70.})
    high=evaluate_position(summary,{'uncertainty_penalty':.30},position={'shares':1.,'portfolio_value':10000.})
    assert low['Decisión']=='Ampliar' and high['Decisión']=='Mantener'
    assert evaluate_position(summary,{'uncertainty_penalty':0.},position={'shares':20.,'portfolio_value':10000.})['Decisión']=='Reducir'
    assert evaluate_position(summary)['Decisión']=='Sin señal'
    assert summary['fair_value']==150.


def test_settings_reject_invalid_fields_nonfinite_and_unjustified_pe():
    for s in [{'scenarios':{'Base':{'pe':20}}},{'scenarios':{'Base':{'growth':float('nan')}}},{'target_price':200},
              {'policy':{'margin_of_safety':-1}},{'scenarios':{'Base':{'tax':True}}}]:
        with pytest.raises(ValueError):validate_settings(s)


def test_snapshot_cli_excel_json_and_recalculation_agree(tmp_path,stock_inputs):
    a=stock_inputs.copy();annual=a.pop('annual');peers=a.pop('peers');history=a.pop('history')
    target=tmp_path/'inputs.json';write_snapshot(target,annual,peers,a,{'Referencia histórica auditada':history},evidence={'stock_model':{'version':'stock-dashboard-v1','settings':{}}})
    p=json.loads(target.read_text());result,tables=analysis_from_snapshot(p)
    process=subprocess.run([sys.executable,'ejecutar_analisis.py','--snapshot',str(target),'--outdir',str(tmp_path/'out')],text=True,capture_output=True)
    assert process.returncode==0,process.stderr
    summary=json.loads((tmp_path/'out/TEST_resumen.json').read_text())
    workbook=pd.read_excel(tmp_path/'out/valoracion_TEST_replay.xlsx',sheet_name=None)
    np.testing.assert_allclose(workbook['Valoracion EPS PER']['Precio objetivo'],result.valuation['Precio objetivo'])
    np.testing.assert_allclose([r['Precio objetivo'] for r in summary['Valoracion EPS PER']],result.valuation['Precio objetivo'])
    assert summary['auditoria']['objetivos_principales_disponibles']==6
    assert 'Registro valoraciones' in workbook and 'Estado metodos' in workbook


def test_fiscal_labels_handle_52_53_week_year_without_calendar_duplicates():
    from sec_historical import fiscal_year_label
    assert [fiscal_year_label(d) for d in ['2020-01-01','2021-01-03','2022-01-02','2023-01-01','2023-12-31','2024-12-29']]==[2019,2020,2021,2022,2023,2024]
    assert fiscal_year_label('2026-01-31')==2026


def test_diluted_conflicting_duplicate_is_not_replaced_by_an_annual_value(stock_inputs):
    q=stock_inputs['quarterly'].copy();last=q.tail(1).copy();last['Acciones diluidas medias']=99.
    duplicate=pd.concat([q,last])
    result=build_stock_analysis(**{**stock_inputs,'quarterly':duplicate})
    assert not result.summary['primary_available']
    assert result.controls.query("Comprobación=='Acciones diluidas'")['Estado'].iloc[0]=='BLOQUEO'


def test_pence_unit_is_explicit_and_does_not_change_the_pe(stock_inputs):
    from modelo_fundamental import fx_rate
    assert fx_rate('GBP','GBp')[0]==100.
    assert fx_rate('GBp','GBP')[0]==.01
    assert fx_rate('USD','GBp',lambda pair:.8 if pair=='USDGBP=X' else np.nan)[0]==80.
    a=stock_inputs['annual'];price_rows={pd.bdate_range(end=pd.Timestamp(y,12,31),periods=1)[0]:[a.loc[y,'EPS diluido']*15*100,0.] for y in a.index}
    prices=pd.DataFrame.from_dict(price_rows,orient='index',columns=['Close','Stock Splits'])
    history=historical_multiples(a,prices,'GBP','GBp','2026-02-02')
    np.testing.assert_allclose(history['PER histórico'],15.)


def test_source_concepts_for_continuing_eps_and_calendar_years_are_real():
    from sec_historical import sec_fact
    payload={'facts':{'us-gaap':{'IncomeLossFromContinuingOperationsPerDilutedShare':{'units':{'USD/shares':[{'start':'2023-01-02','end':'2023-12-31','val':5.22,'form':'10-K','filed':'2024-02-20'}]}}}}}
    fact=sec_fact(payload,['IncomeLossFromContinuingOperationsPerDilutedShare'],'2023-12-31',currency='USD',mode='eps')
    assert fact['value']==5.22


def test_optional_worker_does_not_mutate_shared_session_environment(stock_inputs,monkeypatch):
    args=stock_inputs.copy();a=args.pop('annual');p=args.pop('peers');h=args.pop('history')
    monkeypatch.setenv('VALUACION_WACC','.20')
    _,tables=stock_tables(a,p,args,h,{'advanced':True,'optional_assumptions':{'wacc':.10,'terminal_growth':.025}})
    assert os.environ['VALUACION_WACC']=='.20'
    r=tables['Valoracion opcional']
    assert r[r['Escenario'].eq('Base')]['WACC (%)'].iloc[0]==pytest.approx(10.)


def test_dashboard_has_six_tabs_exports_and_recalculates_policy(tmp_path,stock_inputs,monkeypatch):
    from streamlit.testing.v1 import AppTest
    args=stock_inputs.copy();a=args.pop('annual');p=args.pop('peers');h=args.pop('history')
    path=tmp_path/'capture.json';write_snapshot(path,a,p,args,{'Referencia histórica auditada':h},evidence={'stock_model':{'version':'stock-dashboard-v1','settings':{}}})
    monkeypatch.setenv('VALUACION_DASHBOARD_SNAPSHOT',str(path))
    at=AppTest.from_file(Path(__file__).resolve().parents[1]/'dashboard_app.py').run(timeout=40)
    assert not at.exception
    assert [t.label for t in at.tabs]==['Resumen','Histórico','Trimestrales','Comparables','Valoración','Datos y auditoría']
    assert len(at.metric)==4 and at.metric[0].value=='100.00'
    # Retorno exigido afecta al valor razonable descontado, no al precio futuro EPS/PER.
    before=at.metric[1].value
    control=next(n for n in at.number_input if n.label=='Retorno exigido')
    control.set_value(20.)
    next(b for b in at.button if b.label=='Aplicar criterios y posición').click().run(timeout=40)
    assert not at.exception and at.metric[1].value!=before
    assert at.metric[2].value=='-12.5 %'


def test_stale_price_blocks_comparison_not_the_future_eps(stock_inputs):
    args=deepcopy(stock_inputs);args['info']['valuation_quote_date']='2025-01-01'
    r=build_stock_analysis(**args)
    assert r.summary['primary_available'] and np.isnan(r.summary['upside_1y'])
    assert r.summary['Atractivo']=='No evaluable'


def test_sec_history_filters_future_filings_before_extracting(monkeypatch):
    import sec_historical as sec
    years=[2024,2025,2026]
    def concept(values,unit='USD'):
        return {'units':{unit:[{'start':f'{y}-01-01','end':f'{y}-12-31','val':v,'form':'10-K','filed':f'{y+1}-02-01','accn':str(y)} for y,v in zip(years,values)]}}
    facts={'entityName':'SYNTHETIC','facts':{'us-gaap':{'Revenues':concept([100,120,999]),'NetIncomeLoss':concept([10,12,99]),
        'EarningsPerShareDiluted':concept([1,1.2,9.9],'USD/shares'),'WeightedAverageNumberOfDilutedSharesOutstanding':concept([10,10,10],'shares')}}}
    submissions={'filings':{'recent':{'form':['10-K']*3,'filingDate':[f'{y+1}-02-01' for y in years],
        'reportDate':[f'{y}-12-31' for y in years],'accessionNumber':['2024','2025','2026'],'primaryDocument':['x.htm']*3}}}
    def fetch(url,ua):
        if 'company_tickers' in url:return {'0':{'ticker':'SYNTHETIC','cik_str':1,'title':'SYNTHETIC'}}
        return deepcopy(facts if 'companyfacts' in url else submissions)
    monkeypatch.setattr(sec,'_get_json',fetch);monkeypatch.setattr(sec,'_inline_fact',lambda *a,**k:None)
    a,audit,meta=sec.download_sec_annual_history('SYNTHETIC',as_of='2026-02-02')
    assert list(a.index)==[2024,2025] and a.loc[2025,'Ingresos']==120
    assert not audit['Presentado'].astype(str).str.startswith('2027').any()
    assert meta['Base contable']=='US_GAAP'


def test_automatic_ntm_requires_three_independent_verified_peers(stock_inputs):
    from tests.multiple_fixtures import with_evidence
    peers=pd.DataFrame([{'Ticker':x,'Emisor id':x,'PER forward':20.,'EV/EBITDA':8.,'PER periodo':'NTM','PER base':'US_GAAP',
        'EV/EBITDA periodo':'NTM','Perímetro deuda':'Financiera sin leases','Margen operativo (%)':20.,
        'Descripción actividad':'enterprise software cloud applications business services','Industria clave':'software','Sector clave':'technology'} for x in ['A','B','C']])
    peers=with_evidence(peers,'2026-02-02',basis='US_GAAP')
    info={**stock_inputs['info'],'industryKey':'software','sectorKey':'technology','longBusinessSummary':'enterprise software cloud applications business services'}
    result=build_stock_analysis(**{**stock_inputs,'peers':peers,'info':info})
    row=result.valuation.query("Método=='EPS × PER' and Escenario=='Base' and `Horizonte (años)`==1").iloc[0]
    assert row['Periodo PER']=='NTM' and row['PER aplicado']==20.
    assert row['Precio objetivo']==pytest.approx(400*1.08**2*.18*.75/10*20)
    insufficient=build_stock_analysis(**{**stock_inputs,'peers':peers.head(2),'info':info})
    row=insufficient.valuation.query("Método=='EPS × PER' and Escenario=='Base' and `Horizonte (años)`==1").iloc[0]
    assert row['Periodo PER']=='TTM' and row['Confianza']=='Baja' and row['PER aplicado']==pytest.approx(15.)


def test_negative_projected_earnings_do_not_generate_a_price_or_tax_credit(stock_inputs):
    result=build_stock_analysis(**stock_inputs,settings={'scenarios':{'Pesimista':{'margin':-.10}}})
    loss=result.projected[result.projected['Escenario'].eq('Pesimista')]
    assert (loss['Beneficio común normalizado']<0).all() and loss['Impuestos'].eq(0).all()
    assert result.valuation.query("Método=='EPS × PER' and Escenario=='Pesimista'")['Precio objetivo'].isna().all()
    assert result.summary['Atractivo']=='No evaluable'


def test_replay_keeps_discovered_candidates_without_inventing_financial_data(tmp_path,stock_inputs):
    args=stock_inputs.copy();annual=args.pop('annual');peers=args.pop('peers');history=args.pop('history')
    path=tmp_path/'capture.json'
    write_snapshot(path,annual,peers,args,{'Referencia histórica auditada':history},evidence={
        'stock_model':{'version':'stock-dashboard-v1','settings':{}},
        'peer_discovery':[{'Ticker':'NO_DATA','Origen candidatos':'Descubrimiento sintético','Estado descarga':'Sin datos'}]})
    result,tables=analysis_from_snapshot(json.loads(path.read_text()))
    row=tables['Universo comparables'].iloc[0]
    assert row['Ticker']=='NO_DATA' and not row['Elegible'] and row['Observación']=='Sin descarga/cobertura'
    assert 'PER TTM verificado' not in row or pd.isna(row['PER TTM verificado'])
    assert result.summary['target_1y']==pytest.approx(87.48)


def test_unavailable_pe_does_not_hide_an_available_optional_dcf(stock_inputs):
    args=stock_inputs.copy();annual=args.pop('annual');peers=args.pop('peers');args.pop('history')
    result,tables=stock_tables(annual,peers,args,pd.DataFrame(),{'advanced':True})
    audit=assess(tables)
    assert not result.summary['primary_available']
    assert audit['exit_code']==0 and audit['objetivos_principales_disponibles']==0
    assert audit['objetivos_fundamentales_disponibles']==9
    registry=tables['Registro valoraciones']
    assert registry[registry['scenario_type'].eq('opcional_dcf')]['price'].notna().sum()==9
    assert result.summary['optional_available']==9 and pd.isna(result.summary['fair_value'])


def test_cli_edited_snapshot_and_optional_export_remain_json_serializable(tmp_path,stock_inputs):
    from auditoria_io import read_snapshot
    args=stock_inputs.copy();annual=args.pop('annual');peers=args.pop('peers');history=args.pop('history')
    snapshot=tmp_path/'inputs.json';write_snapshot(snapshot,annual,peers,args,{'Referencia histórica auditada':history},
        evidence={'stock_model':{'version':'stock-dashboard-v1','settings':{}}})
    original=snapshot.read_bytes()
    _,_,_,raw=read_snapshot(snapshot)
    json.dumps(raw,allow_nan=False) # El lector no inserta un DataFrame dentro del JSON original.
    overrides=tmp_path/'assumptions.json';overrides.write_text(json.dumps({'scenarios':{'Base':{'growth':.10}}}))
    process=subprocess.run([sys.executable,'ejecutar_analisis.py','--snapshot',str(snapshot),'--advanced','--assumptions',str(overrides),'--outdir',str(tmp_path/'edited')],capture_output=True,text=True)
    assert process.returncode==0,process.stdout+process.stderr
    assert snapshot.read_bytes()==original
    exported=json.loads((tmp_path/'edited/TEST_inputs.json').read_text())
    assert exported['evidence']['stock_model']['settings']['advanced']
    assert exported['evidence']['stock_model']['settings']['scenarios']['Base']['growth']==.10
    summary=json.loads((tmp_path/'edited/TEST_resumen.json').read_text())
    assert summary['auditoria']['objetivos_principales_disponibles']==6
    assert any(r['method_id']=='dcf_fcff_future' and r['price'] is not None for r in summary['Registro valoraciones'])


def test_sec_identity_fallback_uses_exact_ticker_and_official_submission(monkeypatch):
    import sec_historical as sec
    links=[{'edgarUrl':'https://www.sec.gov/Archives/edgar/data/789019/000000/filing.htm'},
           {'edgarUrl':'https://example.invalid/Archives/edgar/data/999/evil.htm'}]
    calls=[]
    def fetch(url,ua):
        calls.append(url);return {'cik':789019,'tickers':['MSFT'],'name':'Microsoft Corporation'}
    monkeypatch.setattr(sec,'_get_json',fetch)
    assert sec.cik_from_filing_links('MSFT','StockValuationProject/1.0',links)==('0000789019','Microsoft Corporation')
    assert len(calls)==1 and calls[0].startswith('https://data.sec.gov/submissions/')
    assert sec.cik_from_filing_links('MSFT','StockValuationProject/1.0',[{'edgarUrl':'https://finance.yahoo.com/sec-filing/MSFT/0001193125-26-453698_789019'}])==('0000789019','Microsoft Corporation')
    assert sec.cik_from_filing_links('OTHER','StockValuationProject/1.0',links)==(None,None)


def test_sec_index_403_does_not_force_yahoo_financial_history(monkeypatch):
    import sec_historical as sec
    import requests
    monkeypatch.setattr(sec,'_get_json',lambda *a,**k:(_ for _ in ()).throw(requests.HTTPError('403 índice')))
    monkeypatch.setattr(sec,'cik_from_filing_links',lambda ticker,ua:('0000789019','Microsoft Corporation') if ticker=='MSFT' else (None,None))
    assert sec.resolve_cik('MSFT','StockValuationProject/1.0')==('0000789019','Microsoft Corporation')
    assert sec.resolve_cik('UNKNOWN','StockValuationProject/1.0')==(None,None)
