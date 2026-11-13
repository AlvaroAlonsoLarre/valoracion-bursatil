"""Dashboard fundamental: seis pestañas, una proyección principal y fuentes auditables.

Ejecutar: streamlit run dashboard_app.py. Recalcular supuestos no consulta red.
"""
from __future__ import annotations
import hashlib
import html
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import altair as alt
import numpy as np
import pandas as pd
import streamlit as st
from analisis_acciones import SCENARIOS,DEFAULT_POLICY,evaluate_position,validate_settings
from auditoria_io import clean,provenance
from flujo_acciones import analysis_from_snapshot,excel_bytes,tables_summary
from estado_dashboard import prepare_capture,default_capture,per_settings,edited_settings,model_fingerprint
from grafico_cotizacion import render as render_price_chart

ROOT=Path(__file__).resolve().parent
st.set_page_config(page_title='Fundamental · Acciones',page_icon='◈',layout='wide')
st.markdown('''<style>
.stApp {background:#f5f7fa;color:#1b293d} .block-container {max-width:1480px;padding-top:4.7rem;padding-bottom:3rem}
[data-testid="stSidebar"] {background:#10283f} [data-testid="stSidebar"] * {color:#eef4f8}
[data-testid="stSidebar"] input {color:#10283f} [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] * {color:#1b293d!important} [data-testid="stSidebar"] [data-baseweb="select"] * {color:#1b293d!important} [data-testid="stSidebar"] button {color:#10283f} [data-testid="stSidebar"] button[kind="primaryFormSubmit"] {color:white}
h1 {letter-spacing:-.04em;font-size:2.35rem!important} h2,h3 {letter-spacing:-.02em}
[data-testid="stMetric"] {background:white;border:1px solid #e0e6ec;border-radius:10px;padding:1.15rem}
[data-testid="stMetricLabel"] {color:#64748b} [data-testid="stMetricValue"] {font-variant-numeric:tabular-nums;font-size:1.8rem}
[data-testid="stTabs"] button {font-size:.94rem;font-weight:600} [data-testid="stTabs"] {margin-top:1rem}
.overline {font-size:.7rem;letter-spacing:.16em;font-weight:700;color:#547184;margin-bottom:.4rem}
.diagnostic {background:white;padding:1rem;border:1px solid #e0e6ec;border-radius:10px;min-height:180px}
.diagnostic .label {font-size:.78rem;color:#64748b;margin-bottom:.5rem}
.diagnostic .value {font-size:1.12rem;font-weight:650;margin-bottom:.5rem}
.diagnostic .note {font-size:.8rem;color:#64748b;line-height:1.45}
.status {background:#e9f1f5;padding:.3rem .6rem;border-radius:5px;font-size:.78rem;color:#35566b;display:inline-block}
</style>''',unsafe_allow_html=True)


def fmt(value,percent=False):
    try:
        n=float(value)
        if not np.isfinite(n):return '—'
        return f'{n*100:,.1f} %' if percent else f'{n:,.2f}'
    except (ValueError,TypeError):return '—'


def table(tables,key):
    frame=tables.get(key,pd.DataFrame())
    if frame.empty:st.caption('Sin datos suficientes para esta tabla.')
    else:st.dataframe(frame,hide_index=True,width='stretch')


@st.cache_data(show_spinner=False)
def cached_calculate(payload_json,settings_json,model_signature):
    payload=json.loads(payload_json);settings=json.loads(settings_json)
    result,tables=analysis_from_snapshot(payload,settings)
    return result,tables


def calculate(payload_json,settings_json):
    return cached_calculate(payload_json,settings_json,model_fingerprint(ROOT))


