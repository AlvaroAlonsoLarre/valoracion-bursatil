"""Presentación española y vistas compactas. Nunca cambia datos ni exportaciones."""
import math
import re
import unicodedata
import numpy as np
import pandas as pd
import streamlit as st

SYMBOLS={'USD':'$','EUR':'€','GBP':'£','GBp':'GBp','GBX':'GBp','KRW':'₩','JPY':'¥','CNY':'CN¥','HKD':'HK$','CAD':'C$','AUD':'A$','TWD':'NT$'}

def numero(value,decimals=2,percent=False,signed=False):
    try:n=float(value)
    except (ValueError,TypeError):return '—'
    if not math.isfinite(n):return '—'
    if percent:n*=100
    s=format(n,('+' if signed else '')+f',.{decimals}f')
    return s.replace(',','@').replace('.',',').replace('@','.')+(' %' if percent else '')

def escala(values):
    v=pd.to_numeric(pd.Series(values),errors='coerce').abs().dropna()
    maximum=v.max() if len(v) else 0
    return (1e9,'MM') if maximum>=1e9 else (1e6,'M') if maximum>=1e6 else (1e3,'K') if maximum>=1e3 else (1.,'')

def normal(text):return ''.join(c for c in unicodedata.normalize('NFKD',str(text).lower()) if not unicodedata.combining(c)).strip()

def es_importe(name):
    n=normal(name)
    if '/' in n:return False
    if any(x in n for x in ['origen','fuente','fecha','periodo','ratio','cobertura','per ','per historico','ev/','/ ebitda','/ ventas','margen','tasa','roic','cagr','retorno','rentab','crecimiento','variacion','dilucion','factor','observacion','ejercicio','horizonte','cik','sha','porcentaje','(%','prioridad','confianza','puntuacion']):return False
    return any(x in n for x in ['ingreso','beneficio','ebit','efectivo','inversion','deuda','pasivo','activo','patrimonio','flujo','fcf','capex','impuesto','gasto','recompra','dividendo','nopat','capital','acciones','d&a','depreciacion','amortizacion','precio','valor yahoo','valor sec','valor razonable','coste']) and not n.startswith('eps')

def cabecera_unidad(name,factor,suffix,currency=None,shares=False):
    symbol='' if shares else SYMBOLS.get(currency,currency or '')
    unit=' '.join(x for x in [suffix,symbol] if x)
    return str(name)+(f' ({unit})' if unit else '')

def info(text):
    """Botón de ayuda alineado al margen izquierdo del bloque actual."""
    if text:
        with st.popover('ⓘ',help='Información del apartado',type='tertiary'):
            st.markdown(str(text))

def vista(frame,currency=None):
    """Escala columnas de importes; ratios, fechas, cantidades por acción e IDs conservan su unidad."""
    d=frame.copy();formats={};labels={}
    for col in ['Moneda financiera','Moneda cotización','Divisa financiera','Divisa cotización']:
        if col in d and d[col].dropna().nunique()>1:currency=None
    for c in d:
        n=normal(c)
        if 'fecha' in n or n in ['cierre','cierre del trimestre','inicio']:
            dates=pd.to_datetime(d[c],errors='coerce',utc=True)
            if dates.notna().any():d[c]=dates.dt.strftime('%Y/%m/%d').where(dates.notna(),d[c])
        values=pd.to_numeric(d[c],errors='coerce')
        if pd.api.types.is_bool_dtype(d[c]) or n in ['ejercicio','horizonte (anos)','cik sec','prioridad']:continue
        if not values.notna().any() or (not pd.api.types.is_numeric_dtype(d[c]) and values.notna().sum()!=d[c].notna().sum()):continue
        factor,suffix=escala(values) if es_importe(c) and not any(x in n for x in ['miles de millones','(mm','(m ','(k ']) else (1.,'')
        d[c]=values/factor
        if 'miles de millones' in n:
            labels[c]=re.sub(r'\(miles de millones\)',f'(MM {SYMBOLS.get(currency,currency or "")})',str(c)).replace('MM )','MM)')
        elif factor!=1 or (currency and es_importe(c)):
            labels[c]=cabecera_unidad(c,factor,suffix,currency,'acciones' in n)
        fraction=n in ['roic','tasa fiscal','margen bruto','margen operativo','margen neto','margen fcf']
        if fraction:d[c]*=100;labels[c]=str(c)+' (%)'
        formats[labels.get(c,c)]=lambda v:numero(v)
    d=d.rename(columns=labels)
    return d.style.format(formats,na_rep='—'),labels

