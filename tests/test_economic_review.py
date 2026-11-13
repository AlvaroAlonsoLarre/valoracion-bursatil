"""Calidad económica y fórmulas inversas, sin cotizaciones actuales esperadas."""
from copy import deepcopy
import numpy as np
import pandas as pd
import pytest
from tests.test_stock_dashboard import stock_inputs
from analisis_acciones import build_stock_analysis
from flujo_acciones import stock_tables
from revision_economica import qualified_history,recurrent_financial,investment_amounts,cagr,bridge,official_investment_notes,sensitivity,implied_requirements


def test_compound_growth_is_not_median_of_rates_and_respects_gaps():
    a=pd.DataFrame({'Ingresos':[100.,200.,100.]},index=[2023,2024,2025])
    assert cagr(a,10)==pytest.approx(0.)
    assert pd.isna(cagr(a.iloc[[0,2]],10))


def test_cyclical_initial_margin_does_not_reuse_peak_ttm(stock_inputs):
    args=deepcopy(stock_inputs);args['info']['industryKey']='semiconductors';args['quarterly']['Beneficio operativo']*=3
    result=build_stock_analysis(**args);a=result.assumptions.query("Escenario=='Base'").set_index('Parámetro')['Valor']
    assert a['margin']==pytest.approx(.2) and a['margin_terminal']==pytest.approx(.2)
    assert result.projected.query("Escenario=='Base' and `Año futuro`==1")['EBIT o PBT directo'].iloc[0]==pytest.approx(432*.2)


def test_geometric_fade_uses_observed_long_term_cagr(stock_inputs):
    args=deepcopy(stock_inputs);a=args['annual'];a['Ingresos']=100*np.cumprod([1.05]*5+[1.5]*5)
    args['info']['industryKey']='semiconductors'
    result=build_stock_analysis(**args);p=result.assumptions.query("Escenario=='Base'").set_index('Parámetro')['Valor']
    assert p['growth']==pytest.approx(.5)
    assert p['growth_terminal']==pytest.approx(cagr(a,10))
    assert p['growth_terminal']<.5


def test_material_financial_marks_are_not_projected_as_recurring(stock_inputs):
    a=stock_inputs['annual'].copy();a['Ganancia FV inversiones']=a['Ingresos']*.10
    a['Beneficio antes de impuestos']+=a['Ganancia FV inversiones'];a['Intereses inversiones']=a['Ingresos']*.015
    a['Gastos por intereses']=a['Ingresos']*.005
    result,note=recurrent_financial(a)
    assert result==pytest.approx(.01) and 'otros no operativos no extrapolados' in note
    pd.testing.assert_series_equal(bridge(a)['Ganancias inversiones identificadas'],pd.Series(a['Ingresos'].values*.10,name='Ganancias inversiones identificadas'))


def test_missing_interest_is_not_assumed_zero(stock_inputs):
    a=stock_inputs['annual'].copy();a['Ganancia FV inversiones']=a['Ingresos']*.10
    assert pd.isna(recurrent_financial(a)[0])
    assert pd.isna(investment_amounts(stock_inputs['annual'])).all()


def test_net_expense_cannot_be_subtracted_from_separate_interest_income(stock_inputs):
    a=stock_inputs['annual'].copy();a['Ganancia FV inversiones']=a['Ingresos']*.10
    a['Intereses inversiones']=3.;a['Concepto gasto intereses']='us-gaap:InterestExpenseNonOperatingNetOfInterestIncomeExpense'
    assert pd.isna(recurrent_financial(a)[0])


def test_financial_investment_income_is_not_removed_from_financial_business(stock_inputs):
    a=stock_inputs['annual'].copy();a['Ganancia FV inversiones']=a['Ingresos']*.10
    actual,note=recurrent_financial(a,financial=True)
    assert actual==pytest.approx(-.02)


def test_historical_pe_excludes_financial_marks_without_rewriting_reported_pe(stock_inputs):
    a=stock_inputs['annual'].copy();a.loc[2025,'Revalorizacion inversiones privadas']=100.
    result=qualified_history(a,stock_inputs['history'],stock_inputs['info']).set_index('Ejercicio')
    assert not result.loc[2025,'PER admisible económicamente']
    assert result.loc[2025,'PER histórico']==pytest.approx(15.)
    assert 'financieras identificadas' in result.loc[2025,'Motivo PER económico']


def test_historical_pe_excludes_atypical_tax(stock_inputs):
    a=stock_inputs['annual'].copy();a.loc[2025,'Impuestos']=a.loc[2025,'Beneficio antes de impuestos']*.5
    result=qualified_history(a,stock_inputs['history'],stock_inputs['info']).set_index('Ejercicio')
    assert not result.loc[2025,'PER admisible económicamente'] and 'Fiscalidad' in result.loc[2025,'Motivo PER económico']


def test_cyclical_peak_and_trough_are_excluded_from_pe_reference(stock_inputs):
    a=stock_inputs['annual'].copy();a.loc[2024,'Beneficio neto']*=.1;a.loc[2025,'Beneficio neto']*=3
    info={**stock_inputs['info'],'industryKey':'semiconductors'}
    result=qualified_history(a,stock_inputs['history'],info).set_index('Ejercicio')
    assert not result.loc[2024,'PER admisible económicamente'] and not result.loc[2025,'PER admisible económicamente']


