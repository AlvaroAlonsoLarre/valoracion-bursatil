"""Reglas generales: empresas sintéticas; ninguna cotización real fijada en tests."""
from copy import deepcopy
import json
import numpy as np
import pandas as pd
import pytest
from tests.test_stock_dashboard import stock_inputs
from analisis_acciones import build_stock_analysis
from sec_quarterly import reconcile_quarters,quarter_fact
from estados_datos import STATES
from sec_historical import _annual_periods,sec_fact
from flujo_acciones import analysis_from_snapshot


def fact(start,end,value,form='10-Q',filed='2026-01-20'):
    return dict(start=start,end=end,val=value,form=form,filed=filed,accn='0000000001-26-000001')


def official(concepts):
    return {'cik':1,'facts':{'us-gaap':{k:{'units':{unit:values}} for k,(unit,values) in concepts.items()}}}


def test_sec_completes_missing_flow_and_preserves_eps():
    facts=official({'Revenues':('USD',[fact('2025-10-01','2025-12-31',120.)])})
    q=pd.DataFrame({'Ingresos':[np.nan],'EPS diluido':[2.]},index=pd.to_datetime(['2025-12-31']))
    result,audit=reconcile_quarters(q,facts,'USD','2026-02-02')
    assert result.iloc[0]['Ingresos']==120 and result.iloc[0]['EPS diluido']==2
    assert audit.iloc[0]['Estado']=='DISPONIBLE' and audit.iloc[0]['SHA256']


def test_material_conflict_is_local_and_not_replaced_by_sec():
    facts=official({'Revenues':('USD',[fact('2025-10-01','2025-12-31',120.)])})
    q=pd.DataFrame({'Ingresos':[150.],'EPS diluido':[2.]},index=pd.to_datetime(['2025-12-31']))
    result,audit=reconcile_quarters(q,facts,'USD','2026-02-02')
    assert pd.isna(result.iloc[0]['Ingresos']) and result.iloc[0]['EPS diluido']==2
    assert audit.iloc[0]['Estado']=='BLOQUEADO'


def test_weekly_fiscal_date_needs_two_independent_matching_flows():
    facts=official({'Revenues':('USD',[fact('2025-10-04','2026-01-02',120.)]),
                    'NetIncomeLoss':('USD',[fact('2025-10-04','2026-01-02',20.)])})
    q=pd.DataFrame({'Ingresos':[120.],'Beneficio neto':[20.]},index=pd.to_datetime(['2025-12-31']))
    result,audit=reconcile_quarters(q,facts,'USD','2026-02-02')
    assert result.index[-1]==pd.Timestamp('2026-01-02')
    assert audit.iloc[0]['Campo']=='Fecha cierre'
    q['Beneficio neto']=np.nan
    result,_=reconcile_quarters(q,facts,'USD','2026-02-02')
    assert result.index[-1]==pd.Timestamp('2025-12-31')


def test_ytd_differences_require_same_start_and_do_not_subtract_eps():
    records=[fact('2025-01-01','2025-06-30',70.),fact('2025-01-01','2025-09-30',120.)]
    value,parts=quarter_fact(records,pd.Timestamp('2025-09-30'))
    assert value==50 and parts[1]['coefficient']==-1
    assert pd.isna(quarter_fact(records,pd.Timestamp('2025-09-30'),False)[0])
    records[0]['start']='2025-02-01'
    assert pd.isna(quarter_fact(records,pd.Timestamp('2025-09-30'))[0])


def test_registration_statements_supply_pre_ipo_financial_history():
    facts=official({'Revenues':('USD',[fact('2024-01-01','2024-12-31',100.,'S-1'),fact('2025-01-01','2025-12-31',120.,'S-1/A')])})
    assert _annual_periods(facts,{},10)==['2024-12-31','2025-12-31']
    row=sec_fact(facts,['Revenues'],'2024-12-31',currency='USD')
    assert row['value']==100 and row['form']=='S-1'