def mostrar(frame,currency=None,**kwargs):
    if frame.empty:info('Sin datos suficientes para esta tabla.');return
    # Las tablas verticales mezclan importes y ratios: las unidades van por fila.
    if 'Campo' in frame and {'Valor Yahoo','Valor SEC'}<=set(frame):
        d=frame.copy();units=[]
        for i,r in d.iterrows():
            factor,suffix=escala([r['Valor Yahoo'],r['Valor SEC']]) if es_importe(r['Campo']) else (1.,'')
            unit=' '.join(x for x in [suffix,SYMBOLS.get(currency,currency or '') if es_importe(r['Campo']) and 'acciones' not in normal(r['Campo']) else ''] if x)
            if str(r['Campo']).startswith('EPS'):unit=SYMBOLS.get(currency,currency or '')+'/acción'
            units.append(unit)
            for c in ['Valor Yahoo','Valor SEC']:d.loc[i,c]=pd.to_numeric(pd.Series([r[c]]),errors='coerce').iloc[0]/factor
        d['Unidad']=units
        for c in ['Fecha Yahoo','Fecha SEC']:
            if c in d:d[c]=pd.to_datetime(d[c],errors='coerce').dt.strftime('%Y/%m/%d')
        st.dataframe(d.style.format({'Valor Yahoo':numero,'Valor SEC':numero},na_rep='—'),hide_index=True,width='stretch',**kwargs);return
    if ('Indicador' in frame and 'Valor' in frame) or ('Campo' in frame and 'Base TTM (unidades)' in frame):
        key='Indicador' if 'Indicador' in frame else 'Campo';value='Valor' if 'Valor' in frame else 'Base TTM (unidades)'
        d=frame.copy();units=[];shown=[]
        for _,r in d.iterrows():
            amount=es_importe(r[key]) and not str(r[key]).startswith('EPS')
            factor,suffix=escala([r[value]]) if amount else (1.,'')
            units.append(' '.join(x for x in [suffix,SYMBOLS.get(currency,currency or '') if amount and 'acciones' not in normal(r[key]) else '×' if '/' in str(r[key]) or 'PER' in str(r[key]) else ''] if x))
            try:v=float(r[value])/factor
            except (ValueError,TypeError):v=np.nan
            shown.append(numero(v,percent=normal(r[key])=='roic'))
            if normal(r[key])=='roic':units[-1]='%'
            if str(r[key]).startswith('EPS'):units[-1]=SYMBOLS.get(currency,currency or '')+'/acción'
        d[value]=shown;d['Unidad']=units;d=d.rename(columns={value:'Valor'})
        st.dataframe(d,hide_index=True,width='stretch',**kwargs);return
    styled,_=vista(frame,currency)
    st.dataframe(styled,hide_index=True,width='stretch',**kwargs)

def columnas(frame,key,removed=(),hidden=()):
    d=frame.drop(columns=list(removed),errors='ignore').copy()
    default=[c for c in d if c not in hidden]
    with st.popover('Personalizar columnas'):
        selected=st.multiselect('Columnas visibles',list(d),default=default,key='columns_'+key)
    return d[selected]

def historico_compacto(frame):
    if frame.empty:return frame.copy()
    rows=[]
    for indicator,g in frame.groupby('Indicador',sort=False):
        row={'Indicador':indicator}
        for stat in ['Media','Mediana','CAGR (%)','Cobertura completa','Ejercicios disponibles']:
            for years in [5,10]:
                part=g[g['Ventana (ejercicios)'].eq(years)]
                row[f'{stat} {years} años']=part.iloc[0].get(stat) if len(part) else None
        for years in [5,10]:
            part=g[g['Ventana (ejercicios)'].eq(years)]
            row[f'Dispon. Datos {years} años']=f'{int(part.iloc[0]["Observaciones"]) if len(part) else 0}/{years}'
        rows.append(row)
    return pd.DataFrame(rows)