def load_capture(ticker,quarters,contact):
    if not re.fullmatch(r'[A-Z0-9][A-Z0-9.\-^=]{0,24}',ticker):raise ValueError('Ticker no válido')
    if contact and not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+',contact):raise ValueError('Contacto SEC no válido')
    with tempfile.TemporaryDirectory(prefix='fundamental_ui_') as folder:
        env=os.environ.copy()
        if contact:env['SEC_CONTACT_EMAIL']=contact
        args=[sys.executable,str(ROOT/'ejecutar_analisis.py'),'--ticker',ticker,'--num-quarters',str(quarters),'--outdir',folder]
        proc=subprocess.run(args,env=env,capture_output=True,text=True,timeout=1500)
        snapshot=Path(folder)/(ticker+'_inputs.json')
        if proc.returncode not in (0,2) or not snapshot.exists():raise RuntimeError((proc.stderr or proc.stdout)[-1800:])
        return snapshot.read_text()


with st.sidebar:
    st.markdown('### ◈ Fundamental')
    st.caption('V7 integrada · motor financiero original')
    st.divider()
    with st.form('company'):
        ticker=st.text_input('Ticker',value=st.session_state.get('selected_ticker','MSFT'),help='EE. UU.: MSFT, JNJ, JPM. También admite 000660.KS y otras bolsas.').strip().upper()
        quarters=st.selectbox('Trimestres solicitados',[8,12,16,24],index=1)
        contact=st.text_input('Contacto SEC (opcional)',help='Identificación real de las consultas. No se exporta al informe.')
        fetch=st.form_submit_button('Consultar fuentes',type='primary',width='stretch')
    st.caption('SEC · histórico anual\n\nYahoo · cotizaciones y trimestres')
    st.divider()
    uploaded=st.file_uploader('Abrir captura JSON auditada',type=['json'])
    st.caption('Los cambios de supuestos usan la captura cargada; no vuelven a descargar las fuentes.')

if fetch:
    try:
        with st.spinner(f'Consultando fuentes de {ticker}…'):
            raw=load_capture(ticker,quarters,contact)
        raw,compatibility=prepare_capture(raw)
        chosen=st.session_state.get('settings','{}') if ticker==st.session_state.get('selected_ticker') else json.dumps(json.loads(raw)['evidence']['stock_model'].get('settings',{}))
        st.session_state['capture']=raw;st.session_state['settings']=chosen;st.session_state['selected_ticker']=ticker
        st.session_state.pop('position',None)
        st.session_state['capture_note']='Consulta con red completada. Revisar fechas de cotización y estados financieros.'
        st.session_state.pop('capture_error',None)
    except (ValueError,RuntimeError,subprocess.SubprocessError) as exc:st.session_state['capture_error']=str(exc)
if uploaded is not None:
    sha=hashlib.sha256(uploaded.getvalue()).hexdigest()
    if st.session_state.get('upload_sha')!=sha:
        try:
            raw,compatibility=prepare_capture(uploaded.getvalue().decode('utf-8'));p=json.loads(raw)
            st.session_state['capture']=raw;st.session_state['settings']=json.dumps(p['evidence']['stock_model'].get('settings',{}))
            st.session_state.pop('position',None)
            st.session_state['upload_sha']=sha;st.session_state['selected_ticker']=p['kwargs']['ticker'];st.session_state['capture_note']='Captura importada; consultar fuentes para actualizarla. '+'; '.join(compatibility)
            st.session_state.pop('capture_error',None)
        except (ValueError,UnicodeDecodeError) as exc:st.session_state['capture_error']=str(exc)
if 'capture' not in st.session_state:
    try:
        text_capture=default_capture(ROOT,os.environ.get('VALUACION_DASHBOARD_SNAPSHOT'))
        text_capture,notes=prepare_capture(text_capture)
        st.session_state['capture']=text_capture
        st.session_state['settings']=json.dumps(json.loads(text_capture)['evidence']['stock_model'].get('settings',{}))
        st.session_state['selected_ticker']=json.loads(text_capture)['kwargs']['ticker']
        st.session_state['capture_note']='Captura archivada de ejemplo; precio en la fecha indicada. '+'; '.join(notes)
    except (OSError,ValueError,KeyError) as exc:st.session_state['capture_error']=str(exc)
