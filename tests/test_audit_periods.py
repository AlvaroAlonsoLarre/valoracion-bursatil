import numpy as np
import pandas as pd
import pytest
from modelo_fundamental import quarterly_snapshot, ttm_yoy
from actualidad_financiera import comprobar_actualidad


def quarters():
    dates=pd.date_range('2024-03-31',periods=8,freq='QE')
    return pd.DataFrame({c:[25.]*4+[30.]*4 for c in
        ['Ingresos','Beneficio operativo','Flujo de caja operativo','CAPEX','D&A']},index=dates)


def snap(q,annual=None):
    return quarterly_snapshot(q,pd.DataFrame() if annual is None else annual,pd.Timestamp('2026-01-01'),'2025-12-31')


def test_yoy_equal_periods():
    _,_,q,_=snap(quarters())
    assert ttm_yoy(q,'Ingresos')==pytest.approx(.2)
    assert np.isnan(ttm_yoy(q.tail(5),'Ingresos'))


def test_gap_identical_and_conflicting_duplicates():
    q=quarters()
    assert snap(q.drop(q.index[-2]))[0]['Ingresos'] is np.nan or np.isnan(snap(q.drop(q.index[-2]))[0]['Ingresos'])
    duplicate=pd.concat([q,q.tail(1)])
    assert snap(duplicate)[0]['Ingresos']==120
    duplicate.iloc[-1,duplicate.columns.get_loc('CAPEX')]=60
    result,_,_,notes=snap(duplicate)
    assert np.isnan(result['CAPEX']) and result['Ingresos']==120
    assert any('conflictivo' in n for n in notes)


def test_ocf_ytd_detected_even_when_revenue_matches():
    q=quarters().tail(4)
    q['Flujo de caja operativo']=[30,60,90,120]
    annual=pd.DataFrame({c:[120.] for c in q},index=[2025])
    result,_,_,notes=snap(q,annual)
    assert result['Ingresos']==120
    assert np.isnan(result['Flujo de caja operativo'])
    assert any('Flujo de caja operativo' in n for n in notes)


def test_ytd_conversion_and_missing_start():
    q=quarters().tail(4)
    q.loc[:,:]=np.array([30,60,90,120])[:,None]
    q['Tipo periodo']='YTD'
    assert np.isnan(snap(q)[0]['Ingresos'])
    q['Inicio periodo']='2025-01-01'
    assert snap(q)[0]['Ingresos']==120


def test_freshness_unknown_contact_and_failed_request():
    a=comprobar_actualidad(sec_cik='789019',quarterly_dates=['2026-09-30'],as_of='2026-11-11')
    assert a['status']=='NO_VERIFICADO' and 'CIK conocido' in a['detail']
    def fail(*a,**kw):raise ConnectionError('offline')
    b=comprobar_actualidad(sec_cik='789019',sec_user_agent='Project contact@example.com',
        quarterly_dates=['2026-09-30'],as_of='2026-11-11',requests_get=fail)
    assert b['status']=='NO_VERIFICADO'
