import pandas as pd
import numpy as np
from comparables_inteligentes import score_and_filter, economic_seeds


def peers():
    return pd.DataFrame([{'Ticker':t,'Emisor id':t,'PER forward':10,'EV/EBITDA':8,
       'PER periodo':'NTM','PER base':'GAAP','EV/EBITDA periodo':'NTM','Perímetro deuda':'Financiera sin leases',
       'Descripción actividad':'enterprise software cloud applications business services',
       'Industria clave':'software','Sector clave':'technology','Margen operativo (%)':20} for t in ['A','B','C']])


def score(p):
    from tests.multiple_fixtures import with_evidence
    p=with_evidence(p,'2026-01-15')
    return score_and_filter(p,'TARGET',as_of='2026-01-15',target_info={'valuation_accounting_basis':'GAAP','industryKey':'software','sectorKey':'technology',
      'longBusinessSummary':'enterprise software cloud applications business services'})


def test_three_independent_issuers_and_unknown_definitions():
    p=peers();assert score(p)[1:3]==(10,8)
    assert np.isnan(score(p.head(2))[1])
    p.loc[2,'Emisor id']='B';assert np.isnan(score(p)[1])
    p=peers();p['EV/EBITDA periodo']='LTM';assert np.isnan(score(p)[2]) and score(p)[1]==10
    p['PER periodo']='No verificado';assert np.isnan(score(p)[1])


def test_economic_route_does_not_grant_eligibility():
    assert {'ORCL','SAP','CRM','AMZN'}<=set(economic_seeds('MSFT'))
    assert economic_seeds('OTHER')==[]


def test_da_aggregate_and_lease_perimeter_block_only_affected_methods(build,model_inputs):
    annual=model_inputs['annual'].copy();annual['Definición D&A']='Agregado D&A y otros; no D&A pura'
    r=build(annual=annual)
    assert r.valuation.loc[r.valuation['Método'].str.contains('DCF'),'Precio objetivo (divisa cotización)'].isna().all()
    q=model_inputs['quarterly'].copy();q['Deuda incluye arrendamientos']=True
    r=build(quarterly=q)
    assert r.valuation.loc[r.valuation['Método'].str.contains('DCF'),'Precio objetivo (divisa cotización)'].isna().all()