if st.session_state.get('capture_error'):st.error(st.session_state['capture_error'])

st.markdown('<div class="overline">ANÁLISIS FUNDAMENTAL / RENTA VARIABLE</div>',unsafe_allow_html=True)
if 'capture' not in st.session_state:
    st.title('Del negocio al precio por acción')
    st.write('Consulta un ticker para analizar sus resultados, comparar valoraciones y explorar escenarios a uno y tres años.')
    tabs=st.tabs(['Resumen','Histórico','Trimestrales','Comparables','Valoración','Datos y auditoría'])
    with tabs[0]:st.info('Elige una empresa en el panel lateral. También puedes importar una captura auditada para trabajar sin red.')
    st.stop()

raw=st.session_state['capture'];payload=json.loads(raw);capture_id=hashlib.sha256(raw.encode()).hexdigest()[:12]
try:
    result,tables=calculate(raw,st.session_state.get('settings','{}'))
    defaults,_=calculate(raw,'{}')
except (ValueError,KeyError,TypeError) as exc:
    st.error('La captura no permite completar el análisis: '+str(exc));st.stop()
s=result.summary;info=payload['kwargs'].get('info') or {};currency=s['currency']
st.title(str(info.get('longName') or s['ticker']))
st.caption(f"{s['ticker']}  ·  {currency}  ·  Corte {s['as_of']} / cotización {s.get('quote_date') or 'sin fecha'}  ·  Histórico {s['source']}")
st.caption(st.session_state.get('capture_note','Captura financiera auditada.'))
st.markdown(f'<span class="status">ESCENARIOS CONDICIONALES · CONFIANZA {html.escape(s["confidence"].upper())}</span>',unsafe_allow_html=True)

