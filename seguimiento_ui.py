"""Pestaña Mi seguimiento: la red sólo se consulta tras una acción explícita."""
from datetime import datetime,timezone
import json
import time
import pandas as pd
import streamlit as st
from seguimiento_store import Store,storage_path,TTL
from seguimiento_servicio import Service,search_companies
from seguimiento_metricas import discount_color

COLUMNS=['Empresa','Ticker','Precio','Moneda','Fecha precio','PER actual TTM','PER mediana 5 FY','Descuento PER (%)','PER comparables TTM',
         'QoQ neto reciente (%)','QoQ neto anterior (%)','QoQ neto tercero (%)','QoQ media 5a (%)','QoQ mediana 5a (%)','Cobertura QoQ',
         'EV/EBITDA último FY','EV/EBITDA mediana 5 FY','EV/EBITDA comparables NTM','Últimos resultados','Origen','Advertencias','Actualización (UTC)','Estado datos']


@st.cache_resource
def store_for(path):return Store(path)


def consume_open():
    ticker=st.session_state.pop('watch_open',None)
    if not ticker:return
    entry=store_for(str(storage_path())).entry(ticker)
    if not entry or not entry['payload']:return
    p=entry['payload']
    st.session_state['capture']=json.dumps(p,ensure_ascii=False,allow_nan=False)
    st.session_state['settings']=json.dumps(p.get('evidence',{}).get('stock_model',{}).get('settings',{}))
    st.session_state['selected_ticker']=ticker
    st.session_state['capture_note']='Análisis guardado de Mi seguimiento; revisar fechas y cobertura antes de decidir.'
    st.session_state['principal_tabs']='Resumen'
    st.session_state['watch_grid_epoch']=st.session_state.get('watch_grid_epoch',0)+1
    st.session_state.pop('capture_error',None);st.session_state.pop('upload_sha',None)


def table_rows(entries,now=None):
    now=time.time() if now is None else now;rows=[]
    for e in entries:
        row={'Empresa':e['name'],'Ticker':e['ticker'],**e['metrics'].get('row',{})}
        row['Actualización (UTC)']=datetime.fromtimestamp(e['updated'],timezone.utc).strftime('%Y-%m-%d %H:%M') if e['updated'] else None
        row['Estado datos']='Desactualizado: '+e['error'] if e['error'] else 'Pendiente de consultar' if not e['updated'] else 'Captura fechada; consultar fuentes' if not e['metrics'].get('financial_updated') else 'Caché vencida; actualizar' if now-e['updated']>TTL['quote'] else 'Guardado'
        rows.append(row)
    return pd.DataFrame(rows).reindex(columns=COLUMNS)


