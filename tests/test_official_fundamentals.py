from copy import deepcopy
from pathlib import Path
import json
import numpy as np
import pandas as pd
import pytest
from fuentes_fundamentales import pure_da_facts,quarter_da,earnings_pdf,enrich_financials
from comparables_definiciones import definition_coverage
from modelo_fundamental import quarterly_snapshot


def inline(currency='USD',entity='0000789019',include_amort=True,dimensions=False):
    extra='<xbrldi:explicitMember>Segment</xbrldi:explicitMember>' if dimensions else ''
    facts='<ix:nonFraction name="us-gaap:Depreciation" contextRef="c" unitRef="u" scale="9">34.3</ix:nonFraction>'
    if include_amort:facts+='<ix:nonFraction name="us-gaap:AmortizationOfIntangibleAssets" contextRef="c" unitRef="u" scale="9">4.7</ix:nonFraction>'
    # This finance-lease component is included in PP&E depreciation and must not be added again.
    facts+='<ix:nonFraction name="us-gaap:FinanceLeaseRightOfUseAssetAmortization" contextRef="c" unitRef="u" scale="9">5.403</ix:nonFraction>'
    return f'<xbrli:unit id="u"><xbrli:measure>iso4217:{currency}</xbrli:measure></xbrli:unit><xbrli:context id="c"><xbrli:entity><xbrli:identifier>{entity}</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2025-07-01</xbrli:startDate><xbrli:endDate>2026-06-30</xbrli:endDate></xbrli:period>{extra}</xbrli:context>'+facts


def parse(html):return pure_da_facts(html,currency='USD',entity_id='0000789019',source='fixture',published='2026-07-29')


def test_da_requires_both_consolidated_components_no_lease_double_count():
    data=parse(inline());assert data[('2025-07-01','2026-06-30')]['value']==pytest.approx(39e9)
    assert not parse(inline(include_amort=False))
    assert not parse(inline(currency='KRW'))
    assert not parse(inline(dimensions=True))
    with pytest.raises(ValueError,match='Emisor'):parse(inline(entity='OTHER'))


def test_nested_durations_reconstruct_quarters_not_pro_rata():
    def rec(value):return {'value':value,'source':'fixture','published':'2026-10-28'}
    source={('2025-07-01','2026-06-30'):rec(39e9),('2025-07-01','2026-03-31'):rec(27.7e9),
       ('2025-07-01','2025-09-30'):rec(8.6e9),('2026-01-01','2026-03-31'):rec(10.1e9)}
    q=quarter_da(source)
    assert q[('2025-10-01','2025-12-31')]['value']==pytest.approx(9e9)
    assert q[('2026-04-01','2026-06-30')]['value']==pytest.approx(11.3e9)
    assert sum(v['value'] for v in q.values())==pytest.approx(39e9)


class Page:
    def __init__(self,text):self.text=text
    def extract_text(self,**kw):return self.text


def pdf_reader(monkeypatch):
    income="""K-IFRS (KRW Billion) Q3'26 Q2'26 Q3'25
Revenue 104,615 79,319 24,449
Operating Profit 83,334 60,543 11,383
EBITDA 87,675 64,563 14,949
Net Profit 39,776 93,923 12,598
Income Before Tax 50,708 122,708 14,790
Tax Expense/Benefit 10,933 28,786 2,193
EPS(KRW)
Diluted 54,454 131,478 17,850
Shares
"""
    cf="""(Unit : KRW Billion) ’26 Q3 ’26 Q2 ’25 Q3
Beginning Cash Balance** 87,958 54,330 16,962
CF from Operating Activities 54,781 65,710 14,368
D&A* 4,335 4,030 3,560
Acquisition of PP&E (12,670) (10,671) (5,033)
Dividend Payout (272) (1,594) (259)
Ending Cash Balance** 114,460 87,958 27,854
"""
    balance="""K-IFRS (KRW Billion) Q3'26 Q2'26 Q4'25
Interest-bearing Debts 15,800 18,587 22,248
Total Shareholders' Equity 309,088 262,693 120,667
"""
    pages=[Page('') for _ in range(20)]
    pages[0]=Page('SK hynix FY2026 2026.10.28 consolidated K-IFRS FY2026 Q3')
    pages[19]=Page(income);pages[15]=Page(cf);pages[18]=Page(balance)
    class Reader:
        def __init__(self,*a):self.pages=pages
    monkeypatch.setattr('pypdf.PdfReader',Reader)
    return pages