resumen,historico,trimestrales,comparables,valoracion,auditoria=st.tabs(['Resumen','Histórico','Trimestrales','Comparables','Valoración','Datos y auditoría'])
with resumen:
    cols=st.columns(4)
    cols[0].metric(f'Precio actual · {currency}',fmt(s['price']),help='Precio observado en la captura; revisar su fecha y consultar fuentes para actualizar.')
    cols[1].metric(f'Valor razonable hoy · {currency}',fmt(s['fair_value']),help='Precio Base a 1 año / (1 + retorno exigido). Es una referencia descontada, no una media de métodos.')
    cols[2].metric('Potencial a 1 año',fmt(s['upside_1y'],True),help='Precio Base a 1 año / precio de captura − 1. No incluye dividendos.')
    cols[3].metric('Anualizada a 3 años',fmt(s['annual_return_3y'],True),help='(Precio Base a 3 años / precio de captura)^(1/3) − 1. No incluye dividendos, costes o impuestos personales.')
    st.write('')
    left,right=st.columns([1.8,1])
    with left:
        st.subheader('Cotización y escenarios del motor')
        rows=result.valuation[result.valuation['Método'].eq('EPS × PER')]
        chart_rows=render_price_chart(payload,s,result.valuation,capture_id)
        tables['Grafico cotizacion']=chart_rows
        if not s['primary_available']:
            method=result.methods[result.methods['Método'].eq('EPS × PER')].iloc[0]
            st.warning('EPS × PER: '+method['Detalle'])
    with right:
        st.subheader('Lectura de valoración')
        st.markdown('**'+s['Atractivo']+'**')
        st.write(s['per_source'])
        base_h=result.assumptions.query("Escenario=='Base'").set_index('Parámetro')['Valor']
        st.caption('Base · crecimiento '+fmt(base_h.get('growth'),True)+' → '+fmt(base_h.get('growth_terminal'),True)+
                   ' · margen '+fmt(base_h.get('margin'),True)+' → '+fmt(base_h.get('margin_terminal'),True)+
                   ' · PER '+fmt(base_h.get('pe'))+'×. Extremos de años 1 y 3; editables en Valoración.')

        st.caption('La referencia propia reduce la confianza; las bandas son supuestos, no probabilidades.')
        st.write('Margen de seguridad exigido: **'+fmt(s['Margen de seguridad exigido (%)']/100,True)+'**')
        if len(rows):
            compact=rows.pivot(index='Escenario',columns='Horizonte (años)',values='Precio objetivo').reindex(SCENARIOS)
            st.dataframe(compact.rename(columns={1:'1 año',3:'3 años'}).style.format('{:,.2f}',na_rep='—'),width='stretch')
    with st.expander('Referencia PER · automático o manual',expanded=True):
        saved=result.settings
        manual=any('pe' in v for v in saved.get('scenarios',{}).values())
        base_pe=float(result.assumptions.query("Escenario=='Base' and Parámetro=='pe'")['Valor'].iloc[0])
        base_pe=base_pe if np.isfinite(base_pe) else 20.
        scenario_settings=saved.get('scenarios',{})
        down=max(0.,min(.95,1-scenario_settings.get('Pesimista',{}).get('pe',base_pe*.8)/base_pe))
        up=max(0.,min(1.,scenario_settings.get('Optimista',{}).get('pe',base_pe*1.2)/base_pe-1))
        with st.form('per_'+capture_id):
            mode=st.radio('Modo del PER',['Automático','Manual'],index=1 if manual else 0,horizontal=True)
            a,b,c=st.columns(3)
            chosen_pe=a.number_input('PER objetivo Base',min_value=.1,max_value=200.,value=float(base_pe),step=.5)
            lower=b.number_input('Distancia pesimista (%)',min_value=0.,max_value=95.,value=float(round(down*100,6)))
            upper=c.number_input('Distancia optimista (%)',min_value=0.,max_value=100.,value=float(round(up*100,6)))
            per_reason=st.text_input('Justificación del PER',value=saved.get('per_reason',''))
            per_basis=st.selectbox('Base temporal del PER manual',['TTM','NTM'],index=1 if saved.get('per_basis')=='NTM' else 0)
            exploratory=st.checkbox('Permitir valoración exploratoria con 2 PER históricos limpios',value=saved.get('exploratory_pe',False))
            pe_apply=st.form_submit_button('Aplicar referencia PER',type='primary')
        st.caption('Con dos referencias: exploratoria y confianza Baja, banda al menos ±20%. Con cero o una: PER manual justificado. El PER no corrige faltas de EPS ni otros bloqueos contables. Se preservan el resto de ajustes.')
        if s.get('exploratory_pe'):st.warning('Valoración exploratoria: sólo dos referencias históricas; confianza Baja.')
        if pe_apply:
            try:
                chosen=per_settings(saved,mode,chosen_pe,lower/100,upper/100,per_reason,per_basis,exploratory)
                calculate(raw,json.dumps(chosen,allow_nan=False))
                st.session_state['settings']=json.dumps(chosen,allow_nan=False);st.rerun()
            except (ValueError,TypeError) as exc:st.error(str(exc))
    st.subheader('El negocio en cuatro diagnósticos')
    for column,(_,diagnostic) in zip(st.columns(4),result.diagnostics.iterrows()):
        with column:
            st.markdown('<div class="diagnostic"><div class="label">'+html.escape(diagnostic['Diagnóstico'])+'</div><div class="value">'+html.escape(diagnostic['Lectura'])+'</div><div class="note">'+html.escape(diagnostic['Detalle'])+'</div></div>',unsafe_allow_html=True)
    with st.expander('Criterios de atractivo y posición (opcional)'):
        st.caption('Umbrales en %. Una mayor incertidumbre exige más margen de seguridad. Las reglas no envían órdenes ni garantizan resultados.')
        policy={**DEFAULT_POLICY,**result.settings.get('policy',{})}
        with st.form('position_rules_form'):
            cols=st.columns(6);new_policy={}
            for col,(key,label) in zip(cols,[('required_return','Retorno exigido'),('margin_of_safety','Margen mínimo'),('sell_premium','Prima para reducir'),('uncertainty_penalty','Penalización incertidumbre'),('max_position_weight','Peso máximo posición'),('max_downside','Caída tolerada')]):
                new_policy[key]=col.number_input(label,min_value=0.,max_value=80.,value=float(policy[key]*100),step=1.)/100
            pcols=st.columns(3)
            shares=pcols[0].number_input('Acciones en cartera · '+s['ticker'],min_value=0.,value=0.)
            cost=pcols[1].number_input(f'Coste por acción · {currency}',min_value=0.,value=0.)
            portfolio=pcols[2].number_input(f'Valor total cartera · {currency}',min_value=0.,value=0.,help='Debe estar en la misma moneda que la cotización. Sin valor de cartera no se propone ampliar.')
            update_policy=st.form_submit_button('Aplicar criterios y posición')
        if update_policy:
            chosen=json.loads(st.session_state.get('settings','{}'));chosen['policy']=new_policy
            st.session_state['settings']=json.dumps(chosen);st.session_state['position']={'shares':shares,'cost_price':cost,'portfolio_value':portfolio};st.rerun()
        position=st.session_state.get('position')
        if position is not None:
            decision=evaluate_position(s,policy,position)
            st.write('Decisión orientativa: **'+decision['Decisión']+'**')
            st.caption(decision['Motivo'])
            st.json(clean(decision),expanded=False)
        st.caption('Reglas: comprar sólo si el descuento supera el margen exigido, el retorno a 3 años supera el mínimo y el escenario pesimista limita la caída. Ampliar exige peso conocido inferior al máximo. Reducir por sobrevaloración o exceso de peso; vender exige una prima doble. El coste afecta a la plusvalía informativa, no al valor del negocio.')
    st.caption('Escenarios de precio sin dividendos ni probabilidades. No constituyen garantías ni sustituyen la revisión de riesgos y de la situación personal.')

