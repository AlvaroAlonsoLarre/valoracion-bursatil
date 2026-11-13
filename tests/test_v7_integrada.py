"""Integración V7 sobre el único motor, con capturas reales ya archivadas."""
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
import json,zipfile,io
import numpy as np
import pandas as pd
import pytest
from analisis_acciones import build_stock_analysis
from auditoria_io import frame_payload,clean
from flujo_acciones import analysis_from_snapshot,excel_bytes,tables_summary
from estado_dashboard import prepare_capture,per_settings,edited_settings
from grafico_cotizacion import chart_data,HISTORY,FORECAST
from tests.test_stock_dashboard import stock_inputs
ROOT=Path(__file__).resolve().parents[1]


@lru_cache
def archived(ticker):
    member=f'final/{ticker}/{ticker}_inputs.json'
    for archive in (ROOT/'docs/economia_final_2026-11-12').glob('ejecuciones_*.zip'):
        with zipfile.ZipFile(archive) as z:
            if member in z.namelist():return json.loads(z.read(member))
    raise ValueError(ticker)


def test_msft_exact_verified_capture_six_scenarios():
    r,_=analysis_from_snapshot(archived('MSFT'))
    assert r.summary['target_1y']==pytest.approx(696.8406273758014)
    assert r.summary['target_3y']==pytest.approx(940.6814417866705)
    v=r.valuation.query("Método=='EPS × PER'")
    assert len(v)==6 and v['Precio objetivo'].notna().all()
    assert set(v['Escenario'])=={'Pesimista','Base','Optimista'}


@pytest.mark.parametrize('history',HISTORY)
@pytest.mark.parametrize('forecast',FORECAST)
def test_all_chart_period_combinations(history,forecast):
    p=archived('MSFT');r,_=analysis_from_snapshot(p);d=chart_data(p,r.summary,r.valuation,history,forecast)
    observed=d[d['Tipo'].eq('Observado')];future=d[d['Tipo'].eq('Proyección')]
    assert len(observed)>0 and observed['Fecha'].max()<=pd.Timestamp(r.summary['as_of'])
    if forecast=='Ninguna':assert future.empty;return
    assert set(future['Serie'])=={'Pesimista','Base','Optimista'}
    end=pd.Timestamp(r.summary['as_of'])+pd.DateOffset(months=FORECAST[forecast])
    assert future['Fecha'].max()==end
    if FORECAST[forecast]>=12:
        for _,row in r.valuation.query("Método=='EPS × PER'").iterrows():
            date=pd.Timestamp(r.summary['as_of'])+pd.DateOffset(years=int(row['Horizonte (años)']))
            if date>end:continue
            actual=future[future['Serie'].eq(row['Escenario'])&future['Fecha'].eq(date)]
            assert actual.iloc[0]['Precio']==pytest.approx(row['Precio objetivo'])
            assert actual.iloc[0]['Origen']=='Objetivo EPS × PER del motor'


def test_missing_horizon_does_not_erase_valid_one_or_extrapolate():
    p=archived('MSFT');r,_=analysis_from_snapshot(p);v=r.valuation.copy()
    v.loc[v['Horizonte (años)'].eq(3),'Precio objetivo']=np.nan
    d=chart_data(p,r.summary,v,'1 semana','3 años');future=d[d['Tipo'].eq('Proyección')]
    assert future['Fecha'].max()==pd.Timestamp(r.summary['as_of'])+pd.DateOffset(years=1)
    v.loc[v['Método'].eq('EPS × PER'),'Precio objetivo']=np.nan
    d=chart_data(p,r.summary,v,'1 semana','3 años')
    assert d['Tipo'].eq('Observado').all()


