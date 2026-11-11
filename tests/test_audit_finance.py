import math
import numpy as np
import pandas as pd
import pytest
from modelo_fundamental import wacc_model, fx_rate


def test_common_terminal_independent_dcf(build):
    r=build()
    path=r.projected.query("Escenario == 'Base'").set_index('Año futuro')
    vals=r.valuation.query("Escenario == 'Base' and Método.str.contains('DCF')",engine='python').set_index('Horizonte (años)')
    a=r.assumptions.set_index('Supuesto')['Valor']
    w=a['WACC (%)']/100; g=a['Crecimiento terminal (%)']/100
    assert path.loc[8,'Crecimiento ingresos (%)']/100==pytest.approx(g)
    terminal=path.loc[8,'FCFF (miles MM)']*1e9*(1+g)/(w-g)
    for h in [0,1,3]:
        ev=sum(path.loc[y,'FCFF (miles MM)']*1e9/(1+w)**(y-h) for y in range(h+1,9))+terminal/(1+w)**(8-h)
        nd=a['Deuda neta reciente (miles MM)']*1e9 if h==0 else path.loc[h,'Deuda neta proyectada (miles MM)']*1e9
        shares=a['Acciones al cierre (miles MM)']*1e9 if h==0 else path.loc[h,'Acciones (miles MM)']*1e9
        assert vals.loc[h,'Precio objetivo (divisa cotización)']==pytest.approx((ev-nd)/shares)
        subset=r.dcf_detail.query("Escenario == 'Base' and `Horizonte base (años)` == @h")
        assert subset['Año flujo'].max()==8
    reinv=path.loc[8,'CAPEX (miles MM)']-path.loc[8,'D&A (miles MM)']+path.loc[8,'Variación capital trabajo (miles MM)']
    rr=reinv/path.loc[8,'NOPAT (miles MM)']
    assert vals.loc[1,'ROIC terminal implícito (%)']/100==pytest.approx(g/rr)


def test_fcff_identity_shares_cash_and_total_return(build):
    normal=build(); changed=build(share_schedule={1:{'cancelled_shares':1.,'issued_shares':.2,'buyback_price_fin':5.,'source':'fixture evidence'}})
    a=changed.projected.query("Escenario == 'Base'").iloc[0]
    b=normal.projected.query("Escenario == 'Base'").iloc[0]
    assert a['Acciones (miles MM)']*1e9==pytest.approx(9.2)
    assert a['Deuda neta proyectada (miles MM)']-b['Deuda neta proyectada (miles MM)']==pytest.approx(a['Recompras cash (miles MM)']-b['Recompras cash (miles MM)'])
    assert a['FCFF (miles MM)']==pytest.approx(a['NOPAT (miles MM)']+a['D&A (miles MM)']-a['CAPEX (miles MM)']-a['Variación capital trabajo (miles MM)'])
    v=changed.valuation.query("Escenario == 'Base' and `Horizonte (años)` == 1 and Método.str.contains('DCF')",engine='python').iloc[0]
    assert v['Retorno total (%)']==pytest.approx((v['Precio objetivo (divisa cotización)']+v['Dividendos acumulados (divisa cotización)'])/100*100-100)
    with pytest.raises(ValueError):build(share_schedule={1:{'cancelled_shares':1}})


def test_wacc_aligned_debt_currency_and_country(model_inputs,monkeypatch):
    annual=model_inputs['annual'].copy();annual.loc[2024,'Deuda total']=40.;annual.loc[2025,'Deuda total']=60.
    r=wacc_model('USD',1000,1,9999,annual,{'beta':1},.25)
    assert r[4]==pytest.approx(.05) # 2.5 / ((40+60)/2), no deuda posterior 9999
    monkeypatch.setenv('VALUACION_PARAMETROS_MONEDA','KRW')
    assert np.isnan(wacc_model('USD',1000,1,60,annual,{'beta':1},.25)[0])
    monkeypatch.setenv('VALUACION_PARAMETROS_MONEDA','USD')
    monkeypatch.setenv('VALUACION_ERP_INCLUYE_PAIS','true');monkeypatch.setenv('VALUACION_RIESGO_PAIS','0.01')
    assert np.isnan(wacc_model('USD',1000,1,60,annual,{'beta':1},.25)[0])


def test_roic_mean_and_missing_initial(build,model_inputs):
    annual=model_inputs['annual'].copy();annual.loc[2024,'Capital invertido aproximado']=80.;annual.loc[2025,'NOPAT aproximado']=20.
    r=build(annual=annual)
    assert r.roic.iloc[-1]['ROIC capital medio (%)']==20.
    assert np.isnan(r.roic.iloc[0]['ROIC capital medio (%)'])


def test_fx_direct_inverse_and_missing():
    assert fx_rate('KRW','KRW')[0]==1
    assert fx_rate('USD','KRW',lambda pair:1300 if pair=='USDKRW=X' else np.nan)[0]==1300
    assert fx_rate('USD','KRW',lambda pair:1/1300 if pair=='KRWUSD=X' else np.nan)[0]==1300
    assert np.isnan(fx_rate('USD','KRW')[0])


def test_expired_override_blocks_all_targets(build,monkeypatch):
    monkeypatch.setenv('VALUACION_TIPO_LIBRE_RIESGO_CADUCIDAD','2025-01-01')
    assert build().valuation['Precio objetivo (divisa cotización)'].isna().all()


def test_ttm_roic_requires_same_period_initial_balance(build,model_inputs):
    q=model_inputs['quarterly'].copy()
    prior=q.iloc[[0]].copy();prior.index=pd.to_datetime(['2024-12-31'])
    q=pd.concat([prior,q]);q['Capital invertido aproximado']=[80.,90.,100.,110.,120.]
    # EBIT TTM 120; normalised tax 25%; mean capital 100 -> 90%.
    r=build(quarterly=q)
    assert r.roic_ttm.iloc[0]['ROIC TTM capital medio (%)']==pytest.approx(90.)
    assert build().roic_ttm.iloc[0]['Estado']=='N/D'
