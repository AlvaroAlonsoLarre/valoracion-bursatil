"""Orden visual y sincronización real de hipótesis, sin descargar fuentes."""
from copy import deepcopy
import json
import os
from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest
from seguimiento_store import Store
from seguimiento_servicio import Service
from flujo_acciones import analysis_from_snapshot

ROOT=Path(__file__).resolve().parents[1]


def capture():
    path=os.environ.get('VALUACION_TEST_CAPTURE')
    if path:return json.loads(Path(path).read_text())
    from tests.test_v7_integrada import archived
    return deepcopy(archived('NFLX'))


def test_order_and_bidirectional_per_persistence(tmp_path,monkeypatch):
    p=capture();ticker=p['kwargs']['ticker'];store=Store(tmp_path)
    Service(store).save_capture(p);store.set_meta('selected_company',ticker)
    monkeypatch.setenv('VALUACION_WATCHLIST_DIR',str(tmp_path))
    monkeypatch.delenv('VALUACION_DASHBOARD_SNAPSHOT',raising=False)
    monkeypatch.setattr('seguimiento_ui.Service.refresh',lambda *a,**k:pytest.fail('No consultar red al editar PER'))
    app=AppTest.from_file(ROOT/'dashboard_app.py').run(timeout=45)
    assert not app.exception
    watch,summary=app.tabs[:2]
    elements=list(watch)
    table=next(i for i,e in enumerate(elements) if e.type=='dataframe')
    chart=next(i for i,e in enumerate(elements) if e.type=='vega_lite_chart')
    controls=next(i for i,e in enumerate(elements) if e.type=='radio' and e.label=='Modo del PER')
    assert table<chart<controls
    assert len(watch.radio)==len(summary.radio)==1
    assert watch.radio[0].key!=summary.radio[0].key
    automatic=analysis_from_snapshot(p)[0].summary['target_1y']
    watch.radio[0].set_value('Manual')
    next(n for n in watch.number_input if n.label=='PER objetivo Base').set_value(20.)
    next(n for n in watch.text_input if n.label=='Justificación del PER').set_value('Sensibilidad para comprobar las dos vistas')
    next(b for b in watch.button if b.label=='Aplicar referencia PER').click().run(timeout=45)
    assert not app.exception
    watch,summary=app.tabs[:2]
    assert watch.radio[0].value==summary.radio[0].value=='Manual'
    assert store.entry(ticker)['payload']['evidence']['stock_model']['settings']['scenarios']['Base']['pe']==20.
    summary.radio[0].set_value('Automático')
    next(b for b in summary.button if b.label=='Aplicar referencia PER').click().run(timeout=45)
    assert not app.exception
    assert app.tabs[0].radio[0].value==app.tabs[1].radio[0].value=='Automático'
    restored=analysis_from_snapshot(store.entry(ticker)['payload'])[0]
    assert restored.summary['target_1y']==pytest.approx(automatic)