def test_no_pe_still_projects_financials_without_fabricating_targets(stock_inputs):
    result=build_stock_analysis(**{**stock_inputs,'history':pd.DataFrame()})
    assert len(result.projected)==12
    assert result.valuation['Precio objetivo'].isna().all()
    assert result.metrics.set_index('Indicador').loc['Ingresos','Estado']=='DISPONIBLE'
    assert set(result.methods['Estado'])<=STATES
    assert set(result.controls['Estado'])<=STATES


@pytest.mark.parametrize('field',['market_cap','shares_outstanding'])
def test_market_perimeter_inconsistency_does_not_invalidate_per_share_eps(stock_inputs,field):
    args={**stock_inputs,field:3000.}
    result=build_stock_analysis(**args)
    assert result.summary['primary_available'] and len(result.projected)==12
    bad=result.controls.query("Comprobación=='Precio × acciones = capitalización'").iloc[0]
    assert bad['Estado']=='BLOQUEADO' and bad['Método']=='Capitalización/EV'


def test_class_and_issuer_shares_are_kept_separate(stock_inputs):
    args={**stock_inputs,'shares_outstanding':4.,'info':{**stock_inputs['info'],'impliedSharesOutstanding':10.}}
    result=build_stock_analysis(**args)
    assert result.summary['diluted_base']==10 and result.summary['primary_available']
    assert result.controls.query("Comprobación=='Precio × acciones = capitalización'").iloc[0]['Estado']=='DISPONIBLE'


def test_split_adjustment_prevents_false_dilution(stock_inputs):
    args=deepcopy(stock_inputs);a=args['annual'];h=args['history']
    a.loc[a.index<2025,'Acciones diluidas medias']/=10
    a.loc[a.index<2025,'EPS diluido']*=10
    h.loc[h['Ejercicio']<2025,'Factor split acciones']=10.
    result=build_stock_analysis(**args)
    dilution=result.assumptions.query("Escenario=='Base' and Parámetro=='dilution'")['Valor'].iloc[0]
    assert dilution==pytest.approx(0.) and result.summary['primary_available']


def test_fade_compounds_each_year_and_normalizes_margin(stock_inputs):
    scenarios={s:{'growth':.30,'growth_terminal':.10,'margin':.30,'margin_terminal':.20} for s in ['Pesimista','Base','Optimista']}
    result=build_stock_analysis(**stock_inputs,settings={'scenarios':scenarios})
    p=result.projected.query("Escenario=='Base'").set_index('Año futuro')
    assert p.loc[1,'Ingresos']==pytest.approx(400*1.3)
    assert p.loc[3,'Ingresos']==pytest.approx(400*1.3*1.2*1.1)
    assert p.loc[2,'Margen aplicado']==pytest.approx(.25)
    assert p.loc[4,'Margen aplicado']==pytest.approx(.20)
    assert p.loc[3,'EPS financiero']==pytest.approx(p.loc[3,'Beneficio común normalizado']/p.loc[3,'Acciones diluidas'])


def test_cyclicality_changes_assumptions_without_using_market_price(stock_inputs):
    args=deepcopy(stock_inputs);args['info']['industryKey']='semiconductors'
    one=build_stock_analysis(**args)
    two=build_stock_analysis(**{**args,'price':150.,'market_cap':1500.})
    pd.testing.assert_frame_equal(one.assumptions,two.assumptions)
    pd.testing.assert_frame_equal(one.projected,two.projected)


def test_separation_keeps_raw_history_and_excludes_pre_listing_from_normalization(stock_inputs):
    args=deepcopy(stock_inputs);args['info'].update(firstTradeDateMilliseconds=int(pd.Timestamp('2024-01-01').timestamp()*1000),valuation_separation_registration=True)
    args['annual'].loc[args['annual'].index<2024,'Ingresos']*=100
    result=build_stock_analysis(**args)
    growth=result.assumptions.query("Escenario=='Base' and Parámetro=='growth'")['Valor'].iloc[0]
    assert growth==pytest.approx(.08)
    assert result.history_statistics['Ejercicios disponibles'].max()==10
    assert result.controls['Comprobación'].eq('Perímetro anterior a separación').any()


