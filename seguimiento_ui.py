"""Pestaña Mi seguimiento: la red sólo se consulta tras una acción explícita."""
from datetime import datetime,timezone
import json
import time
import pandas as pd
import streamlit as st
from seguimiento_store import Store,storage_path,TTL
from seguimiento_servicio import Service,search_companies
from seguimiento_metricas import discount_color
from seguimiento_incremental import local_stamp,quote_ttl
from predicciones_ui import render_predictions
from flujo_acciones import analysis_from_snapshot

COLUMNS=['Empresa','Ticker','Precio','Moneda','Fecha precio','PER actual TTM','PER mediana 5 FY','Descuento PER (%)','PER comparables TTM',
         'QoQ neto reciente (%)','QoQ neto anterior (%)','QoQ neto tercero (%)','QoQ media 5a (%)','QoQ mediana 5a (%)','Cobertura QoQ',
         'EV/EBITDA último FY','EV/EBITDA mediana 5 FY','EV/EBITDA comparables NTM','Últimos resultados','Origen','Advertencias','Actualización (UTC)','Estado datos']
OLD_COLUMNS=COLUMNS.copy()
COLUMNS=COLUMNS[:15]+['EV/EBITDA Yahoo','Periodo EV Yahoo']+COLUMNS[15:18]+['Calidad EV FY','PER TTM comparables B','PER forward comparables B','EV/EBITDA comparables B']+COLUMNS[18:]
COLUMNS += ['N PER comparables','Origen PER comparables','N PER forward comparables','PER TTM comparables validado']
COLUMNS=['Actualización local' if c=='Actualización (UTC)' else c for c in COLUMNS]
TEXT_COLUMNS=['Empresa','Ticker','Moneda','Fecha precio','Cobertura QoQ','Últimos resultados','Origen','Advertencias','Actualización local','Estado datos','Periodo EV Yahoo','Calidad EV FY','Origen PER comparables']


@st.cache_resource
def store_for(path):return Store(path)


def consume_open():
    ticker=st.session_state.pop('watch_open',None)
    if not ticker:return
    entry=store_for(str(storage_path())).entry(ticker)
    if not entry or not entry['payload']:return
    p=entry['payload']
    store_for(str(storage_path())).set_meta('selected_company',ticker)
    st.session_state['capture']=json.dumps(p,ensure_ascii=False,allow_nan=False)
    st.session_state['settings']=json.dumps(p.get('evidence',{}).get('stock_model',{}).get('settings',{}))
    st.session_state['selected_ticker']=ticker
    st.session_state['capture_note']='Análisis guardado de Mi seguimiento; revisar fechas y cobertura antes de decidir.'
    st.session_state['principal_tabs']=st.session_state.pop('watch_open_tab','Resumen')
    st.session_state['saved_company']=ticker
    st.session_state['watch_chart_ticker']=ticker
    st.session_state['watch_grid_epoch']=st.session_state.get('watch_grid_epoch',0)+1
    st.session_state.pop('capture_error',None);st.session_state.pop('upload_sha',None)


def table_rows(entries,now=None,zone='UTC'):
    now=time.time() if now is None else now;rows=[]
    for e in entries:
        row={'Empresa':e['name'],'Ticker':e['ticker'],**e['metrics'].get('row',{})}
        row['Actualización local']=local_stamp(e['updated'],zone)
        market_zone=((e.get('payload') or {}).get('kwargs',{}).get('info') or {}).get('exchangeTimezoneName')
        quote_at=e['metrics'].get('quote_queried_at') or e['updated'] or 0
        row['Estado datos']='Desactualizado/parcial: '+e['error'] if e['error'] else 'Pendiente de consultar' if not e['updated'] else 'Captura fechada; consultar fuentes' if not e['metrics'].get('financial_updated') else 'Caché vencida; actualizar' if now-quote_at>quote_ttl(now,market_zone) else 'Guardado'
        rows.append(row)
    return pd.DataFrame(rows).reindex(columns=COLUMNS)


def queue_open(ticker,tab=None):
    if ticker:
        st.session_state['watch_open']=ticker
        st.session_state['watch_open_tab']=tab or st.session_state.get('principal_tabs','Resumen')