def doc():return json.loads(Path('fuentes_fundamentales.json').read_text())['000660.KS']['documents'][0]


def test_official_pdf_units_periods_and_two_da_definitions(monkeypatch):
    pages=pdf_reader(monkeypatch)
    row,comparatives=earnings_pdf(b'fixture',doc(),'SK hynix')
    assert row['Ingresos']==104615e9
    assert row['CAPEX PP&E']==12670e9
    assert 'CAPEX' not in row
    assert row['D&A operativa']==4341e9 and row['D&A cash flow']==4335e9
    assert row['EPS diluido']==54454
    assert row['Deuda neta']==-98660e9
    pages[19].text=pages[19].text.replace("Q3'26","Q2'26")
    with pytest.raises(ValueError,match='periodo'):earnings_pdf(b'fixture',doc(),'SK hynix')


def test_sk_partial_capex_never_uses_historical_fallback(monkeypatch,model_inputs):
    pdf_reader(monkeypatch)
    class Response:
        content=b'fixture'
        def raise_for_status(self):pass
    config={'GENERIC.KS':deepcopy(json.loads(Path('fuentes_fundamentales.json').read_text())['000660.KS'])}
    a=model_inputs['annual'];q=model_inputs['quarterly']
    result=enrich_financials('GENERIC.KS',a,q,'KRW','2026-11-12',config=config,requests_get=lambda *a,**kw:Response())
    assert result.quarterly.index.max()==pd.Timestamp('2026-09-30')
    assert np.isnan(result.quarterly.loc['2026-09-30','CAPEX'])
    assert set(result.quarterly.attrs['invalid_flows'])=={'CAPEX','D&A'}
    # An absent full CAPEX must remain invalid even when annual CAPEX exists.
    snapshot=quarterly_snapshot(result.quarterly,a,pd.Timestamp('2026-11-12'),'2025-12-31')[0]
    assert np.isnan(snapshot['CAPEX'])


def test_uncovered_ticker_is_unchanged_and_failed_source_not_verified(model_inputs):
    a=model_inputs['annual'];q=model_inputs['quarterly']
    result=enrich_financials('OTHER',a,q,'USD','2026-11-12')
    pd.testing.assert_frame_equal(result.annual,a);pd.testing.assert_frame_equal(result.quarterly,q)
    def fail(*a,**kw):raise ConnectionError('offline')
    config={'OTHER':{'currency':'USD','entity_id':'789019','documents':[{'kind':'inline_xbrl','published':'2026-01-01','url':'https://example.invalid/source'}]}}
    result=enrich_financials('OTHER',a,q,'USD','2026-11-12',requests_get=fail,config=config)
    assert result.evidence['status']=='PARCIAL' and result.evidence['issues']
    pd.testing.assert_frame_equal(result.annual,a)


def test_peer_labels_without_documentation_do_not_claim_complete_definitions():
    p=pd.DataFrame([{'Ticker':'TEST','PER periodo':'NTM','PER base':'GAAP','EV/EBITDA periodo':'LTM','Perímetro deuda':'Financiera sin leases'}])
    result=definition_coverage(p)
    assert not result['Definición completa'].any()
    assert result['Requisitos pendientes'].str.contains('fuente').all()


def test_ttm_reconciliation_distinguishes_missing_and_conflicted_flows(model_inputs):
    from fuentes_fundamentales import ttm_reconciliation
    q=model_inputs['quarterly'].copy();q.attrs['invalid_flows']=['CAPEX']
    data=ttm_reconciliation(q,model_inputs['annual'],'2026-01-15','2025-12-31').set_index('Campo')
    assert data.loc['Ingresos','TTM (unidades)']==400.
    assert data.loc['Ingresos','Conciliación FY']=='CONCILIA'
    assert data.loc['CAPEX','Observaciones fuente']==4
    assert data.loc['CAPEX','Periodos utilizables']==0
    assert data.loc['CAPEX','Estado']=='N/D'