@pytest.mark.parametrize('ticker',['AMZN','000660.KS'])
def test_manual_pe_enables_six_targets_without_changing_other_assumptions(ticker):
    p=archived(ticker);a,_=analysis_from_snapshot(p)
    settings=per_settings({'scenarios':{'Base':{'growth':.10}},'policy':{'required_return':.12}},'Manual',20.,.2,.25,'Sensibilidad sintética para verificar integración')
    b,t=analysis_from_snapshot(p,settings)
    assert b.summary['primary_available'] and b.summary['per_mode']=='Manual'
    assert b.settings['scenarios']['Base']['growth']==.10 and b.settings['policy']['required_return']==.12
    per=b.assumptions.query("Parámetro=='pe'").set_index('Escenario')['Valor']
    assert per.to_dict()=={'Pesimista':16.,'Base':20.,'Optimista':25.}
    for _,row in b.valuation.query("Método=='EPS × PER'").iterrows():
        assert row['Precio objetivo']==pytest.approx(row['EPS aplicado']*row['PER aplicado']*b.summary['per_share_fx'])
    history=chart_data(p,b.summary,b.valuation,'4 meses','3 años')
    assert history['Tipo'].eq('Proyección').any()
    xls=pd.read_excel(io.BytesIO(excel_bytes(t)),sheet_name='Valoracion EPS PER')
    result=tables_summary(ticker,t)
    assert np.allclose(xls['Precio objetivo'],pd.DataFrame(result['Valoracion EPS PER'])['Precio objetivo'],equal_nan=True)
    automatic=per_settings(settings,'Automático')
    assert automatic['scenarios']['Base']['growth']==.10 and 'pe' not in automatic['scenarios']['Base']


def test_exploratory_two_is_explicit_and_never_uses_one():
    p=deepcopy(archived('000660.KS'));r,_=analysis_from_snapshot(p,{'exploratory_pe':True})
    assert r.summary['primary_available'] and r.summary['exploratory_pe'] and r.summary['confidence']=='Baja'
    from auditoria_io import restore_frame
    h=restore_frame(p['historical']['Referencia histórica auditada']);h['PER histórico']=np.nan
    h.loc[h.index[-1],'PER histórico']=10.
    p['historical']['Referencia histórica auditada']=frame_payload(h)
    r,_=analysis_from_snapshot(p,{'exploratory_pe':True})
    assert not r.summary['primary_available']
    r,_=analysis_from_snapshot(p,per_settings({},'Manual',15.,.2,.2,'Un único PER no determina un automático'))
    assert r.summary['primary_available']


@pytest.mark.parametrize('ticker',['NVDA','MU'])
def test_normalized_economics_preserved(ticker):
    r,_=analysis_from_snapshot(archived(ticker));v=r.assumptions.query("Escenario=='Base'").set_index('Parámetro')['Valor']
    assert v['growth_terminal']<=v['growth'] and v['margin']==pytest.approx(v['margin_terminal'])
    assert v['margin']<.6


def test_manual_pe_does_not_bypass_negative_eps_or_missing_revenue(stock_inputs):
    args=deepcopy(stock_inputs);args['quarterly']['EPS diluido']=-1.
    r=build_stock_analysis(**args,settings=per_settings({},'Manual',20.,.2,.2,'No puede ocultar pérdidas'))
    assert not r.summary['primary_available']
    args['quarterly']['Ingresos']=np.nan
    assert not build_stock_analysis(**args,settings=per_settings({},'Manual',20.,.2,.2,'No puede inventar ingresos')).summary['primary_available']


def test_capture_legacy_missing_reference_is_explained_not_invented():
    p=deepcopy(archived('MSFT'));p['historical'].pop('Referencia histórica auditada');p['historical'].pop('Precios y splits');p['evidence'].pop('stock_model')
    raw,notes=prepare_capture(json.dumps(p));assert notes
    r,_=analysis_from_snapshot(json.loads(raw));assert not r.summary['primary_available'] and not r.projected.empty
    raw,_=prepare_capture(json.dumps(archived('MSFT')));r,_=analysis_from_snapshot(json.loads(raw));assert r.summary['primary_available']
    with pytest.raises(ValueError,match='resultados'):prepare_capture(json.dumps({'schema_version':'stock-dashboard-v1'}))


def test_capture_rebuilds_only_from_auditable_prices_and_splits():
    p=deepcopy(archived('MSFT'));p['historical'].pop('Referencia histórica auditada')
    raw,notes=prepare_capture(json.dumps(p));r,_=analysis_from_snapshot(json.loads(raw))
    assert notes and r.summary['target_1y']==pytest.approx(696.8406273758014)


