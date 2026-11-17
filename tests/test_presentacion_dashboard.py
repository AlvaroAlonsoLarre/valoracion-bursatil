"""Aceptación de las modificaciones de presentación solicitadas, con capturas fechadas."""
from copy import deepcopy
import json
from pathlib import Path
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest
from tests.test_v7_integrada import archived
from flujo_acciones import analysis_from_snapshot
from seguimiento_servicio import Service
from seguimiento_store import Store
from seguimiento_metricas import summarize,discount_color
from seguimiento_ui import DEFAULT_COLUMNS,COLUMNS,COLUMN_LABELS
from presentacion_dashboard import historico_compacto,vista,numero,resumen_metricas,ANNUAL_REMOVE,ANNUAL_HIDDEN,fechas_grafico_trimestral

ROOT=Path(__file__).resolve().parents[1]


def test_financial_display_preserves_sources_and_same_scale_across_windows():
    p=deepcopy(archived('NFLX'));before=json.dumps(p,sort_keys=True)
    r,t=analysis_from_snapshot(p)
    compact=historico_compacto(t['Estadisticas 5 y 10'])
    assert list(compact)[:5]==['Indicador','Media 5 años','Media 10 años','Mediana 5 años','Mediana 10 años']
    assert list(compact)[-2:]==['Dispon. Datos 5 años','Dispon. Datos 10 años']
    row=compact.set_index('Indicador').loc['Ingresos']
    raw=t['Estadisticas 5 y 10'].query("Indicador=='Ingresos' and `Ventana (ejercicios)`==5").iloc[0]
    assert row['Media 5 años']==raw['Media']
    assert row['Dispon. Datos 5 años']==f'{int(raw["Observaciones"])}/5'
    scaled,_=vista(t['Financieros anuales'][['Fecha cierre fiscal','Ingresos','EPS diluido']],'USD')
    assert 'Ingresos (MM $)' in scaled.data
    assert scaled.data['Ingresos (MM $)'].iloc[-1]==pytest.approx(t['Financieros anuales']['Ingresos'].iloc[-1]/1e9)
    assert scaled.data['Fecha cierre fiscal'].str.fullmatch(r'\d{4}/\d{2}/\d{2}').all()
    assert numero(1234567.89)=='1.234.567,89'
    assert numero(float('nan'))=='—'
    missing,_=vista(pd.DataFrame({'Fecha cierre fiscal':[pd.NaT]}),'USD')
    assert pd.isna(missing.data.iloc[0,0])
    assert json.dumps(p,sort_keys=True)==before
    assert len(list(resumen_metricas(p,r)))==10


def test_new_sign_and_ev_reference_migrate_without_sources(tmp_path,monkeypatch):
    p=deepcopy(archived('NFLX'));r,_=analysis_from_snapshot(p);m=summarize(p,r)
    row=m['row'];pe=row['PER actual TTM'];hist=row['PER mediana 5 FY']
    if pe and hist:assert row['Diferencia PER con histórico (%)']==pytest.approx(100*(pe/hist-1))
    assert '#dcfce7' in discount_color(-20) and '#fee2e2' in discount_color(20)
    assert row['EV/EBITDA comparables TTM Yahoo']==m['informative_peers']['stats']['EV/EBITDA Yahoo']['median']
    store=Store(tmp_path);service=Service(store,None);service.save_capture(p)
    old=deepcopy(store.entry('NFLX')['metrics']);old['schema_version']=4;old['financial_updated']=1234.;old['quote_queried_at']=1235.
    store.update_metrics('NFLX',old)
    monkeypatch.setattr('seguimiento_servicio.provider_profile',lambda *a,**k:pytest.fail('La migración no descarga datos'))
    upgraded=service.ensure_metrics(store.entry('NFLX'))['metrics']
    assert upgraded['schema_version']==5 and upgraded['financial_updated']==1234. and upgraded['quote_queried_at']==1235.
    assert 'Diferencia PER con histórico (%)' in upgraded['row']


def test_compact_ui_controls_defaults_and_metrics(tmp_path,monkeypatch):
    store=Store(tmp_path);Service(store).save_capture(archived('NFLX'));store.set_meta('selected_company','NFLX')
    monkeypatch.setenv('VALUACION_WATCHLIST_DIR',str(tmp_path));monkeypatch.delenv('VALUACION_DASHBOARD_SNAPSHOT',raising=False)
    app=AppTest.from_file(ROOT/'dashboard_app.py').run(timeout=50)
    assert not app.exception
    watch,summary,historical,quarterly,peers=app.tabs[:5]
    controls=next(m for m in watch.multiselect if m.label=='Columnas visibles')
    assert controls.value==DEFAULT_COLUMNS
    assert COLUMN_LABELS['Cobertura QoQ'] in controls.options and 'Cobertura QoQ' not in controls.value
    assert not any('comparables B' in c for c in controls.value)
    assert 'EV/EBITDA comparables TTM Yahoo' in controls.value
    elements=list(watch);table_index=next(i for i,e in enumerate(elements) if e.type=='dataframe')
    assert next(i for i,e in enumerate(elements) if e.type=='text_input' and e.label=='Buscar empresa o ticker')<table_index
    assert next(i for i,e in enumerate(elements) if e.type=='button' and e.label=='Eliminar empresa')<table_index
    assert len(summary.metric)==14
    assert any('BPA diluido' in m.label for m in summary.metric)
    assert any('Deuda neta/EBITDA' in m.label for m in summary.metric)
    annual=next(m for m in historical.multiselect if m.key=='columns_anuales')
    assert not set(ANNUAL_REMOVE)&set(annual.options)
    assert set(ANNUAL_HIDDEN)&set(annual.options) and not set(ANNUAL_HIDDEN)&set(annual.value)
    assert any(e.label=='Comparación de datos SEC-Yahoo' for e in quarterly.expander)
    assert not any('controles de valoración' in str(x.value) for x in peers.markdown)


def test_chart_dates_use_only_stored_publications_or_explicit_fiscal_fallback():
    q=pd.DataFrame({'Cierre':['2026-03-31','2026-06-30'],'Ingresos':[10.,12.],'Beneficio neto':[1.,2.],
        'Publicación de resultados estimada/registrada':['2026-04-20','2026-07-20']})
    plot,label,_=fechas_grafico_trimestral(q,'2026-11-17')
    assert plot['Trimestre'].tolist()==['2026/04/20','2026/07/20'] and 'Yahoo' in label
    q.loc[1,'Publicación de resultados estimada/registrada']=None
    plot,label,note=fechas_grafico_trimestral(q,'2026-11-17')
    assert plot['Trimestre'].tolist()==['2026/03/31','2026/06/30'] and label=='Cierre del trimestre'
    assert 'Faltan fechas' in note
