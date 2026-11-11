# -*- coding: utf-8 -*-
"""Panel interactivo local de valoración bursátil mediante Yahoo Finance."""
from __future__ import annotations

import io
import os
import re
import sys
import tempfile
import subprocess
import unicodedata
from pathlib import Path
from datetime import datetime
from typing import Any

import numpy as np
import altair as alt
import pandas as pd
import streamlit as st

BASE_DIR = Path(__file__).resolve().parent
ENGINE_PATH = BASE_DIR / "valoracion_engine.py"

st.set_page_config(
    page_title="Panel de valoración bursátil",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
      .stApp { background: #f4f7fb; }
      .block-container { padding-top: 1.6rem; padding-bottom: 3rem; max-width: 1500px; }
      h1, h2, h3 { color: #142b4a; }
      .hero {
        padding: 1.35rem 1.55rem; border-radius: 18px;
        background: linear-gradient(120deg, #102b4e 0%, #1e5278 100%);
        color: #ffffff; margin-bottom: 1rem;
      }
      .hero h1 { color: #ffffff; margin: 0 0 .35rem 0; font-size: 2rem; }
      .hero p { color: #dce9f5; margin: 0; font-size: 1rem; }
      div[data-testid="stMetric"] {
        background: #ffffff; border: 1px solid #e1e8f0; padding: 1rem 1.1rem;
        border-radius: 14px; box-shadow: 0 2px 8px rgba(20,43,74,.04);
      }
      div[data-testid="stMetricLabel"] { color: #52677f; }
      div[data-testid="stMetricValue"] { color: #102b4e; }
      div[data-testid="stTabs"] button { font-weight: 600; }
      .subtle { color: #65758b; font-size: .9rem; }
      .section-note { color: #586b81; font-size: .9rem; margin-top: -.35rem; }
      div[data-testid="stDataFrame"] { border: 1px solid #e2e8f0; border-radius: 10px; overflow: hidden; }
    </style>
    """,
    unsafe_allow_html=True,
)


def clean_key(text: Any) -> str:
    s = unicodedata.normalize("NFKD", str(text))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", s.lower())


def read_excel_bytes(data: bytes) -> dict[str, pd.DataFrame]:
    with pd.ExcelFile(io.BytesIO(data)) as workbook:
        return {name: workbook.parse(name) for name in workbook.sheet_names}


def clean_table(df: pd.DataFrame | None) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    result = df.copy()
    result.columns = [str(c) for c in result.columns]
    # Excel añade una columna Unnamed cuando un DataFrame se exportó con índice.
    renamed = {}
    for col in result.columns:
        if col.startswith("Unnamed:"):
            if "Indicador" not in result.columns and "Métrica" not in result.columns and "Concepto" not in result.columns:
                renamed[col] = "Indicador"
            else:
                renamed[col] = "Índice"
    return result.rename(columns=renamed)


def lookup_value(sheets: dict[str, pd.DataFrame], sheet_name: str, concept: str, value_col: str = "Valor"):
    df = sheets.get(sheet_name, pd.DataFrame())
    if df.empty:
        return None
    key_col = None
    wanted = clean_key(concept)
    for col in df.columns:
        if clean_key(col) in {"concepto", "indicador", "metrica", "unnamed0", "indice"}:
            key_col = col
            break
    if key_col is None:
        key_col = df.columns[0]
    val_col = value_col if value_col in df.columns else (df.columns[1] if len(df.columns) > 1 else None)
    if val_col is None:
        return None
    matches = df[df[key_col].astype(str).map(clean_key) == wanted]
    if matches.empty:
        # Permitir búsquedas parciales, útiles con cambios en etiquetas de Yahoo.
        matches = df[df[key_col].astype(str).map(clean_key).str.contains(wanted, regex=False)]
    if matches.empty:
        return None
    return matches.iloc[0][val_col]


def fmt_number(value: Any, decimals: int = 2, suffix: str = "") -> str:
    try:
        number = float(value)
        if pd.isna(number):
            return "No disponible"
        return f"{number:,.{decimals}f}{suffix}"
    except (TypeError, ValueError):
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return "No disponible"
        return str(value)


def safe_text(value: Any, fallback: str) -> str:
    if value is None:
        return fallback
    try:
        if pd.isna(value):
            return fallback
    except (TypeError, ValueError):
        pass
    value = str(value).strip()
    return fallback if value.lower() in {"", "nan", "nat", "none"} else value


def fmt_date(value: Any) -> str:
    if value is None or pd.isna(value) or str(value).strip() in {"", "NaT", "nan"}:
        return "No disponible"
    try:
        return pd.to_datetime(value).strftime("%d/%m/%Y")
    except (TypeError, ValueError):
        return str(value)


def run_analysis(ticker: str, num_quarters: int, sec_contact_email: str = "", assumptions: dict | None = None) -> dict[str, Any]:
    if not ENGINE_PATH.exists():
        raise FileNotFoundError(f"No se encuentra el motor de cálculo: {ENGINE_PATH}")
    clean_ticker = re.sub(r"[^A-Za-z0-9_.^=-]", "", ticker.strip().upper())
    if not clean_ticker:
        raise ValueError("Introduce un ticker válido, por ejemplo MSFT, AAPL o SAN.MC.")

    env = os.environ.copy()
    env["VALUACION_TICKER"] = clean_ticker
    env["VALUACION_NUM_TRIMESTRES"] = str(int(num_quarters))
    email = sec_contact_email.strip()
    if email:
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            raise ValueError("Introduce un correo de contacto SEC válido.")
        env["VALUACION_SEC_USER_AGENT"] = f"StockValuationDashboard/2.0 (contact: {email})"

    if assumptions:
        for key,value in assumptions.items():
            if value is not None:
                env['VALUACION_'+key] = str(value)

    with tempfile.TemporaryDirectory(prefix=f"yahoo_{clean_ticker}_") as temp_dir:
        proc = subprocess.run(
            [sys.executable, "-u", str(ENGINE_PATH)],
            cwd=temp_dir,
            env=env,
            capture_output=True,
            text=True,
            timeout=900,
            check=False,
        )
        safe_ticker = re.sub(r"[^A-Za-z0-9_.-]", "_", clean_ticker)
        excel_files = sorted(
            Path(temp_dir).glob(f"valoracion_completa_{safe_ticker}*.xlsx"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if proc.returncode != 0 or not excel_files:
            details = (proc.stderr or "")[-9000:]
            output = (proc.stdout or "")[-3500:]
            message = details.strip() or output.strip() or "El motor terminó sin crear el Excel."
            raise RuntimeError(
                "No se pudo completar el análisis con Yahoo Finance.\n\n"
                + message
            )
        excel_data = excel_files[0].read_bytes()
        # Exportación persistente junto al dashboard, independiente de cwd.
        # Se evita perder el Excel cuando TemporaryDirectory se elimina.
        out_dir = ENGINE_PATH.parent / "Resultados"
        out_dir.mkdir(parents=True, exist_ok=True)
        output_path = out_dir / f"valoracion_{safe_ticker}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.xlsx"
        output_path.write_bytes(excel_data)
        sheets = read_excel_bytes(excel_data)
        return {
            "ticker": clean_ticker,
            "sheets": sheets,
            "excel_bytes": excel_data,
            "excel_name": output_path.name,
            "saved_path": str(output_path),
            "stdout": proc.stdout or "",
            "stderr": proc.stderr or "",
        }


def get_df(sheets: dict[str, pd.DataFrame], key: str) -> pd.DataFrame:
    return clean_table(sheets.get(key, pd.DataFrame()))


def show_df(sheets: dict[str, pd.DataFrame], key: str, *, height: int = 360, use_container_width: bool = True):
    df = get_df(sheets, key)
    if df.empty:
        st.info("Yahoo Finance no ha devuelto datos para esta tabla.")
        return
    financial_tabs={"Financieros anuales","Resultados trimestrales","Proyeccion negocio","Supuestos fundamentales","DCF detalle","ROIC capital medio","Valoracion historica"}
    table_cur=(st.session_state.get("financial_currency","USD") if key in financial_tabs else st.session_state.get("display_currency","USD"))
    show_table(df, height=height, currency=table_cur)


# Descripciones emergentes de unidad en los encabezados de todas las tablas.
def unit_for_column(name: str, currency: str = "USD") -> str:
    key = clean_key(name)
    if any(x in key for x in ("fecha", "ejercicio", "trimestre", "publicacion", "cierre", "horizonte")) and "precio" not in key:
        return "Fecha o periodo; sin unidad monetaria."
    if any(x in key for x in ("porcentaje", "pct", "margen", "yield", "rentabilidad", "cagr", "crecimiento", "tasa", "potencial", "roe", "roic")):
        return "Porcentaje (%); salvo indicación contraria."
    if key in {"per", "pertrailing", "perforward", "ev/ebitda", "ev/ingresos", "ev/fcf", "p/ventas", "p/valorcontable", "beta"} or any(x in key for x in ("peraplicado", "permedio", "desviacionestandarper", "deudaneta/ebitda", "deudapatrimonio", "coberturadeintereses", "multiple")):
        return "Múltiplo (veces, ×); beta no tiene unidad."
    if "divisafinanciera" in key:
        return "Divisa financiera de las cuentas (mira General)."
    if any(x in key for x in ("eps", "precioactual", "preciobjetivo", "precioobjetivo", "preciocierre", "preciocompra", "precioestimado")):
        return f"{currency} por acción; ver columna si se especifica otra divisa."
    if "acciones" in key:
        return "Número de acciones; revisar la tabla para saber si está expresado en unidades o miles de millones."
    if any(x in key for x in ("ingresos", "beneficio", "ebitda", "capex", "fcf", "efectivo", "inversion", "deuda", "capitalizacion", "patrimonio", "activos", "flujo", "dividend", "impuestos", "nopat", "capitalinvertido", "ev")):
        return f"Miles de millones de {currency}, salvo si la cabecera indica otra unidad."
    if "numero" in key or "datos" in key or "intervalos" in key:
        return "Recuento de observaciones (número)."
    return "Dato identificativo, valor sin unidad o consultar la definición en la tabla."


def show_table(df: pd.DataFrame, *, height: int = 360, currency: str = "USD"):
    if df is None or df.empty:
        st.info("No hay datos disponibles para esta tabla.")
        return
    config = {str(c): st.column_config.Column(str(c), help=unit_for_column(str(c), currency)) for c in df.columns}
    st.dataframe(df, use_container_width=True, hide_index=True, height=height, column_config=config)


def make_peer_comparison(stats: pd.DataFrame, quarters: pd.DataFrame) -> pd.DataFrame:
    if stats.empty:
        return pd.DataFrame()
    quarter = quarters.iloc[0] if not quarters.empty else pd.Series(dtype=object)
    mapping = {
        "PER trailing": "PER TTM", "EV/EBITDA": "EV/EBITDA TTM",
        "Margen neto (%)": "Margen neto", "Margen operativo (%)": "Margen operativo",
        "ROE (%)": "ROE trimestral anualizado (%)", "Deuda/Patrimonio (%)": "Deuda/Patrimonio (%)",
        "Rentabilidad FCF (%)": "Rentabilidad FCF TTM (%)", 
    }
    rows = []
    for _, item in stats.iterrows():
        metric = str(item.get("Métrica", item.iloc[0]))
        peer = pd.to_numeric(item.get("Media comparables"), errors="coerce")
        source = mapping.get(metric)
        value = pd.to_numeric(quarter.get(source), errors="coerce") if source else np.nan
        difference = value - peer if pd.notna(value) and pd.notna(peer) else np.nan
        rows.append({"Métrica": metric, "Media comparables": peer, "Último trimestre / TTM": value, "Diferencia (empresa − media)": difference})
    return pd.DataFrame(rows)


def show_peer_comparison(df: pd.DataFrame, currency: str = "USD"):
    if df.empty:
        st.info("No se dispone de estadísticas comparables.")
        return
    def tint(x):
        if pd.isna(x): return ""
        return "background-color: #d9f4df; color: #165b2d" if x > 0 else ("background-color: #fbe0df; color: #8b2323" if x < 0 else "")
    fmt = {c: "{:.2f}" for c in df.columns if c != "Métrica"}
    styled = df.style.format(fmt, na_rep="N/D").map(tint, subset=["Diferencia (empresa − media)"])
    st.dataframe(styled, use_container_width=True, hide_index=True, height=530,
        column_config={c: st.column_config.Column(c, help=("Diferencia = valor de la empresa menos media de comparables. Verde: positiva; rojo: negativa. No equivale necesariamente a valoración favorable." if c.startswith("Diferencia") else unit_for_column(c, currency))) for c in df.columns})


def show_quarter_charts(quarterly: pd.DataFrame, currency: str = "USD"):
    if quarterly.empty:
        st.info("No hay resultados trimestrales para representar.")
        return
    data = quarterly.copy()
    date_col = next((c for c in ("Cierre del trimestre", "Fecha cierre fiscal") if c in data), None)
    if date_col is None:
        st.warning("Falta la fecha del trimestre para construir las gráficas.")
        return
    data["_fecha"] = pd.to_datetime(data[date_col], dayfirst=True, errors="coerce")
    data = data.dropna(subset=["_fecha"]).sort_values("_fecha")
    charts = [
        ("Ingresos", "Ingresos", f"Miles de millones de {currency}"),
        ("Beneficio operativo", "Beneficio operativo", f"Miles de millones de {currency}"),
        ("EPS diluido", "EPS diluido", f"{currency}/acción"),
        ("Deuda neta", "Deuda neta", f"Miles de millones de {currency}"),
        ("FCF", "Flujo de caja libre", f"Miles de millones de {currency}"),
        ("CAPEX", "CAPEX", f"Miles de millones de {currency}"),
        ("EBITDA", "EBITDA aproximado", f"Miles de millones de {currency}"),
        ("PER trimestral (anualizado)", "PER trimestral anualizado", "veces (×)"),
        ("EV/EBITDA trimestral (anualizado)", "EV/EBITDA trimestral anualizado", "veces (×)"),
        ("Deuda neta / EBITDA trimestral (anualizado)", "Deuda neta / EBITDA trimestral anualizado", "veces (×)"),
    ]
    for start in range(0,len(charts),2):
        cols=st.columns(2)
        for col,(label,field,unit) in zip(cols,charts[start:start+2]):
            with col:
                st.markdown(f"**{label}**")
                if field not in data.columns:
                    st.caption("Sin datos trimestrales disponibles para esta métrica.")
                    continue
                plot=data[["_fecha",field]].copy()
                plot[field]=pd.to_numeric(plot[field],errors="coerce")
                plot=plot.replace([np.inf,-np.inf],np.nan).dropna()
                if plot.empty:
                    st.caption("Sin observaciones suficientes para representar.")
                    continue
                chart=(alt.Chart(plot).mark_line(point=True).encode(
                    x=alt.X("_fecha:T",title="Cierre trimestral"),
                    y=alt.Y(f"{field}:Q",title=unit,scale=alt.Scale(zero=False)),
                    tooltip=[alt.Tooltip("_fecha:T",title="Trimestre",format="%d/%m/%Y"),alt.Tooltip(f"{field}:Q",title=label,format=",.2f")],
                ).properties(height=230))
                st.altair_chart(chart,use_container_width=True)


def metric_from_df(df: pd.DataFrame, metric: str, value_col: str | None = None):
    if df.empty:
        return None
    df = clean_table(df)
    key_col = next((c for c in df.columns if clean_key(c) in {"concepto", "indicador", "metrica", "indice"}), df.columns[0])
    wanted = clean_key(metric)
    rows = df[df[key_col].astype(str).map(clean_key) == wanted]
    if rows.empty:
        return None
    if value_col and value_col in rows.columns:
        return rows.iloc[0][value_col]
    value_candidates = [c for c in rows.columns if c != key_col]
    return rows.iloc[0][value_candidates[0]] if value_candidates else None


def card(label: str, value: str, help_text: str | None = None):
    st.metric(label, value, help=help_text)


st.markdown(
    "<div class='hero'><h1>Panel de valoración bursátil</h1>"
    "<p>Histórico anual SEC EDGAR · cotización, resultados trimestrales y comparables Yahoo Finance</p></div>",
    unsafe_allow_html=True,
)

with st.form("ticker_form", clear_on_submit=False):
    c1, c2, c3, c4 = st.columns([2.1, .8, 2.0, 1.1])
    ticker_input = c1.text_input("Ticker de Yahoo Finance", value=st.session_state.get("ticker_input", "MSFT"), placeholder="MSFT, AAPL, GOOGL, SAN.MC…")
    quarter_count = c2.selectbox("Trimestres", options=[4, 6, 8, 12, 16], index=3)
    sec_email_input = c3.text_input("Correo de contacto SEC", value=st.session_state.get("sec_contact_email", ""), placeholder="tu-correo@ejemplo.com", help="La SEC recomienda identificar las peticiones automatizadas. Se usa para el encabezado de consulta, no se añade al Excel.")
    with st.expander("Hipótesis de proyección (opcionales; dejar en blanco para cálculo automático)"):
        h1,h2,h3,h4=st.columns(4)
        input_wacc=h1.text_input("WACC (%)",placeholder="Ej. 9.5",help="Si se rellena, debe ser apropiado para la divisa y riesgo de esta empresa.")
        input_gterm=h2.text_input("Crecimiento terminal (%)",placeholder="Ej. 2.5")
        input_gventas=h3.text_input("Crecimiento anual ventas (%)",placeholder="Automático")
        input_nwc=h4.text_input("Capital trabajo / incremento ventas (%)",placeholder="Ej. 1.0")
    manual_peers=st.text_input(
        "Añadir comparables manuales (opcional; normalmente dejar vacío)",
        placeholder="Automático para cualquier ticker. Opcional: ORCL,SAP,CRM",
        help="La selección es automática por actividad y resultados financieros. Puedes añadir candidatos, pero deben superar los mismos filtros.")
    with st.expander("Ajustes avanzados: riesgo, ciclo y margen sostenible"):
        a1,a2,a3,a4=st.columns(4)
        input_rf=a1.text_input("Tipo libre riesgo (%)",placeholder="Por divisa, configurable")
        input_erp=a2.text_input("Prima riesgo mercado (%)",placeholder="5.5")
        input_margen=a3.text_input("Margen EBIT de ciclo (%)",placeholder="Solo para negocio cíclico")
        input_ciclo=a4.selectbox("Empresa cíclica",options=["Automático","Sí","No"])
    c4.markdown("<div style='height: 1.8rem'></div>", unsafe_allow_html=True)
    submitted = c4.form_submit_button("Analizar empresa", type="primary", use_container_width=True)

if submitted:
    st.session_state["ticker_input"] = ticker_input.strip().upper()
    st.session_state["sec_contact_email"] = sec_email_input.strip()
    try:
        with st.spinner(f"Consultando SEC EDGAR + Yahoo Finance y calculando métricas de {ticker_input.strip().upper()}… Puede tardar según la cobertura del ticker."):
            custom={}
            for env_key, raw in [
                ("WACC",input_wacc),("CRECIMIENTO_TERMINAL",input_gterm),
                ("CRECIMIENTO_VENTAS",input_gventas),("VAR_CAPITAL_TRABAJO_PCT",input_nwc),
            ]:
                if raw.strip():
                    try:
                        custom[env_key]=float(raw.replace(',','.'))/100
                    except ValueError:
                        raise ValueError(f"Valor no válido en {env_key}: {raw}")
            for ek,raw in [("TIPO_LIBRE_RIESGO",input_rf),
                           ("PRIMA_RIESGO_MERCADO",input_erp),
                           ("MARGEN_NORMALIZADO",input_margen)]:
                if raw.strip():
                    try:custom[ek]=float(raw.replace(',','.'))/100
                    except ValueError:raise ValueError(f"Valor no válido para {ek}: {raw}")
            if input_ciclo!="Automático":
                custom['EMPRESA_CICLICA']='1' if input_ciclo=='Sí' else '0'
            if manual_peers.strip():
                import re as _re
                manual_list=[v.strip().upper() for v in _re.split(r'[,;\s]+',manual_peers) if v.strip()]
                if any(not _re.fullmatch(r'[A-Z0-9][A-Z0-9.\-^=]{0,20}',t) for t in manual_list):
                    raise ValueError('Ticker inválido en comparables manuales')
                custom['COMPARABLES']=','.join(manual_list[:15])
            st.session_state["analysis_result"] = run_analysis(ticker_input, quarter_count, sec_email_input, custom)
            st.session_state["analysis_error"] = None
    except Exception as error:
        st.session_state["analysis_error"] = str(error)
        st.session_state.pop("analysis_result", None)

if st.session_state.get("analysis_error"):
    st.error("No se pudo completar el análisis.")
    st.code(st.session_state["analysis_error"], language="text")

result = st.session_state.get("analysis_result")
if result:
    sheets = result["sheets"]
    ticker = result["ticker"]
    company = safe_text(lookup_value(sheets, "General", "Empresa"), ticker)
    currency = safe_text(lookup_value(sheets, "General", "Divisa de cotización"), safe_text(lookup_value(sheets, "General", "Divisa financiera"), "divisa"))
    financial_currency = safe_text(lookup_value(sheets, "General", "Divisa financiera"), currency)
    current_df = sheets.get("Valoracion actual", pd.DataFrame())
    annual_df = sheets.get("Financieros anuales", pd.DataFrame())
    quarterly_df = sheets.get("Resultados trimestrales", pd.DataFrame())
    history_df = sheets.get("Valoracion historica", pd.DataFrame())
    current = lambda key: lookup_value(sheets, "Valoracion actual", key)

    st.subheader(f"{company} ({ticker})")
    annual_source = safe_text(lookup_value(sheets, "General", "Fuente histórico anual"), "Fuente anual no indicada")
    cik_source = safe_text(lookup_value(sheets, "General", "CIK SEC"), "No disponible")
    st.caption(
        f"Divisa de cotización: {currency}; divisa contable: {financial_currency} · Histórico anual: {annual_source} · "
        f"CIK SEC: {cik_source} · Cotización actual, datos trimestrales y comparables: Yahoo Finance."
    )

    freshness=get_df(sheets,"Actualidad resultados")
    if not freshness.empty:
        status=str(freshness.iloc[0].get('status','')).upper()
        detail=str(freshness.iloc[0].get('detail',''))
        if status=='BLOQUEO':
            st.error('Publicación más reciente detectada: actualizar datos antes de utilizar los precios objetivo. '+detail)
        elif status in ('REVISAR','NO_VERIFICADO'):
            st.warning('Actualidad financiera '+status+': '+detail)
        else:
            st.caption('Control de actualidad financiera: '+detail)

    st.session_state["display_currency"] = currency
    st.session_state["financial_currency"] = financial_currency
    price = current("Precio actual")
    if price is None:
        price = current("Precio actual (divisa cotización/acción)")
    trailing_per = current("PER TTM publicado por Yahoo")
    eps = current("EPS del último ejercicio")
    if eps is None:
        eps = current("EPS del último ejercicio (divisa financiera/acción)")
    market_cap = current("Capitalización actual")
    if market_cap is None:
        market_cap = current("Capitalización actual (miles de millones)")
    last_fy = current("Último ejercicio fiscal disponible")

    m1, m2, m3, m4 = st.columns(4)
    with m1: card("Precio actual", f"{fmt_number(price)} {currency}")
    with m2: card("PER TTM", fmt_number(trailing_per, 2, "x"))
    with m3: card("EPS último ejercicio", f"{fmt_number(eps)} {financial_currency}")
    with m4: card("Capitalización", f"{fmt_number(market_cap)} B {currency}")

    # Verificación de cobertura: evita presentar una media de seis años como si
    # fuera una media de diez, incluso cuando la extracción SEC devuelve OK.
    num_years = len(annual_df)
    validation = get_df(sheets, "Resumen Yahoo SEC")
    if num_years >= 10 and "SEC" in annual_source:
        st.success(f"Histórico SEC disponible: {num_years} ejercicios fiscales; las ventanas de 5 y 10 años se pueden calcular.")
    elif "SEC" in annual_source:
        st.warning(f"Cobertura anual SEC incompleta: {num_years} ejercicios. El modelo fundamental sigue disponible si existen datos suficientes.")
    else:
        st.info(f"Fuente anual sin SEC: {annual_source}. {num_years} ejercicios; habitual en cotizaciones internacionales como 000660.KS.")
    if not validation.empty and "Diferencias >=1%" in validation.columns:
        total_ok = pd.to_numeric(validation["Coinciden (<1%)"], errors="coerce").sum()
        total_bad = pd.to_numeric(validation["Diferencias >=1%"], errors="coerce").sum()
        no_comp = pd.to_numeric(validation["No comparables"], errors="coerce").sum()
        if total_bad:
            st.error(f"Auditoría Yahoo–SEC: {int(total_bad)} discrepancias de al menos el 1 %. Revisa 'Datos y exportación'.")
        else:
            st.info(f"Auditoría Yahoo–SEC: {int(total_ok)} datos coinciden con diferencia inferior al 1 %; {int(no_comp)} no comparables por ausencia de datos u otras limitaciones.")

    tab_resumen,tab_modelo,tab_peers,tab_history,tab_scenarios,tab_quarters,tab_data = st.tabs([
        "Resumen", "Modelo fundamental", "Comparables", "Histórico y CAGR", "Histórico EPS/PER", "Resultados trimestrales", "Datos y exportación"
    ])

    with tab_resumen:
        st.markdown("### Precios objetivo a 1 año · proyección del negocio × PER forward")
        st.caption("Escenarios mecánicos, no consenso de analistas. Precios condicionados a supuestos; el potencial no incluye dividendos.")
        scenarios_top = get_df(sheets, "Valoracion fundamental")
        if not scenarios_top.empty:
            scenarios_top = scenarios_top[scenarios_top['Método'].eq('PER forward')].copy()
        if not scenarios_top.empty and "Horizonte (años)" in scenarios_top:
            one_year = scenarios_top[pd.to_numeric(scenarios_top["Horizonte (años)"], errors="coerce") == 1]
            scenario_cols = st.columns(3)
            for ix, name in enumerate(("Pesimista", "Base", "Optimista")):
                found = one_year[one_year["Escenario"].astype(str).map(clean_key) == clean_key(name)]
                with scenario_cols[ix]:
                    if not found.empty:
                        line = found.iloc[0]
                        target = pd.to_numeric(line.get("Precio objetivo (divisa cotización)"), errors="coerce")
                        potential = (target / float(price) - 1) * 100 if pd.notna(target) and pd.notna(pd.to_numeric(price, errors="coerce")) and float(price) > 0 else pd.to_numeric(line.get("Potencial acumulado (%)"),errors="coerce")
                        st.metric("Medio" if name == "Base" else name, f"{fmt_number(target)} {currency}", delta=(f"{potential:+.2f}% vs. actual" if pd.notna(potential) else None))
                    else:
                        st.metric("Medio" if name == "Base" else name, "N/D")
        else:
            st.info("No hay escenarios a un año; consulta los controles de divisa y datos disponibles.")
        st.caption("El histórico EPS×PER con medias de diez años se conserva en ‘Histórico EPS/PER’, pero ya no se presenta como previsión principal.")
        left, right = st.columns([1.05, 1.45], gap="large")
        with left:
            st.markdown("### Datos clave de la empresa")
            latest_annual = annual_df.iloc[-1] if not annual_df.empty else pd.Series(dtype=object)
            latest_quarter = quarterly_df.iloc[0] if not quarterly_df.empty else pd.Series(dtype=object)
            actual_rows = [
                ("Fecha de cierre fiscal", fmt_date(latest_annual.get("Fecha cierre fiscal", None))),
                ("Último trimestre disponible", fmt_date(latest_quarter.get("Cierre del trimestre", latest_quarter.get("Fecha cierre fiscal", None)))),
                ("Publicación asociada al último trimestre", fmt_date(latest_quarter.get("Publicación de resultados estimada/registrada", None))),
                ("Próxima publicación según Yahoo", fmt_date(lookup_value(sheets, "Fecha resultados", "Próxima publicación indicada por Yahoo", "Fecha"))),
                ("Ventas (último ejercicio, miles de millones)", fmt_number(latest_annual.get("Ingresos", np.nan))),
                ("Beneficio neto (miles de millones)", fmt_number(latest_annual.get("Beneficio neto", np.nan))),
                ("EPS diluido", fmt_number(latest_annual.get("EPS diluido", np.nan))),
                ("EBITDA aproximado (miles de millones)", fmt_number(latest_annual.get("EBITDA aproximado", np.nan))),
                ("CAPEX (miles de millones)", fmt_number(latest_annual.get("CAPEX", np.nan))),
                ("FCF (miles de millones)", fmt_number(latest_annual.get("Flujo de caja libre", np.nan))),
                ("Deuda neta (último balance, miles de millones)", fmt_number(lookup_value(sheets,"Supuestos fundamentales","Deuda neta reciente (miles MM)"))),
                ("PER forward Yahoo", fmt_number(current("PER forward publicado por Yahoo"), 2, "x")),
            ]
            show_table(pd.DataFrame(actual_rows, columns=["Indicador", "Valor"]), currency=currency)
        with right:
            st.markdown("### Comparables más similares")
            peers = get_df(sheets, "Comparables")
            if not peers.empty:
                preferred = ["Ticker", "Empresa", "Relación", "Precio actual", "PER trailing", "PER forward", "EV/EBITDA", "EV/Ingresos", "P/Ventas", "Rentabilidad FCF (%)", "Margen neto (%)", "ROE (%)"]
                show_table(peers[[c for c in preferred if c in peers.columns]], height=410, currency=currency)
                st.caption("Se muestran hasta 10 comparables. La compañía objetivo no se incluye en sus estadísticas.")
            else:
                st.info("No se han encontrado comparables utilizables para este ticker.")
            st.markdown("### Media y mediana de los comparables económicos")
            show_df(sheets, "Estadisticas peers economicos", height=270)

        st.markdown("### Comparación frente a la media de los comparables")
        peer_comparison = make_peer_comparison(get_df(sheets, "Estadisticas peers economicos"), quarterly_df)
        show_peer_comparison(peer_comparison, currency)
        st.caption("Diferencia = empresa − media de comparables, en puntos porcentuales para métricas en % y en veces para múltiplos. Verde significa mayor, no necesariamente mejor. Los múltiplos y rentabilidades usan TTM (4 trimestres); otras métricas no comparables se dejan N/D.")

        st.markdown("### Histórico de la compañía")
        hist_stats = get_df(sheets, "Estadisticas historicas")
        if not hist_stats.empty:
            cols_stats = ["Indicador", "Media 5 años", "Mediana 5 años", "Media 10 años", "Mediana 10 años", "Datos 5 años", "Datos 10 años"]
            show_table(hist_stats[[c for c in cols_stats if c in hist_stats.columns]], height=480, currency=currency)
            st.caption("Valores anuales SEC; cifras financieras en miles de millones, EPS y cotizaciones por acción, porcentajes donde se indica. 'Datos' es el número de observaciones no nulas; una media de 10 años requiere comprobar su cobertura.")
        else:
            st.info("No hay suficientes datos históricos para calcular medias y medianas.")
        cagr = get_df(sheets, "CAGR")
        if not cagr.empty:
            st.markdown("### CAGR histórico")
            cagr_cols = st.columns(min(3, len(cagr)))
            for i, (_, row) in enumerate(cagr.iterrows()):
                with cagr_cols[i % len(cagr_cols)]:
                    card(f"CAGR {row.get('Indicador', 'Indicador')}", fmt_number(row.get("CAGR (%)"), 2, "%"), help_text=f"{row.get('Ejercicio inicial', '')} a {row.get('Ejercicio final', '')}; {row.get('Intervalos anuales', '')} intervalos.")
        st.caption("Los importes de estados financieros se presentan en miles de millones de la divisa financiera; EPS y precios por acción. EBITDA, EV histórico y capitalización histórica son aproximaciones del modelo.")

    with tab_modelo:
        st.markdown("### Valoración fundamental · 1 y 3 años")
        st.caption("Proyección de ingresos→EBIT→beneficio/EPS, CAPEX y FCFF. Compara PER forward, EV/EBITDA forward y DCF a la fecha futura, sin promediar objetivos automáticamente. WACC y crecimiento terminal son supuestos editables, no estimaciones del mercado.")
        model_table=get_df(sheets,"Valoracion fundamental")
        if not model_table.empty:
            st.markdown("#### Precios objetivo y potencial")
            choice=st.radio("Horizonte fundamental",[1,3],horizontal=True,key="modelo_horizonte")
            filtered=model_table[pd.to_numeric(model_table["Horizonte (años)"],errors="coerce")==choice]
            show_table(filtered,currency=currency,height=360)
        else:
            st.warning("Valoraciones desactivadas por ausencia de datos críticos, FX no verificado o ratios no válidos. Consulta el control del modelo.")
        with st.expander("Controles de calidad y limitaciones",expanded=True):
            show_df(sheets,"Control modelo",height=320)
            st.markdown('**Control de nuevas publicaciones y retrasos de Yahoo**')
            show_df(sheets,"Actualidad resultados",height=145)
        st.markdown("#### Hipótesis utilizadas")
        show_df(sheets,"Supuestos fundamentales",height=390)
        st.markdown("#### Proyección operativa por escenario")
        show_df(sheets,"Proyeccion negocio",height=360)
        st.markdown("#### DCF: flujos descontados y valor terminal")
        show_df(sheets,"DCF detalle",height=310)
        st.markdown("#### Valoración inversa")
        show_df(sheets,"Valoracion inversa",height=180)
        st.markdown("#### ROIC con capital invertido medio")
        show_df(sheets,"ROIC capital medio",height=270)
        st.markdown("#### Base financiera TTM y balance más reciente")
        show_df(sheets,"Base TTM y balance",height=320)
        st.markdown("#### Puente al cierre fiscal del año en curso")
        show_df(sheets,"Puente ejercicio fiscal",height=280)
        st.info("La deuda neta se aproxima año a año mediante FCFF, intereses y pagos a accionistas; no se proyecta un balance completo. Los escenarios no incluyen guidance ni consenso. El último cierre TTM puede preceder a la fecha actual.")

    with tab_peers:
        st.markdown("### Comparables seleccionados")
        st.caption("V5: una sola clasificación de todo el universo internacional por similitud de negocio, actividad explícita y finanzas. Se descartan candidatos de baja confianza o con actividad incompatible; se muestra por qué.")
        show_df(sheets, "Comparables", height=460)
        st.markdown("### Comparables depurados para múltiplos forward")
        show_df(sheets, "Comparables depurados", height=350)
        st.caption("Solo empresas de confianza Media/Alta pueden entrar en la mediana; se exigen 3 valores válidos por múltiplo. No se reemplazan los comparables ausentes por el múltiplo de la propia compañía. Si faltan pares se muestra N/D.")
        with st.expander("Auditoría: universo de candidatos examinados y exclusiones"):
            show_df(sheets,"Universo comparables",height=490)
            st.caption("La similitud textual es heurística. Un producto o segmento de negocio minoritario no convierte a dos grupos en pares perfectos.")
        st.markdown("#### Medianas de comparables elegibles")
        show_df(sheets,"Referencia comparables",height=170)
        st.markdown("### Estadísticas de comparables económicos elegibles")
        show_df(sheets,"Estadisticas peers economicos",height=420)
        st.caption("Las estadísticas económicas se calculan una sola vez a partir de los candidatos aceptados; no se utiliza una media sectorial bruta para valorar.")
        st.markdown("### Empresa analizada frente a comparables")
        show_df(sheets, "Empresa y comparables", height=460)

    with tab_history:
        st.markdown("### Crecimiento compuesto (CAGR)")
        show_df(sheets, "CAGR", height=200)
        st.markdown("### Principales métricas: media y mediana (5 y 10 años)")
        show_df(sheets, "Estadisticas historicas", height=520)
        st.caption("Ventanas basadas en ejercicios fiscales SEC; las observaciones disponibles pueden ser inferiores a la longitud de la ventana. Datos contables en miles de millones, salvo EPS y acciones (miles de millones), ratios y porcentajes.")
        st.markdown("### Crecimientos de ventas, EPS y FCF: 5 y 10 años")
        show_df(sheets, "CAGR 5 y 10", height=270)
        st.caption("El CAGR utiliza los valores inicial y final y el número de intervalos; la media y mediana de crecimiento se calculan sobre variaciones interanuales, que representan una estadística distinta.")
        st.markdown("### Valoración por ejercicio fiscal")
        show_df(sheets, "Valoracion historica", height=430)
        st.markdown("### Estados financieros anuales")
        show_df(sheets, "Financieros anuales", height=430)
        st.markdown("### Crecimientos anuales de EPS y FCF")
        show_df(sheets, "Crecimientos EPS FCF", height=250)

    with tab_scenarios:
        st.markdown("### Análisis histórico EPS × PER · solo contraste, NO modelo central")
        st.warning("Estos escenarios heredados usan medias y desviaciones históricas, y el PER al cierre fiscal incorpora EPS conocido después. No deben interpretarse como predicciones ajustadas por riesgos o información point-in-time.")
        st.caption("Escenario medio: crecimiento anual medio del EPS y PER histórico medio obtenidos de los últimos 10 ejercicios. Los escenarios extremos incorporan ±1 desviación estándar. Si no existen 10 ejercicios, no se publican escenarios de este tipo.")
        scenarios = get_df(sheets, "Escenarios EPS PER")
        if not scenarios.empty and "Horizonte (años)" in scenarios.columns:
            horizon = st.radio("Horizonte de valoración", options=[1, 3], horizontal=True, format_func=lambda x: f"{x} año" if x == 1 else f"{x} años", key="scenario_horizon")
            filtered = scenarios[scenarios["Horizonte (años)"].astype(str).str.replace(".0", "", regex=False) == str(horizon)]
            preferred = ["Escenario", "EPS base último ejercicio", "Crecimiento anual EPS (%)", "EPS estimado", "PER medio histórico (ventana 10 años)", "PER: ejercicios válidos", "Crecimiento EPS: intervalos válidos", "Desviación estándar PER", "PER aplicado", "Precio objetivo", "Potencial acumulado (%)", "Rentabilidad anualizada (%)"]
            show_table(filtered[[c for c in preferred if c in filtered.columns]], currency=currency)
        else:
            st.info("No hay suficientes datos para calcular escenarios EPS/PER.")
        st.markdown("### Parámetros utilizados")
        show_df(sheets, "Parametros escenarios", height=200)
        st.markdown("### Escenarios basados en flujo de caja libre")
        fcf_scenarios = get_df(sheets, "Escenarios FCF")
        if not fcf_scenarios.empty and "Horizonte (años)" in fcf_scenarios.columns:
            hfcf = st.radio("Horizonte FCF", options=[1, 3], horizontal=True, format_func=lambda x: f"{x} año" if x == 1 else f"{x} años", key="fcf_horizon")
            fcf_filtered = fcf_scenarios[fcf_scenarios["Horizonte (años)"].astype(str).str.replace(".0", "", regex=False) == str(hfcf)]
            show_table(fcf_filtered, currency=currency)
        else:
            st.info("No hay suficientes ejercicios y datos SEC de los últimos diez años para construir escenarios FCF.")
        st.markdown("### Comparación de métodos")
        show_df(sheets, "Comparacion", height=270)
        st.warning("Los escenarios son resultados matemáticos condicionados a hipótesis históricas; no son predicciones garantizadas ni recomendaciones de inversión.")

    with tab_quarters:
        st.markdown("### Últimos resultados trimestrales disponibles")
        show_df(sheets, "Resultados trimestrales", height=560)
        st.caption("La fecha de publicación de resultados puede no estar disponible o ser una estimación de Yahoo Finance.")
        st.markdown("### Evolución trimestral · gráficas individuales")
        show_quarter_charts(quarterly_df, currency)
        st.caption("Estas tres gráficas utilizan exclusivamente los resultados de cada trimestre y el precio/deuda a su cierre. Para comparar múltiplos se anualiza el EPS o EBITDA trimestral multiplicándolo por 4, sin sumar cuatro trimestres ni usar TTM. Los periodos sin datos válidos aparecen como N/D. Las métricas TTM de otras tablas permanecen sin cambios.")

    with tab_data:
        st.markdown("### Información general y fuente del histórico")
        show_df(sheets, "General", height=280)
        if "Resumen Yahoo SEC" in sheets and not sheets["Resumen Yahoo SEC"].empty:
            st.markdown("### Auditoría de coincidencia Yahoo–SEC (umbral <1 %)")
            show_df(sheets, "Resumen Yahoo SEC", height=210)
            with st.expander("Ver todos los campos y diferencias anuales"):
                show_df(sheets, "Comparacion Yahoo SEC", height=520)
            st.caption("Solo se evalúan campos numéricos presentes en ambas fuentes. Los campos no comparables NO cuentan como coincidencias.")
        if "Fuentes SEC" in sheets and not sheets["Fuentes SEC"].empty:
            st.markdown("### Etiquetas y procedencia de SEC EDGAR")
            show_df(sheets, "Fuentes SEC", height=420)
        st.markdown("### Valoración actual según Yahoo Finance")
        show_df(sheets, "Valoracion actual", height=360)
        st.markdown("### Revisión de datos ausentes")
        missing = get_df(sheets, "Datos ausentes")
        if missing.empty:
            st.success("No se han registrado datos ausentes en las tablas evaluadas.")
        else:
            show_table(missing, height=360, currency=currency)
        st.caption("Excel guardado automáticamente en: " + str(result.get("saved_path", "Ruta no disponible")))
        st.download_button(
            "Descargar todas las tablas en Excel",
            data=result["excel_bytes"],
            file_name=result["excel_name"],
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
            use_container_width=True,
        )
        with st.expander("Registro técnico del cálculo"):
            log = (result.get("stdout", "") + "\n" + result.get("stderr", "")).strip()
            st.code(log[-14000:] if log else "Sin mensajes de registro.", language="text")
else:
    st.markdown("### Estructura del panel")
    st.write("Introduce un ticker y pulsa **Analizar empresa**. El panel intentará obtener hasta diez ejercicios anuales de SEC EDGAR; Yahoo Finance se utiliza para cotizaciones, datos trimestrales y comparables.")
    st.info("El primer análisis puede tardar varios minutos porque consulta estados financieros, precios históricos y hasta 10 comparables. Necesitas conexión a Internet.")
    st.markdown("**Secciones incluidas:** precio y métricas actuales; comparables con media y mediana; ratios históricos y CAGR; escenarios EPS × PER y FCF; resultados trimestrales; descarga del Excel completo.")

st.markdown("<div class='subtle'>Histórico anual: SEC EDGAR cuando el emisor está cubierto y la descarga funciona. Yahoo Finance aporta cotizaciones, resultados trimestrales y comparables. La cobertura de ambas fuentes varía por ticker; algunas métricas pueden aparecer como ‘No disponible’.</div>", unsafe_allow_html=True)