def mostrar_historico(frame,currency):
    d=historico_compacto(frame)
    d=columnas(d,'historico',hidden=[c for c in d if c.startswith(('Cobertura completa','Ejercicios disponibles'))])
    if d.empty:return
    # Una escala por indicador, compartida entre ventanas, para comparar 5/10 años.
    units=[]
    for i,r in d.iterrows():
        cols=[c for c in d if c.startswith(('Media ','Mediana '))]
        amount=es_importe(r['Indicador'])
        factor,suffix=escala([r[c] for c in cols]) if amount else (1.,'')
        for c in cols:d.loc[i,c]=pd.to_numeric(pd.Series([r[c]]),errors='coerce').iloc[0]/factor
        units.append(' '.join(x for x in [suffix,SYMBOLS.get(currency,currency) if amount else '×' if 'PER' in str(r['Indicador']) or '/' in str(r['Indicador']) else ''] if x))
    d.insert(1,'Unidad',units)
    formats={c:numero for c in d if c.startswith(('Media ','Mediana ','CAGR '))}
    st.dataframe(d.style.format(formats,na_rep='—'),hide_index=True,width='stretch')

ANNUAL_REMOVE=['Ejercicio','Beneficio neto común','Beneficio neto continuado','EPS continuado diluido','EPS continuado fuente presentado','EPS fuente presentado','Acciones fuente presentado','Efectivo e inversiones combinado directo','Concepto gasto intereses','Ganancia FV inversiones','Revalorizacion inversiones privadas','Deterioro inversiones privadas','Ganancias deuda realizadas','Perdidas deuda realizadas','Intereses inversiones','Origen D&A','Origen deuda','Deuda incluye arrendamientos','Origen efectivo/inversiones','Cobertura de intereses','Capital invertido aproximado','Origen financiero anual','CIK SEC']
ANNUAL_HIDDEN=['Efectivo','Inversiones a corto plazo','Deuda a largo plazo','Activos totales','Patrimonio neto','D&A','Impuestos','Beneficio antes de impuestos','Gastos por intereses','D&A y otros','Deuda a corto plazo','Pasivos por arrendamientos','Deuda total','Deuda total incl. arrendamientos','Tasa fiscal','Margen bruto','Margen operativo','NOPAT aproximado']
QUARTER_REMOVE=['Origen efectivo/inversiones','Efectivo e inversiones','Deuda incluye arrendamientos','Origen deuda','CAPEX PP&E','D&A cash flow','Definición D&A','Arrendamientos','Cobertura de intereses','Publicación de resultados estimada/registrada']
QUARTER_HIDDEN=['Beneficio bruto','Beneficio operativo','Efectivo','Inversiones a corto plazo','Deuda a corto plazo','Deuda a largo plazo','Deuda total','Activos totales','Patrimonio neto','D&A','Impuestos','Beneficio antes de impuestos','Tasa fiscal','Gastos por intereses','Margen bruto','Margen operativo','NOPAT aproximado','Capital invertido aproximado']
PEER_REMOVE=['Relación B','Justificación económica','Limitación económica','Fecha cotización','Nivel','Periodo PER','Periodo EV','Cierre reportado Yahoo','Origen','Estado A','Prioridad']