def test_metric_missing_capex_and_roic_is_local(stock_inputs):
    args=deepcopy(stock_inputs);args['quarterly']['CAPEX']=np.nan;args['quarterly']['Flujo de caja libre']=np.nan
    result=build_stock_analysis(**args);m=result.metrics.set_index('Indicador')
    assert m.loc['FCF','Estado']=='NO DISPONIBLE' and m.loc['Ingresos','Estado']=='DISPONIBLE'
    assert m.loc['ROIC','Estado']=='NO DISPONIBLE' and result.summary['primary_available']


def test_empty_new_issuer_is_diagnostic_and_exportable(tmp_path):
    from ejecutar_analisis import save_unavailable
    from datetime import datetime,timezone
    assert save_unavailable('NEW-ISSUER',tmp_path,datetime.now(timezone.utc))==2
    snapshot=json.loads((tmp_path/'NEW-ISSUER_inputs.json').read_text())
    result,tables=analysis_from_snapshot(snapshot)
    assert not result.summary['primary_available'] and list(tmp_path.glob('*.xlsx'))
    assert tables['Disponibilidad metricas']['Valor'].isna().all()


def test_peer_class_deduplication_uses_verified_issuer_or_same_legal_name(stock_inputs):
    from comparables_inteligentes import score_and_filter
    info={**stock_inputs['info'],'industryKey':'software','sectorKey':'technology','longBusinessSummary':'enterprise software cloud applications business services'}
    peers=pd.DataFrame([{'Ticker':t,'Empresa':'Same Consolidated Issuer','Emisor id':t,'Descripción actividad':info['longBusinessSummary'],'Industria clave':'software','Sector clave':'technology'} for t in ['CLASS-A','CLASS-C']])
    selected,_,_,_,universe=score_and_filter(peers,'NEW',target_info=info,return_universe=True)
    assert len(selected)==1 and universe['Observación'].str.contains('clase duplicada').any()


def test_registration_tables_require_consolidated_heading_scale_and_annual_header():
    from registration_history import parse_registration
    filing={'form':'S-1','filing_date':'2026-01-20','accession':'1-26-1','url':'https://www.sec.gov/Archives/edgar/data/1/document.htm'}
    document='''<div>CONSOLIDATED STATEMENTS OF OPERATIONS (in millions, except per share data) U.S. GAAP</div>
    <table><tr><td>Year Ended June 30,</td></tr><tr><td></td><td>2025</td><td>2024</td></tr>
    <tr><td>Revenue</td><td>120</td><td>100</td></tr><tr><td>Net income (loss)</td><td>10</td><td>(4)</td></tr>
    <tr><td>Net income (loss) per share of common stock attributable to common shareholders</td><td></td><td></td></tr>
    <tr><td>Diluted</td><td>1.00</td><td>(0.40)</td></tr></table>'''
    a,audit,gaap=parse_registration(document,filing)
    assert gaap and a.loc[2025,'Ingresos']==120e6 and a.loc[2024,'EPS diluido']==-.4
    assert a.loc[2025,'Fecha cierre fiscal']==pd.Timestamp('2025-06-30')
    assert audit['Concepto SEC'].str.startswith('Tabla:').all()
    assert parse_registration(document.replace('in millions','scale unavailable'),filing)[0].empty
    assert parse_registration(document.replace('Year Ended June 30,','Three Months Ended June 30,'),filing)[0].empty


def test_sec_reconciliation_does_not_accept_future_filing_or_wrong_unit():
    facts=official({'Revenues':('EUR',[fact('2025-10-01','2025-12-31',120.)])})
    q=pd.DataFrame({'Ingresos':[np.nan]},index=pd.to_datetime(['2025-12-31']))
    assert pd.isna(reconcile_quarters(q,facts,'USD','2026-02-02')[0].iloc[0]['Ingresos'])
    facts=official({'Revenues':('USD',[fact('2025-10-01','2025-12-31',120.,filed='2027-01-20')])})
    assert pd.isna(reconcile_quarters(q,facts,'USD','2026-02-02')[0].iloc[0]['Ingresos'])