def render(load_capture,payload=None,settings=None):
    store=store_for(str(storage_path()));service=Service(store,load_capture)
    st.subheader('Tu lista de empresas')
    st.caption('Empresas y datos guardados en este equipo. Cambiar pestañas u ordenar no descarga datos. Precios fechados; FY, TTM y NTM se muestran por separado.')
    with st.form('watch_search_form'):
        col,button=st.columns([4,1])
        query=col.text_input('Buscar empresa o ticker',placeholder='Nombre completo, parcial o ticker')
        searched=button.form_submit_button('Buscar',width='stretch')
    if searched:
        try:
            with st.spinner('Buscando coincidencias de Yahoo…'):st.session_state['watch_matches']=search_companies(query,store)
            if not st.session_state['watch_matches']:st.info('Sin coincidencias de acciones. Prueba un nombre más completo o el ticker y su mercado.')
        except Exception as exc:st.warning('No se pudo buscar; la lista guardada se conserva. '+str(exc)[:250])
    matches=st.session_state.get('watch_matches',[])
    if matches:
        selected=st.selectbox('Confirma la empresa y bolsa',range(len(matches)),format_func=lambda i:f"{matches[i]['name']} · {matches[i]['ticker']} · {matches[i]['exchange']}")
        download=st.checkbox('Descargar datos al añadir',value=True)
        if st.button('Añadir empresa confirmada'):
            item=matches[selected]
            if store.add(item['ticker'],item['name'],item['exchange']):
                if download:
                    with st.spinner('Preparando análisis V7; la primera consulta puede tardar…'):service.refresh(item['ticker'])
                st.success('Empresa añadida')
            else:st.info('La empresa ya está en tu lista')
    if payload and st.button('Guardar empresa y ajustes del análisis abierto'):
        try:service.save_capture(payload,settings);st.success('Captura y supuestos guardados; conserva su fecha de mercado original')
        except Exception as exc:st.error(str(exc))
    entries=store.entries()
    if not entries:
        st.info('Tu lista está vacía. Busca y confirma una empresa o guarda el análisis abierto para empezar sin descargar datos.')
        st.caption('Persistencia: '+str(store.path));return
    labels={e['ticker']:e['name']+' · '+e['ticker'] for e in entries}
    with st.expander('Actualizar y gestionar empresas',expanded=True):
        managed=st.selectbox('Empresa de la lista',list(labels),format_func=labels.get)
        force=st.checkbox('Forzar todas las fuentes (más consultas)',value=False,help='Por defecto: cotización 15 min, estados SEC/Yahoo 24 h, histórico 7 días y comparables 72 h. Un nuevo filing puede exigir revisar la cobertura.')
        a,b,c,d=st.columns(4)
        one=a.button('Actualizar empresa',width='stretch');all_=b.button('Actualizar todas',width='stretch')
        if c.button('Abrir análisis V7',width='stretch'):
            if store.entry(managed)['payload']:st.session_state['watch_open']=managed;st.rerun()
            else:st.info('Actualiza primero la empresa para disponer de una captura')
        remove=d.button('Eliminar empresa',width='stretch')
        if remove:store.remove(managed);st.rerun()
        if one or all_:
            tickers=list(labels) if all_ else [managed]
            progress=st.progress(0,text='Actualizando…')
            for i,ticker in enumerate(tickers):
                progress.progress(i/len(tickers),text=f'Actualizando {ticker}…')
                service.refresh(ticker,force)
            progress.empty();st.rerun()
    frame=table_rows(entries)
    with st.expander('Personalizar columnas'):
        saved=store.preferences();default=[c for c in saved if c in frame] if saved is not None else frame.columns.tolist()
        columns=st.multiselect('Columnas visibles',frame.columns.tolist(),default=default)
        if columns!=saved:store.set_preferences(columns)
    if not columns:st.info('Selecciona al menos una columna');return
    view=frame[columns].copy()
    numeric=[c for c in columns if c not in ['Empresa','Ticker','Moneda','Fecha precio','Cobertura QoQ','Últimos resultados','Origen','Advertencias','Actualización (UTC)','Estado datos']]
    for column in numeric:view[column]=pd.to_numeric(view[column],errors='coerce')
    styled=view.style.format({c:('{:+.2f} %' if c=='Descuento PER (%)' else '{:.2f} %' if '(%)' in c else '{:,.2f}') for c in numeric},na_rep='—')
    if 'Descuento PER (%)' in view:styled=styled.map(discount_color,subset=['Descuento PER (%)'])
    event=st.dataframe(styled,hide_index=True,width='stretch',height=min(560,100+35*len(view)),
                       key='watch_table_'+str(st.session_state.get('watch_grid_epoch',0)),on_select='rerun',selection_mode='single-row')
    st.caption('Ordena pulsando cualquier cabecera y desplázate horizontalmente. Seleccionar una fila abre su análisis V7. Verde/+ = PER TTM inferior a la mediana FY; rojo/− = superior. No es una señal de compra ni comparación entre periodos idénticos.')
    if event.selection.rows:
        entry=entries[event.selection.rows[0]]
        if entry['payload']:st.session_state['watch_open']=entry['ticker'];st.rerun()
        else:st.info('Esta empresa aún no tiene una captura; usa Actualizar empresa')
    detail=st.selectbox('Detalle de fuentes y cobertura',list(labels),format_func=labels.get)
    entry=next(e for e in entries if e['ticker']==detail);m=entry['metrics']
    if entry['error']:st.warning('Se conserva la última captura válida. '+entry['error'])
    if m:
        with st.expander('Beneficio trimestral: fechas, QoQ y componentes SEC',expanded=False):
            st.caption('Hasta 20 variaciones; puede requerir un cierre previo adicional. Sin porcentaje con base cero/negativa ni entre cierres de cuatro meses. Neto reportado, sensible a estacionalidad/extraordinarios.')
            st.dataframe(pd.DataFrame(m.get('quarters',[])),hide_index=True,width='stretch')
        with st.expander('PER histórico y comparables auditados'):
            st.write('PER histórico depurado: '+str(m.get('per_history_n',0))+'/5 FY')
            st.dataframe(pd.DataFrame(m.get('historical_pe',[])),hide_index=True,width='stretch')
            for key,title in [('per_peers','PER TTM'),('per_ntm','PER NTM separado'),('ev_peers','EV/EBITDA NTM')]:
                stats=m.get(key,{})
                st.write(title,{'Media':stats.get('mean'),'Mediana':stats.get('median'),'N':stats.get('n'),'Advertencia':stats.get('warning')})
                if stats.get('rows'):st.dataframe(pd.DataFrame(stats['rows']),hide_index=True,width='stretch')
            st.caption(m.get('ev_fy',{}).get('warning',''))
    st.download_button('Exportar lista y capturas de seguimiento',json.dumps(entries,ensure_ascii=False,allow_nan=False,indent=2),file_name='mi_seguimiento.json',mime='application/json')
    st.caption('Ubicación local de la lista: '+str(store.path)+'. En servidores compartidos esta instalación comparte la misma lista; para datos personales usa una instancia propia.')