def test_editing_other_cells_keeps_manual_pe_and_prior_growth():
    saved=per_settings({'scenarios':{'Base':{'growth':.10}}},'Manual',20.,.2,.2,'Referencia de prueba')
    baseline=pd.DataFrame({'growth':[.1],'margin':[.3],'pe':[20.]},index=['Base'])
    edited=pd.DataFrame([{'Escenario':'Base','g':10.,'m':35.,'p':20.}])
    result=edited_settings(saved,edited,baseline,{'growth':'g','margin':'m','pe':'p'})
    assert result['scenarios']['Base']=={'growth':.1,'margin':.35,'pe':20.}
    assert 'margin' not in saved['scenarios']['Base']


def test_streamlit_per_and_other_settings_persist_through_reruns(tmp_path,monkeypatch):
    from streamlit.testing.v1 import AppTest
    p=deepcopy(archived('MSFT'));p['evidence']['stock_model']['settings']={'scenarios':{'Base':{'growth':.10}},'policy':{'required_return':.12}}
    path=tmp_path/'capture.json';path.write_text(json.dumps(p));monkeypatch.setenv('VALUACION_DASHBOARD_SNAPSHOT',str(path))
    a=AppTest.from_file(ROOT/'dashboard_app.py').run(timeout=40);assert not a.exception
    next(r for r in a.radio if r.label=='Modo del PER').set_value('Manual')
    next(n for n in a.number_input if n.label=='PER objetivo Base').set_value(20.)
    next(t for t in a.text_input if t.label=='Justificación del PER').set_value('Prueba de persistencia')
    next(b for b in a.button if b.label=='Aplicar referencia PER').click().run(timeout=40);assert not a.exception
    before=json.loads(a.session_state['settings']);assert before['scenarios']['Base']['growth']==.10
    next(b for b in a.button if b.label=='Recalcular escenarios').click().run(timeout=40);assert not a.exception
    after=json.loads(a.session_state['settings']);assert after['scenarios']['Base']['pe']==20. and after['scenarios']['Base']['growth']==.10
    next(s for s in a.selectbox if s.label=='Previsión gráfica').set_value('3 años').run(timeout=40)
    assert json.loads(a.session_state['settings'])==after


def test_three_year_target_survives_missing_one_year():
    p=archived('MSFT');r,_=analysis_from_snapshot(p);v=r.valuation.copy()
    v.loc[v['Horizonte (años)'].eq(1),'Precio objetivo']=np.nan
    d=chart_data(p,r.summary,v,'1 semana','3 años');future=d[d['Tipo'].eq('Proyección')]
    assert len(future)==6 and future['Fecha'].max()==pd.Timestamp(r.summary['as_of'])+pd.DateOffset(years=3)
    assert not (future['Fecha']==pd.Timestamp(r.summary['as_of'])+pd.DateOffset(years=1)).any()


def test_legacy_manual_capture_keeps_prices_when_recalculating_other_form(tmp_path,monkeypatch):
    from streamlit.testing.v1 import AppTest
    p=deepcopy(archived('MSFT'));p['historical'].pop('Referencia histórica auditada');p['historical'].pop('Precios y splits')
    p['evidence']['stock_model']['settings']=per_settings({},'Manual',20.,.2,.2,'Sensibilidad de reproducción: sin referencias históricas archivadas')
    path=tmp_path/'legacy.json';path.write_text(json.dumps(p));monkeypatch.setenv('VALUACION_DASHBOARD_SNAPSHOT',str(path))
    a=AppTest.from_file(ROOT/'dashboard_app.py').run(timeout=40)
    before=a.metric[1].value;assert before!='—' and not a.exception
    next(b for b in a.button if b.label=='Recalcular escenarios').click().run(timeout=40)
    assert a.metric[1].value==before and json.loads(a.session_state['settings'])['scenarios']['Base']['pe']==20.


def test_model_fingerprint_changes_with_financial_source(tmp_path):
    from estado_dashboard import model_fingerprint
    for name in ['analisis_acciones.py','flujo_acciones.py','historico_acciones.py','revision_economica.py']:(tmp_path/name).write_text('base')
    before=model_fingerprint(tmp_path);(tmp_path/'analisis_acciones.py').write_text('revision')
    assert model_fingerprint(tmp_path)!=before
