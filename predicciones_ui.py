"""Controles PER reutilizados en Seguimiento y Resumen; sin fórmulas nuevas."""
import hashlib
import json
import math
import streamlit as st
from estado_dashboard import per_settings
from grafico_cotizacion import render as render_price_chart


def render_per_controls(result,key,on_apply):
    saved=result.settings
    manual=any('pe' in value for value in saved.get('scenarios',{}).values())
    selected=result.assumptions.query("Escenario=='Base' and Parámetro=='pe'")['Valor']
    observed=float(selected.iloc[0]) if len(selected) else float('nan')
    base=observed if math.isfinite(observed) and observed>0 else 20.
    scenarios=saved.get('scenarios',{})
    down=max(0.,min(.95,1-scenarios.get('Pesimista',{}).get('pe',base*.8)/base))
    up=max(0.,min(1.,scenarios.get('Optimista',{}).get('pe',base*1.2)/base-1))
    version=hashlib.sha256(json.dumps(saved,sort_keys=True,default=str).encode()).hexdigest()[:12]
    prefix='per_'+key+'_'+version
    with st.expander('Referencia PER · automático o manual',expanded=True):
        st.caption('Las dos vistas comparten empresa y supuestos. Automático usa la referencia admisible del modelo; Manual aplica tu hipótesis al EPS proyectado. La mediana informativa de comparables no sustituye sus controles.')
        st.caption('Referencia del modelo: '+str(result.summary.get('per_source') or 'No disponible'))
        current=result.metrics[result.metrics['Indicador'].eq('PER TTM')]
        current_pe=float(current.iloc[0]['Valor']) if len(current) else float('nan')
        if math.isfinite(current_pe) and math.isfinite(observed):
            st.caption(f'PER actual TTM: {current_pe:,.2f}× · PER Base supuesto: {observed:,.2f}×. Un objetivo puede depender de una expansión o contracción del múltiplo, además del crecimiento del beneficio.')
        if not math.isfinite(observed):st.info('Sin PER automático admisible. El 20 del formulario es sólo un valor inicial de edición; no es un PER calculado ni aplicado.')
        with st.form(prefix):
            mode=st.radio('Modo del PER',['Automático','Manual'],index=1 if manual else 0,horizontal=True,key=prefix+'_mode')
            a,b,c=st.columns(3)
            chosen=a.number_input('PER objetivo Base',min_value=.1,max_value=200.,value=float(max(.1,min(base,200.))),step=.5,key=prefix+'_base')
            lower=b.number_input('Distancia pesimista (%)',min_value=0.,max_value=95.,value=float(round(down*100,6)),key=prefix+'_lower')
            upper=c.number_input('Distancia optimista (%)',min_value=0.,max_value=100.,value=float(round(up*100,6)),key=prefix+'_upper')
            reason=st.text_input('Justificación del PER',value=saved.get('per_reason',''),key=prefix+'_reason')
            basis=st.selectbox('Base temporal del PER manual',['TTM','NTM'],index=1 if saved.get('per_basis')=='NTM' else 0,key=prefix+'_basis')
            exploratory=st.checkbox('Permitir valoración exploratoria con 2 PER históricos limpios',value=saved.get('exploratory_pe',False),key=prefix+'_exploratory')
            apply=st.form_submit_button('Aplicar referencia PER',type='primary')
        st.caption('El valor Base y las distancias se aplican en Manual. Con dos referencias históricas, la opción exploratoria tiene confianza Baja. El PER manual no resuelve ausencias de EPS ni bloqueos contables; se conservan los demás ajustes.')
        if result.summary.get('exploratory_pe'):st.warning('Valoración exploratoria: sólo dos referencias históricas; confianza Baja.')
        if apply:
            try:on_apply(per_settings(saved,mode,chosen,lower/100,upper/100,reason,basis,exploratory))
            except (ValueError,TypeError) as exc:st.error(str(exc))


def render_predictions(payload,result,key,on_apply):
    st.subheader('Cotización y escenarios')
    data=render_price_chart(payload,result.summary,result.valuation,key)
    render_per_controls(result,key,on_apply)
    if not result.summary.get('primary_available'):
        method=result.methods[result.methods['Método'].eq('EPS × PER')]
        reason=method.iloc[0]['Detalle'] if len(method) else result.summary.get('per_source','Cobertura insuficiente')
        st.info('Limitación de los objetivos: '+str(reason))
    return data