with historico:
    st.subheader('Histórico SEC y referencias de valoración')
    st.caption('Importes de cuentas en unidades de '+s['financial_currency']+'. EPS por acción; PER y Precio/FCF en veces. Cobertura explícita por ventana de 5 y 10 ejercicios.')
    st.caption('Los estados anteriores a cotizar son historia financiera: no crean precios ni PER. Los registros de separación requieren revisar su perímetro económico antes de normalizar.')
    table(tables,'Estadisticas 5 y 10')
    st.subheader('Cuentas anuales seleccionadas')
    table(tables,'Financieros anuales')
    with st.expander('Referencia de precio y base de acción de cada ejercicio'):
        table(tables,'Referencias historicas')
        st.caption('Precios Close ajustados por splits, sin ajuste por dividendos. EPS y acciones se concilian con el beneficio común y los eventos posteriores al filing. Es retrospectivo; no es un backtest con información disponible en cada fecha histórica.')

with trimestrales:
    st.subheader('La base actual del negocio')
    with st.expander('Conciliación SEC–Yahoo y fechas reales'):
        table(tables,'Conciliacion SEC Yahoo')
    table(tables,'Disponibilidad metricas')
    table(tables,'Base TTM y balance')
    st.caption('TTM exige cuatro trimestres consecutivos; no se multiplica un trimestre por cuatro. El balance utiliza el cierre más reciente.')
    q=tables.get('Resultados trimestrales',pd.DataFrame())
    if not q.empty and 'Ingresos' in q:
        date=q.columns[0];plot=q[[date,'Ingresos','Beneficio neto']].copy();plot[date]=pd.to_datetime(plot[date],errors='coerce')
        plot=plot.melt(id_vars=[date],var_name='Métrica',value_name='Importe').dropna()
        plot['Importe']/=1e9
        st.altair_chart(alt.Chart(plot).mark_bar().encode(x=alt.X(date+':T',title='Cierre'),y=alt.Y('Importe:Q',title='Miles de millones de '+s['financial_currency']),color='Métrica:N',xOffset='Métrica:N',tooltip=[date,'Métrica','Importe']).properties(height=280),width='stretch')
    table(tables,'Resultados trimestrales')