def test_business_regime_does_not_fill_pe_reference_with_old_regime(stock_inputs):
    a=stock_inputs['annual'].copy();a.loc[a.index>=2023,'Beneficio operativo']*=3
    result=qualified_history(a,stock_inputs['history'],stock_inputs['info']).set_index('Ejercicio')
    assert not result.loc[2022,'PER admisible económicamente'] and result.loc[2023,'PER admisible económicamente']


def test_too_few_clean_per_references_do_not_block_business_projection(stock_inputs):
    args=deepcopy(stock_inputs);a=args['annual'];a.loc[a.index<2024,'Ganancia FV inversiones']=1000.
    a['Intereses inversiones']=a['Ingresos']*.01
    result=build_stock_analysis(**args)
    assert len(result.projected)==12 and not result.summary['primary_available']
    assert result.valuation.query("Método=='EPS × PER'")['Precio objetivo'].isna().all()
    assert result.methods.set_index('Método').loc['Precio/FCF','Estado']=='ESTIMADO'


def test_sensitivity_recalculates_business_path_and_keeps_market_fixed(stock_inputs):
    result=build_stock_analysis(**stock_inputs);s=sensitivity(result,'USD','USD')
    base=s[(s['Parámetro']=='growth')&(s['Cambio']==0)&s['Horizonte (años)'].eq(3)].iloc[0]
    assert base['Precio sensibilidad']==pytest.approx(result.summary['target_3y'])
    high=s[(s['Parámetro']=='growth')&(s['Cambio']==.05)&s['Horizonte (años)'].eq(3)].iloc[0]
    assert high['Precio sensibilidad']/base['Precio sensibilidad']==pytest.approx((1.13/1.08)**3)
    pe=s[(s['Parámetro']=='pe')&(s['Cambio']==.2)&s['Horizonte (años)'].eq(3)].iloc[0]
    assert pe['Precio sensibilidad']==pytest.approx(1.2*base['Precio sensibilidad'])
    assert result.summary['price']==stock_inputs['price']


def test_implied_one_variable_equations_reproduce_quote(stock_inputs):
    result=build_stock_analysis(**stock_inputs);table=implied_requirements(result)
    for _,row in table.iterrows():
        r=result.projected.query("Escenario=='Base'").set_index('Año futuro').loc[row['Año EPS']]
        assert row['PER implícito']*r['EPS financiero']==pytest.approx(stock_inputs['price'])
        sales=400*(1+row['Crecimiento uniforme implícito'])**row['Año EPS']
        assert sales*.18*.75/r['Acciones diluidas']*row['PER supuesto']==pytest.approx(stock_inputs['price'])
        assert (r['Ingresos']*(row['Margen implícito']-.02)*.75/r['Acciones diluidas']*row['PER supuesto'])==pytest.approx(stock_inputs['price'])


def test_sensitivity_cannot_bypass_main_controls(stock_inputs):
    args=deepcopy(stock_inputs);args['quarterly']['EPS diluido']=-1.
    result=build_stock_analysis(**args)
    assert not result.summary['primary_available'] and sensitivity(result,'USD','USD').empty


def test_economic_assumptions_do_not_depend_on_quote(stock_inputs):
    a=build_stock_analysis(**stock_inputs);b=build_stock_analysis(**{**stock_inputs,'price':300.,'market_cap':3000.})
    pd.testing.assert_frame_equal(a.assumptions,b.assumptions);pd.testing.assert_frame_equal(a.projected,b.projected)


def test_official_investment_notes_keep_periods_separate_and_auditable():
    filing={'url':'https://www.sec.gov/Archives/edgar/data/1/0001/report.htm','filing_date':'2026-10-30','report_date':'2026-09-30','form':'10-Q','accession':'1-26-1'}
    text='''<html><xbrli:context id="ytd"><xbrli:period><xbrli:startDate>2026-01-01</xbrli:startDate><xbrli:endDate>2026-09-30</xbrli:endDate></xbrli:period></xbrli:context><ix:nonFraction name="other:DebtSecuritiesAvailableForSaleReclassificationAdjustmentFromAOCI" contextRef="ytd" unitRef="USD" scale="6">40</ix:nonFraction></html>'''
    class Response:
        content=text.encode()
        def __init__(self):self.text=text
        def raise_for_status(self):pass
    result=official_investment_notes(filing,'USD','software',requests_get=lambda *a,**k:Response())
    assert result.iloc[0]['Importe pretax']==40e6
    assert result.iloc[0]['Inicio']=='2026-01-01' and result.iloc[0]['SHA256 documento']


def test_investment_total_is_not_added_to_its_unrealized_component():
    from revision_economica import INVESTMENT_TAGS
    from sec_historical import sec_fact
    def concept(value):return {'units':{'USD':[{'start':'2025-01-01','end':'2025-12-31','val':value,'form':'10-K','filed':'2026-02-01'}]}}
    facts={'facts':{'us-gaap':{'EquitySecuritiesFvNiGainLoss':concept(10.),'EquitySecuritiesFvNiUnrealizedGainLoss':concept(7.)}}}
    assert sec_fact(facts,INVESTMENT_TAGS['Ganancia FV inversiones'],'2025-12-31',currency='USD')['value']==10.


def test_positive_earnings_from_tax_benefit_are_not_clean_pe(stock_inputs):
    a=stock_inputs['annual'].copy();a.loc[2025,'Beneficio antes de impuestos']=-1.
    r=qualified_history(a,stock_inputs['history'],stock_inputs['info']).set_index('Ejercicio')
    assert not r.loc[2025,'PER admisible económicamente']