def test_companyfacts_is_an_official_fallback_with_same_filing_components():
    from fuentes_fundamentales import pure_da_companyfacts
    def row(value,accn='same',filed='2026-07-29'):
        return {'start':'2025-07-01','end':'2026-06-30','filed':filed,'accn':accn,'form':'10-K','val':value}
    data={'cik':789019,'facts':{'us-gaap':{
        'Depreciation':{'units':{'USD':[row(34.3e9)]}},
        'AmortizationOfIntangibleAssets':{'units':{'USD':[row(4.7e9)]}}}}}
    def extract(value):return pure_da_companyfacts(value,currency='USD',entity_id='789019',source='fixture',as_of='2026-11-12')
    assert extract(data)[('2025-07-01','2026-06-30')]['value']==39e9
    bad=deepcopy(data);bad['facts']['us-gaap']['AmortizationOfIntangibleAssets']['units']['USD'][0]['accn']='other'
    assert not extract(bad)
    bad=deepcopy(data);bad['facts']['us-gaap']['AmortizationOfIntangibleAssets']['units']['USD'][0]['filed']='2027-01-01'
    assert not extract(bad)
    with pytest.raises(ValueError):extract({**data,'cik':1})


@pytest.mark.parametrize('ticker',['MSFT','000660.KS'])
def test_real_enriched_snapshots_preserve_method_controls_and_ttm(ticker):
    from auditoria_io import read_snapshot
    from modelo_fundamental import build_fundamental_model
    annual,peers,kwargs,_=read_snapshot(Path('docs/auditoria_2026-11-12/inputs')/(ticker+'_after.json'))
    result=build_fundamental_model(annual,peers,**kwargs)
    if ticker=='MSFT':
        assert annual.loc[2026,'D&A']==pytest.approx(39e9)
        # Prefer the directly reported 9.1bn Q2 to a 9.0bn residual of rounded notes.
        assert kwargs['quarterly'].tail(4)['D&A'].sum()==pytest.approx(42.6e9)
        assert kwargs['quarterly'].loc['2025-07-01':'2026-06-30','D&A'].sum()-annual.loc[2026,'D&A']==pytest.approx(.1e9)
        targets=result.valuation['Precio objetivo (divisa cotización)']
        assert targets.notna().sum()==9
        assert result.valuation.loc[result.valuation['Método'].str.contains('forward'),'Precio objetivo (divisa cotización)'].isna().all()
        # Independent Gordon calculation from the real explicit path for each scenario.
        for scenario in ['Pesimista','Base','Optimista']:
            path=result.projected.query('Escenario == @scenario').set_index('Año futuro')
            for h in [0,1,3]:
                row=result.valuation[(result.valuation['Escenario']==scenario)&(result.valuation['Horizonte (años)']==h)&result.valuation['Método'].str.contains('DCF')].iloc[0]
                w=row['WACC (%)']/100;g=row['G terminal (%)']/100
                terminal=path.loc[8,'FCFF (miles MM)']*1e9*(1+g)/(w-g)
                ev=sum(path.loc[y,'FCFF (miles MM)']*1e9/(1+w)**(y-h) for y in range(h+1,9))+terminal/(1+w)**(8-h)
                nd=kwargs['quarterly'].iloc[-1]['Deuda neta'] if h==0 else path.loc[h,'Deuda neta proyectada (miles MM)']*1e9
                shares=kwargs['shares_outstanding'] if h==0 else path.loc[h,'Acciones (miles MM)']*1e9
                assert row['Precio objetivo (divisa cotización)']==pytest.approx((ev-nd)/shares)
    else:
        assert kwargs['quarterly'].index.max()==pd.Timestamp('2026-09-30')
        assert result.valuation.empty
        ttm=result.base_ttm.set_index('Campo')['Base TTM (unidades)']
        assert ttm['Ingresos']==pytest.approx(269336686e6)
        assert np.isnan(ttm['CAPEX']) and np.isnan(ttm['D&A'])


def test_source_identifies_software_without_inventing_a_contact(monkeypatch,model_inputs):
    monkeypatch.delenv('VALUACION_SEC_USER_AGENT',raising=False)
    seen=[]
    def request(url,**kwargs):
        seen.append(kwargs['headers']['User-Agent'])
        raise ConnectionError('fixture')
    config={'OTHER':{'currency':'USD','entity_id':'789019','documents':[{'kind':'companyfacts','url':'https://example.invalid/source'}]}}
    enrich_financials('OTHER',model_inputs['annual'],model_inputs['quarterly'],'USD','2026-11-12',requests_get=request,config=config)
    assert seen==['StockValuationProject/1.0']