with comparables:
    st.subheader('Actividad similar, múltiplos separados')
    st.caption('Preferencia de 3 a 6 empresas. No se fuerza completar el grupo. Los candidatos descartados y sus motivos se conservan en la auditoría.')
    selected=result.peers
    if selected.empty:st.info('No hay pares con actividad suficientemente comparable. Se examina el histórico propio como referencia de menor confianza.')
    else:
        preferred=['Ticker','Empresa','Confianza en comparabilidad','Justificación económica','PER TTM verificado','PER NTM verificado','Estado PER TTM','Estado PER NTM','Puntuación económica (0-100)']
        st.dataframe(selected[[c for c in preferred if c in selected]],hide_index=True,width='stretch')
    st.caption('TTM reportado y NTM forward se verifican por separado: periodo, moneda, base contable, acción ordinaria/ADR y beneficios. Un forwardPE o un forecast normalized de proveedor no acredita GAAP NTM.')
    with st.expander('Fuentes y cobertura de múltiplos'):
        table(tables,'Fuentes comparables TTM');table(tables,'Fuentes comparables')
    with st.expander('Todos los candidatos y motivos de selección'):
        table(tables,'Universo comparables')

with valoracion:
    st.subheader('EPS proyectado × PER razonable')
    st.caption('Ingresos TTM → crecimiento previsto → EBIT normalizado + resultado no operativo → impuestos → beneficio común / acciones diluidas. Para financieras se usa margen PBT, con resultado financiero ya incluido. Un REIT requiere FFO/AFFO/NAV.')
    if s['profit_model']=='PBT directo':st.info('Esta captura utiliza margen PBT normalizado: el resultado financiero ya está incluido. No se inventa una serie EBIT ni se suma el financiero dos veces.')
    table(tables,'Valoracion EPS PER')
    with st.expander('Sensibilidad y comparación con la cotización'):
        st.caption('Cada variable cambia por separado. Sensibilidad: ±5 puntos de crecimiento, ±3 de margen y ±20% PER. Los supuestos no se ajustan automáticamente al precio.')
        data=tables.get('Sensibilidad EPS PER',pd.DataFrame()).copy()
        if not data.empty:
            data['Parámetro']=data['Parámetro'].map({'growth':'Crecimiento','margin':'Margen','pe':'PER'})
            data['Cambio']=[f'{v*100:+.0f} %' if parameter=='PER' else f'{v*100:+.0f} pp' for v,parameter in zip(data['Cambio'],data['Parámetro'])]
            st.dataframe(data[['Horizonte (años)','Parámetro','Cambio','Precio sensibilidad','Moneda']],hide_index=True,width='stretch')
        implied=tables.get('Expectativas implicitas',pd.DataFrame()).copy()
        for col in ['Crecimiento uniforme implícito','Margen implícito']:
            if col in implied:implied[col+' (%)']=implied.pop(col)*100
        st.markdown('**Contraste de retorno de precio cero**')
        display=['Horizonte (años)','Precio observado','Precio objetivo Base','Crecimiento uniforme implícito (%)','Margen implícito (%)','PER implícito','Año EPS']
        st.dataframe(implied[[c for c in display if c in implied]].rename(columns={
            'Precio observado':'Cotización','Precio objetivo Base':'Objetivo Base','Crecimiento uniforme implícito (%)':'Crecim. uniforme (%)'}),hide_index=True,width='stretch')
        st.caption('Este contraste iguala el precio futuro a la cotización observada: retorno de precio cero. Resuelve una incógnita manteniendo el resto Base; no estima las expectativas del mercado ni es un pronóstico. El crecimiento implícito es uniforme hasta el año del EPS, distinto de una senda desacelerada. Sin dividendos ni descuento.')
    with st.expander('Resultados recurrentes y calidad del PER histórico'):
        table(tables,'Puente recurrencia');table(tables,'Recurrencia trimestral');table(tables,'Referencias historicas');table(tables,'Notas inversiones oficiales')
        st.caption('Importes pretax en moneda financiera. Los beneficios reportados se conservan: no se inventa un impuesto ni un EPS ajustado. Un PER puede excluirse de la referencia sin ocultar el dato histórico.')
    st.subheader('Supuestos editables')
    initial=result.assumptions.pivot(index='Escenario',columns='Parámetro',values='Valor').reindex(SCENARIOS)
    labels={'growth':'Crecimiento ventas (%)','margin':'Margen EBIT / PBT (%)','tax':'Fiscalidad (%)','financial_sales':'No operativo / ventas (%)','dilution':'Variación acciones (%)','pe':'PER (x)','growth_terminal':'Crecimiento año 3 (%)','margin_terminal':'Margen año 3 (%)'}
    editor=initial.copy()
    for key in editor:
        if key!='pe':editor[key]*=100
    editor=editor.rename(columns=labels).reset_index()
    with st.form('assumptions'):
        edited=st.data_editor(editor,hide_index=True,disabled=['Escenario',labels['pe']]+([labels['financial_sales']] if defaults.summary['profit_model']=='PBT directo' else []),width='stretch',key='hypotheses_'+capture_id)
        st.caption('El PER se configura en Resumen. Este formulario conserva esa referencia y modifica sólo los ajustes editados.')
        turnaround=st.checkbox('Caso explícito de recuperación desde EPS negativo',value=bool(result.settings.get('allow_turnaround')))
        turn_reason=st.text_input('Justificación de recuperación',value=result.settings.get('turnaround_reason',''))
        with st.expander('Acción / ADR y análisis opcionales'):
            adr=st.number_input('Acciones ordinarias por ADR (0 si no se aporta puente)',min_value=0.,value=float(result.settings.get('adr',{}).get('ordinary_per_quote_share',0.)))
            adr_source=st.text_input('Fuente HTTPS del ratio ADR',value=result.settings.get('adr',{}).get('source',''))
            adr_date=st.text_input('Fecha del ratio ADR (AAAA-MM-DD)',value=result.settings.get('adr',{}).get('date',''))
            advanced=st.checkbox('Calcular EV/EBITDA y DCF opcionales',value=bool(result.settings.get('advanced')))
            wacc=st.text_input('WACC opcional (%)',value=str(result.settings.get('optional_assumptions',{}).get('wacc','')*100) if 'wacc' in result.settings.get('optional_assumptions',{}) else '',placeholder='Automático; requiere revisión de riesgo y moneda')
            terminal=st.text_input('Crecimiento terminal opcional (%)',value=str(result.settings.get('optional_assumptions',{}).get('terminal_growth','')*100) if 'terminal_growth' in result.settings.get('optional_assumptions',{}) else '',placeholder='Automático; debe ser compatible con WACC')
            st.caption('Los fallos de estos métodos no invalidan una proyección EPS/PER suficiente. Las financieras y REIT necesitan métodos sectoriales.')
        apply=st.form_submit_button('Recalcular escenarios',type='primary')
    if apply:
        try:
            custom=edited_settings(result.settings,edited,initial,labels,s['profit_model']=='PBT directo')
            custom.update(advanced=advanced,allow_turnaround=turnaround,turnaround_reason=turn_reason)
            if adr>0:custom['adr']={'ordinary_per_quote_share':adr,'source':adr_source,'date':adr_date}
            else:custom.pop('adr',None)
            optional={}
            for key,value in [('wacc',wacc),('terminal_growth',terminal)]:
                if value.strip():optional[key]=float(value.replace(',','.'))/100
            custom['optional_assumptions']=optional
            validate_settings(custom);calculate(raw,json.dumps(custom,allow_nan=False))
            st.session_state['settings']=json.dumps(custom,allow_nan=False);st.rerun()
        except (ValueError,TypeError) as exc:st.error(str(exc))
    st.caption('El crecimiento y margen evolucionan linealmente del año 1 al año 3; después conservan el nivel del año 3. En ciclos o crecimientos excepcionales se usan CAGR compuestos a 5/10 FY y márgenes normalizados desde el primer año, sin calibración al precio.')
    st.caption('Los valores automáticos son hipótesis mecánicas y se identifican como tales. Cambiar la cotización no recalibra crecimiento, márgenes ni PER. Para NTM manual introduce los tres PER explícitos.')
    with st.expander('Trayectoria de beneficios y origen de cada supuesto'):
        table(tables,'Proyeccion EPS');table(tables,'Supuestos EPS PER')
    st.subheader('Suficiencia por método')
    table(tables,'Estado metodos')
    table(tables,'Disponibilidad metricas')
    if result.settings.get('advanced'):
        with st.expander('EV/EBITDA y DCF · resultados y controles propios',expanded=True):
            table(tables,'Valoracion opcional');table(tables,'Control opcionales');table(tables,'Parametros riesgo')

