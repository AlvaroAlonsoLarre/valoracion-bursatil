"""Vista de cotización y escenarios del motor original, sin red ni nuevo motor."""
import numpy as np
import pandas as pd
from auditoria_io import restore_frame
from historico_acciones import number

HISTORY=('1 semana','4 meses','1 año')
FORECAST={'Ninguna':0,'1 mes':1,'4 meses':4,'1 año':12,'3 años':36}
COLORS={'Cotización':'#24415b','Pesimista':'#b46d3a','Base':'#008d99','Optimista':'#536bc0'}
COLUMNS=['Fecha','Precio','Serie','Tipo','Origen']


def chart_data(payload,summary,valuation,history='1 año',forecast='1 año'):
    if history not in HISTORY or forecast not in FORECAST:raise ValueError('Periodo gráfico no válido')
    day=pd.Timestamp(summary['as_of']).normalize();price=number(summary.get('price'));rows=[]
    archive=payload.get('historical',{}).get('Precios y splits')
    prices=restore_frame(archive) if archive else pd.DataFrame()
    start=day-pd.Timedelta(days=7) if history=='1 semana' else day-pd.DateOffset(months=4 if history=='4 meses' else 12)
    if not prices.empty and 'Close' in prices:
        prices.index=pd.to_datetime(prices.index).tz_localize(None).normalize()
        values=pd.to_numeric(prices['Close'],errors='coerce')
        values=values[(values.index>=start)&(values.index<=day)&(values>0)].dropna()
        for date,value in values.items():rows.append({'Fecha':date,'Precio':float(value),'Serie':'Cotización','Tipo':'Observado','Origen':'Close archivado, ajustado por splits, sin dividendos'})
    months=FORECAST[forecast]
    if months and price>0 and summary.get('quote_verified'):
        selected=valuation[valuation['Método'].eq('EPS × PER')]
        for name in ['Pesimista','Base','Optimista']:
            targets={int(r['Horizonte (años)']):number(r['Precio objetivo']) for _,r in selected[selected['Escenario'].eq(name)].iterrows() if number(r['Precio objetivo'])>0}
            if 1 not in targets:
                if months==36 and 3 in targets:
                    rows.extend([{'Fecha':day,'Precio':price,'Serie':name,'Tipo':'Proyección','Origen':'Ancla: precio observado'},
                                 {'Fecha':day+pd.DateOffset(years=3),'Precio':targets[3],'Serie':name,'Tipo':'Proyección','Origen':'Objetivo EPS × PER del motor'}])
                continue
            d1=day+pd.DateOffset(years=1);d3=day+pd.DateOffset(years=3)
            end=day+pd.DateOffset(months=months)
            if end>d1 and 3 not in targets:end=d1
            dates=set(pd.date_range(day,end,periods=60));dates.update([day,end])
            if end>=d1:dates.add(d1)
            if end>=d3:dates.add(d3)
            for date in sorted(dates):
                left,right,p0,p1=(day,d1,price,targets[1]) if date<=d1 else (d1,d3,targets[1],targets[3])
                weight=(date-left).total_seconds()/(right-left).total_seconds()
                value=p0*(p1/p0)**weight
                origin='Objetivo EPS × PER del motor' if date in (d1,d3) else 'Ancla: precio observado' if date==day else 'Interpolación geométrica ilustrativa; no previsión mensual'
                rows.append({'Fecha':date,'Precio':float(value),'Serie':name,'Tipo':'Proyección','Origen':origin})
    return pd.DataFrame(rows,columns=COLUMNS)


def render(payload,summary,valuation,key):
    import streamlit as st
    import altair as alt
    a,b=st.columns(2)
    history=a.selectbox('Histórico de cotización',HISTORY,index=2,key='hist_'+key)
    forecast=b.selectbox('Previsión gráfica',list(FORECAST),index=3,key='fut_'+key)
    data=chart_data(payload,summary,valuation,history,forecast)
    if data[data['Tipo'].eq('Observado')].empty:st.caption('La captura no contiene cierres diarios para este periodo. No se fabrica un histórico ni se vuelve a descargar al cambiar el selector.')
    if FORECAST[forecast] and data[data['Tipo'].eq('Proyección')].empty:st.info('Sin objetivos EPS × PER admisibles para dibujar. Consulta el motivo por método; un PER manual sólo resuelve la falta de múltiplo.')
    if not data.empty:
        names=list(COLORS)
        chart=alt.Chart(data).mark_line(strokeWidth=2.4).encode(
            x=alt.X('Fecha:T',title='Fecha'),y=alt.Y('Precio:Q',title='Precio · '+summary['currency'],scale=alt.Scale(zero=False)),
            color=alt.Color('Serie:N',scale=alt.Scale(domain=names,range=list(COLORS.values())),title=''),
            strokeDash=alt.StrokeDash('Tipo:N',scale=alt.Scale(domain=['Observado','Proyección'],range=[[1,0],[7,5]]),legend=None),
            tooltip=[alt.Tooltip('Fecha:T',format='%d/%m/%Y'),alt.Tooltip('Precio:Q',format=',.2f'),'Serie:N','Origen:N'])
        st.altair_chart(chart.properties(height=330).interactive(),width='stretch')
    st.caption('Sólida: cotización observada archivada. Discontinuas: escenarios del motor a 1/3 años. Los puntos intermedios son interpolaciones geométricas ilustrativas, no previsiones mensuales. Sin dividendos. No se extrapola un horizonte ausente.')
    return data