def saved_selector():
    store=store_for(str(storage_path()));entries=store.entries();labels={e['ticker']:e['name']+' · '+e['ticker'] for e in entries if e['payload']}
    if labels:
        if st.session_state.get('saved_company') not in ['']+list(labels):st.session_state.pop('saved_company',None)
        if 'saved_company' not in st.session_state:st.session_state['saved_company']=store.meta('selected_company') if store.meta('selected_company') in labels else ''
        st.selectbox('Empresa guardada',['']+list(labels),format_func=lambda t:labels.get(t,'Selecciona para recuperar su análisis'),
                     key='saved_company',on_change=lambda:queue_open(st.session_state['saved_company']))


def present_frame(frame,numeric):
    """Celdas ausentes explícitas, manteniendo tipo numérico en el datagrid.

    Streamlit 1.67 ignora na_rep de Styler en celdas Arrow null. Se entregan
    strings parseables y NumberColumn; los ausentes son un guion real.
    """
    view=frame.copy()
    for column in numeric:
        values=pd.to_numeric(view[column],errors='coerce')
        view[column]=values.map(lambda n:'—' if pd.isna(n) else str(float(n)))
    for column in view.columns.difference(numeric):view[column]=view[column].map(lambda v:'—' if v is None or (not isinstance(v,(dict,list)) and pd.isna(v)) else json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else str(v))
    def formatter(column):
        pattern='{:+.2f} %' if column=='Descuento PER (%)' else '{:.2f} %' if '(%)' in column else '{:,.2f}'
        return lambda v:'—' if v=='—' else pattern.format(float(v))
    styled=view.style.format({c:formatter(c) for c in numeric})
    if 'Descuento PER (%)' in view:styled=styled.map(discount_color,subset=['Descuento PER (%)'])
    config={c:st.column_config.NumberColumn(c,help='— = dato no disponible; consultar fuentes y cobertura') for c in numeric}
    return styled,config


def show_detail(frame):
    numeric=[c for c in frame if pd.api.types.is_numeric_dtype(frame[c]) and not pd.api.types.is_bool_dtype(frame[c])]
    styled,config=present_frame(frame,numeric)
    st.dataframe(styled,hide_index=True,width='stretch',column_config=config)


def chart_for_entry(entry):
    m=entry['metrics'];p=entry['payload']
    if not p:st.info('Empresa sin captura financiera: actualiza para obtener los datos disponibles');return
    st.caption(f"{entry['name']} · {entry['ticker']} · {p['kwargs']['quote_currency']} · Precio fechado: {m.get('summary',{}).get('quote_date') or '—'} · Guardado: {local_stamp(entry['updated'],st.context.timezone or 'UTC')}")
    result,_=analysis_from_snapshot(p)
    def apply_watch_per(chosen):
        Service(store_for(str(storage_path()))).save_settings(entry['ticker'],chosen)
        queue_open(entry['ticker'],'Mi seguimiento')
        st.rerun()
    return render_predictions(p,result,'watch_'+entry['ticker'],apply_watch_per)