with auditoria:
    st.subheader('Datos y auditoría')
    st.caption('Aplicación integrada · código '+provenance()['sha']+' · captura '+capture_id+' · modo PER '+s.get('per_mode','Automático'))
    tables['Identidad aplicacion']=pd.DataFrame([{'Aplicación':'dashboard_app.py · V7 integrada','Firma motor':model_fingerprint(ROOT),'Commit':provenance()['sha']}])
    table(tables,'Identidad aplicacion')
    st.caption('CRÍTICO bloquea sólo el ámbito indicado. ADVERTENCIA informa de límites y reduce confianza; no se rellena un dato ausente para obtener un precio.')
    table(tables,'Control por metodo')
    for title,keys in [
        ('Fuentes y conciliación contable',['Fuentes SEC','Fuentes fundamentales','Conciliacion TTM','Componentes CAPEX DA','Resumen Yahoo SEC']),
        ('Actualidad y publicaciones oficiales',['Actualidad resultados','Contraste IR','Extraordinarios IR','Revision filings','Pendientes fundamentales'])]:
        with st.expander(title):
            for key in keys:st.write('**'+key+'**');table(tables,key)
    export_payload=json.loads(raw);export_payload['evidence']['stock_model']['settings']=result.settings
    summary=tables_summary(s['ticker'],tables,provenance());summary['source_capture_sha256']=hashlib.sha256(raw.encode()).hexdigest()
    capture_export=json.dumps(clean(export_payload),ensure_ascii=False,allow_nan=False,indent=2)
    summary['input_sha256']=hashlib.sha256(capture_export.encode()).hexdigest()
    if 'position' in st.session_state:summary['position_analysis']=clean(evaluate_position(s,{**DEFAULT_POLICY,**result.settings.get('policy',{})},st.session_state['position']))
    st.subheader('Exportar el análisis visible')
    a,b,c=st.columns(3)
    a.download_button('Descargar Excel',excel_bytes(tables),file_name=f"{s['ticker']}_fundamental.xlsx",mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',width='stretch')
    b.download_button('Descargar resultados JSON',json.dumps(summary,ensure_ascii=False,allow_nan=False,indent=2),file_name=f"{s['ticker']}_resultados.json",mime='application/json',width='stretch')
    c.download_button('Descargar captura reproducible',capture_export,file_name=f"{s['ticker']}_inputs.json",mime='application/json',width='stretch')
    st.caption('Excel y JSON contienen los supuestos visibles y los mismos resultados. La captura incluye las fuentes y entradas para reproducir el cálculo sin red. Los datos de posición sólo se exportan si se han introducido.')