def resumen_metricas(payload,result):
    from auditoria_io import restore_frame
    from modelo_fundamental import quarterly_snapshot
    from seguimiento_metricas import quarter_series
    from seguimiento_ev import yahoo_ratio
    from historico_acciones import number
    k=payload['kwargs'];q=restore_frame(payload['frames']['quarterly']) if payload['frames'].get('quarterly') else pd.DataFrame()
    a=restore_frame(payload['frames']['annual']);s=result.summary
    ttm,_,aligned,_=quarterly_snapshot(q,a,s['as_of'],k.get('fiscal_end_date'))
    metrics=result.metrics.set_index('Indicador')['Valor'].to_dict()
    quarters=quarter_series(q,s['as_of']);latest=quarters.iloc[-1] if len(quarters) else {}
    provider=payload.get('evidence',{}).get('watch_provider',{}).get('info') or k.get('info') or {}
    ev=yahoo_ratio(provider,s['as_of'])
    debt=number(ttm.get('Deuda neta reciente'));ebitda=number(ttm.get('EBITDA aproximado'))
    labels=[('PER actual TTM',metrics.get('PER TTM'),False,False),('BPA diluido TTM',metrics.get('EPS diluido'),True,False),
            ('Beneficio neto último Q',latest.get('Beneficio neto'),True,True),('Crecimiento beneficio neto último Q (%)',latest.get('QoQ (%)'),False,False),
            ('Acciones diluidas medias',metrics.get('Acciones diluidas'),False,True),('Deuda neta · último cierre',debt,True,True),
            ('FCF TTM',metrics.get('FCF'),True,True),('CAPEX TTM',metrics.get('CAPEX'),True,True),
            ('EV/EBITDA Yahoo · TTM/LTM',ev['value'],False,False),('Deuda neta/EBITDA TTM · aprox.',debt/ebitda if ebitda>0 else None,False,False)]
    for label,value,money,large in labels:
        factor,suffix=escala([value]) if large else (1.,'')
        currency=s['financial_currency'] if money else None
        heading=cabecera_unidad(label,factor,suffix,currency,shares=not money)
        yield {'label':heading,'value':number(value)/factor,'help':('Beneficio neto reportado; variación frente al trimestre anterior, sin anualizar.' if 'último Q' in label else
            'Acciones medias diluidas del último trimestre o FY indicado; no son las acciones exactas al cierre.' if 'Acciones' in label else
            ev['period']+'; dato Yahoo informativo, no reconciliado, no FY ni NTM.' if 'Yahoo' in label else
            'Deuda neta al último balance / EBITDA aproximado de cuatro trimestres; definición D&A no necesariamente conciliada. No se usa en objetivos.' if 'Deuda neta/EBITDA' in label else
            'Último balance disponible; efectivo e inversiones según la definición del motor.' if 'Deuda neta' in label else 'TTM = cuatro trimestres consecutivos, no último trimestre multiplicado por cuatro.')}


def pintar_resumen(payload,result):
    items=list(resumen_metricas(payload,result))
    for start in range(0,len(items),5):
        for col,item in zip(st.columns(5),items[start:start+5]):
            col.metric(item['label'],numero(item['value'])+(' %' if '(%)' in item['label'] and math.isfinite(item['value']) else ''),help=item['help'])
    info('Q es el último trimestre fiscal observado; el crecimiento compara con Q−1 y puede reflejar estacionalidad o extraordinarios. TTM suma cuatro trimestres consecutivos. Acciones diluidas medias incluye el efecto dilutivo de opciones, RSU y convertibles cuando procede; no equivale a acciones exactas al cierre ni incluye automáticamente toda opción existente. EV/EBITDA Yahoo es informativo TTM/LTM; deuda neta/EBITDA utiliza EBITDA aproximado y puede diferir del EBITDA validado. Los datos ausentes permanecen sin valor.')


def fechas_grafico_trimestral(q,as_of):
    date=q.columns[0];plot=q[[date,'Ingresos','Beneficio neto']].copy()
    closes=pd.to_datetime(plot[date],errors='coerce')
    published=pd.to_datetime(q.get('Publicación de resultados estimada/registrada',pd.Series(pd.NaT,index=q.index)),errors='coerce')
    valid=published.notna() & (published>closes) & ((published-closes).dt.days<=90) & (published<=pd.Timestamp(as_of))
    if len(plot) and valid.all():
        plot[date]=published;label='Publicación Yahoo (registrada/estimada)'
        note='Fechas del calendario Yahoo guardadas en la captura y asociadas al cierre precedente; pueden ser registradas o estimadas. No acreditan por sí solas la publicación oficial.'
    else:
        plot[date]=closes;label='Cierre del trimestre'
        note='Faltan fechas de publicación completas o coherentes: se muestran cierres fiscales para no omitir trimestres ni inventar publicaciones. Una fecha de cierre fiscal no es una fecha de presentación.'
    plot=plot.sort_values(date);plot['Trimestre']=plot[date].dt.strftime('%Y/%m/%d')
    return plot,label,note