def render(load_capture,payload=None,settings=None):
    store=store_for(str(storage_path()));service=Service(store,load_capture)
    entries=[service.ensure_metrics(e) for e in store.entries()]
    zone=st.context.timezone or 'UTC'
    table_time=max([e['updated'] or e['created'] for e in entries]+[store.meta('last_table_update',0)]) if entries else store.meta('last_table_update',0)
    last_query=store.meta('last_quote_query',{})
    st.subheader('Tu lista de empresas')
    st.caption(f"Tabla: {local_stamp(table_time,zone)} · Última consulta de cotización: {local_stamp(last_query.get('at'),zone)} · Zona local: {zone}")
    stale=sum(table_rows(entries)['Estado datos'].ne('Guardado')) if entries else 0
    st.caption(f'{stale}/{len(entries)} empresas con datos pendientes, antiguos o parciales. Precios observados/últimos cierres fechados, no cotización garantizada en tiempo real.')
    if entries:
        frame=table_rows(entries,zone=zone)
        with st.expander('Personalizar columnas'):
            saved=store.preferences()
            if saved is not None:saved=['Actualización local' if c=='Actualización (UTC)' else c for c in saved]
            if saved is not None and not store.meta('columns_v4'):
                saved=saved+[c for c in COLUMNS if c not in OLD_COLUMNS and c not in saved];store.set_preferences(saved)
            store.set_meta('columns_v4',True)
            default=[c for c in saved if c in frame] if saved is not None else frame.columns.tolist()
            columns=st.multiselect('Columnas visibles',frame.columns.tolist(),default=default)
            if columns!=saved:store.set_preferences(columns)
        if not columns:
            st.info('Selecciona al menos una columna para mostrar la tabla')
            columns=['Empresa','Ticker']
        view=frame[columns].copy()
        numeric=[c for c in columns if c not in TEXT_COLUMNS]
        styled,config=present_frame(view,numeric)
        for name in ['PER comparables TTM','PER TTM comparables B','PER forward comparables B','EV/EBITDA comparables B','EV/EBITDA comparables NTM']:
            if name in view:config[name]=st.column_config.NumberColumn(name+' · mediana',help='Mediana de valores positivos disponibles. Consultar N, origen y periodo; TTM y forward no se mezclan.')
        if 'Actualización local' in view:config['Actualización local']=st.column_config.TextColumn('Actualización local',help='Timestamp UTC almacenado; presentado en '+zone)
        event=st.dataframe(styled,hide_index=True,width='stretch',column_config=config,height=min(560,100+35*len(view)),
                           key='watch_table_'+str(st.session_state.get('watch_grid_epoch',0)),on_select='rerun',selection_mode='single-row')
        st.caption('Comparables: medianas de ratios positivos, con N y origen visibles. La mediana Yahoo informativa puede completar el PER TTM mostrado, pero no se utiliza automáticamente en precios objetivo. El forward se mantiene separado.')
        st.caption('Ordena pulsando cualquier cabecera y desplázate horizontalmente. Seleccionar una fila actualiza el gráfico y las predicciones de abajo. Verde/+ = PER TTM inferior a la mediana FY; rojo/− = superior. No es una señal de compra ni comparación entre periodos idénticos.')
        if event.selection.rows:
            entry=entries[event.selection.rows[0]]
            if entry['payload']:queue_open(entry['ticker'],'Mi seguimiento');st.rerun()
            else:st.info('Esta empresa aún no tiene una captura; usa Actualizar empresa')
    if entries:
        labels={e['ticker']:e['name']+' · '+e['ticker'] for e in entries}
        if st.session_state.get('watch_chart_ticker') not in labels:st.session_state['watch_chart_ticker']=st.session_state.get('selected_ticker') if st.session_state.get('selected_ticker') in labels else next(iter(labels))
        selected_chart=st.selectbox('Empresa del gráfico',list(labels),format_func=labels.get,key='watch_chart_ticker',
            on_change=lambda:queue_open(st.session_state['watch_chart_ticker'],'Mi seguimiento'))
        chart_for_entry(next(e for e in entries if e['ticker']==selected_chart))
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
        if st.button('Añadir empresa confirmada'):
            item=matches[selected]
            if store.add(item['ticker'],item['name'],item['exchange']):
                with st.status('Análisis V7 completo: estados, históricos, comparables y escenarios…',expanded=True) as status:
                    updated=service.refresh(item['ticker'])
                    status.update(label='Análisis guardado'+(' con incidencias de cobertura' if updated['error'] else ''),state='complete')
                st.success('Empresa añadida')
                st.rerun()
            else:st.info('La empresa ya está en tu lista')
    if payload and st.button('Guardar empresa y ajustes del análisis abierto'):
        try:service.save_capture(payload,settings);st.success('Captura y supuestos guardados; conserva su fecha de mercado original')
        except Exception as exc:st.error(str(exc))
    entries=[service.ensure_metrics(e) for e in store.entries()]
    with st.expander('Importar / exportar copia de seguimiento'):
        st.caption('Importar recupera empresas, datos y supuestos sin red; reemplaza las capturas de los mismos tickers. Exporta antes si quieres conservar ambas versiones.')
        file=st.file_uploader('Importar lista y capturas JSON',type=['json'],key='watch_import')
        if file is not None and st.button('Importar sin descargar datos'):
            try:
                if file.size>128*1024*1024:raise ValueError('Copia demasiado grande (máximo 128 MB)')
                count=store.import_list(file.getvalue().decode('utf-8-sig'));st.success(f'{count} empresas recuperadas')
                current=st.session_state.get('selected_ticker')
                if current and store.entry(current) and store.entry(current)['payload']:queue_open(current,'Mi seguimiento')
                st.rerun()
            except (ValueError,KeyError,TypeError) as exc:st.error(str(exc))
        st.download_button('Exportar lista y capturas de seguimiento',json.dumps(store.export(),ensure_ascii=False,allow_nan=False,indent=2),file_name='mi_seguimiento.json',mime='application/json',on_click='ignore')
    if not entries:
        st.info('Tu lista está vacía. Busca y confirma una empresa o guarda el análisis abierto para empezar sin descargar datos.')
        st.caption('Persistencia: '+str(store.path));return
    labels={e['ticker']:e['name']+' · '+e['ticker'] for e in entries}
    with st.expander('Actualizar y gestionar empresas',expanded=False):
        managed=st.selectbox('Empresa de la lista',list(labels),format_func=labels.get)
        force=st.button('Forzar actualización completa',help='Reconsulta todas las fuentes de la empresa seleccionada; conserva tus supuestos manuales.')
        a,b,c,d=st.columns(4)
        one=a.button('Actualizar empresa',width='stretch');all_=b.button('Actualizar todas',width='stretch')
        if c.button('Abrir análisis V7',width='stretch'):
            if store.entry(managed)['payload']:queue_open(managed,'Resumen');st.rerun()
            else:st.info('Actualiza primero la empresa para disponer de una captura')
        remove=d.button('Eliminar empresa',width='stretch')
        if remove:store.remove(managed);st.rerun()
        if one or all_ or force:
            tickers=list(labels) if all_ else [managed]
            progress=st.progress(0,text='Actualizando…')
            for i,ticker in enumerate(tickers):
                progress.progress(i/len(tickers),text=f'Actualizando {ticker}…')
                service.refresh(ticker,force=force)
            progress.empty();st.rerun()
    detail=st.selectbox('Detalle de fuentes y cobertura',list(labels),format_func=labels.get)
    entry=next(e for e in entries if e['ticker']==detail);m=entry['metrics']
    if entry['error']:st.warning('Se conserva la última captura válida. '+entry['error'])
    if m:
        with st.expander('Actualización incremental: componentes consultados/reutilizados'):
            st.json(m.get('components',{}))
            backup=store.meta('last_valid:'+entry['ticker'])
            if backup:st.download_button('Descargar captura anterior sin incidencias',json.dumps(backup['payload'],ensure_ascii=False,allow_nan=False,indent=2),file_name=entry['ticker']+'_ultima_valida_inputs.json',on_click='ignore')
        with st.expander('Beneficio trimestral: fechas, QoQ y componentes SEC',expanded=False):
            st.caption('Hasta 20 variaciones; puede requerir un cierre previo adicional. Sin porcentaje con base cero/negativa ni entre cierres de cuatro meses. Neto reportado, sensible a estacionalidad/extraordinarios.')
            show_detail(pd.DataFrame(m.get('quarters',[])))
        with st.expander('PER histórico y comparables auditados'):
            st.write('PER histórico depurado: '+str(m.get('per_history_n',0))+'/5 FY')
            show_detail(pd.DataFrame(m.get('historical_pe',[])))
            for key,title in [('per_peers','PER TTM'),('per_ntm','PER NTM separado'),('ev_peers','EV/EBITDA NTM')]:
                stats=m.get(key,{})
                st.write(title,{'Mediana':stats.get('median'),'N':stats.get('n'),'Advertencia':stats.get('warning')})
                if stats.get('rows'):show_detail(pd.DataFrame(stats['rows']))
        with st.expander('EV/EBITDA: proveedor, cálculo FY y componentes históricos'):
            st.write('Proveedor Yahoo',m.get('provider_ev',{}))
            st.caption(m.get('ev_fy',{}).get('warning',''));show_detail(pd.DataFrame(m.get('ev_fy',{}).get('rows',[])))
        with st.expander('Nivel B — comparables informativos (no se usan en objetivos)'):
            b=m.get('informative_peers',{})
            st.caption(b.get('coverage',''))
            if b.get('warning'):st.info(b['warning'])
            st.write(b.get('stats',{}));show_detail(pd.DataFrame(b.get('rows',[])))
            st.caption('Candidatos, relaciones y motivos por los que no cumplen el nivel A')
            show_detail(pd.DataFrame(b.get('candidates',[])))
    st.caption('Ubicación local de la lista: '+str(store.path)+'. En servidores compartidos esta instalación comparte la misma lista; para datos personales usa una instancia propia.')


