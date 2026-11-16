"""Presentación de métricas V7 y QoQ reportado con periodos fiscales auditables."""
import hashlib
import json
import numpy as np
import pandas as pd
from auditoria_io import clean,restore_frame
from historico_acciones import number
from sec_quarterly import records,quarter_fact


def quarter_series(quarterly,as_of,facts=None,currency='USD'):
    day=pd.Timestamp(as_of).normalize();q=quarterly.sort_index();rows={}
    conflicts=set(q.attrs.get('field_conflicts',{}).get('Beneficio neto',[]))
    for date,row in q.iterrows():
        date=pd.Timestamp(date).normalize()
        if date>day:continue
        value=number(row.get('Beneficio neto'))
        if str(date.date()) in conflicts or 'Beneficio neto' in q.attrs.get('invalid_flows',[]):value=np.nan
        rows[date]={'Cierre':date,'Inicio':None,'Beneficio neto':value,'Fuente':'Captura trimestral V7 SEC/Yahoo','Componentes':[],
                    'Estado':'Reportado; duración contrastada por cadencia' if np.isfinite(value) else 'Sin dato / conflicto V7'}
    if facts:
        data=records(facts,['NetIncomeLoss','ProfitLoss'],currency,day)
        fingerprint=hashlib.sha256(json.dumps(facts,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        for end in sorted({pd.Timestamp(r['end']) for r in data}):
            if end<day-pd.DateOffset(years=6):continue
            value,parts=quarter_fact(data,end,True)
            if not parts or not np.isfinite(value):continue
            start=pd.Timestamp(parts[0]['start']) if len(parts)==1 else pd.Timestamp(parts[1]['end'])+pd.Timedelta(days=1)
            if not 70<=(end-start).days+1<=105:continue
            # Una comparación fiscal cercana sólo se alinea si V7 ya la concilió;
            # no se inventa la identidad de trimestres con distintas fechas.
            old=rows.get(end);state='SEC directo' if len(parts)==1 else 'SEC diferencia YTD (flujo aditivo)'
            if old and (not np.isfinite(number(old['Beneficio neto'])) or not np.isclose(value,old['Beneficio neto'],rtol=.009999,atol=1.)):
                value=np.nan;state='BLOQUEADO: divergencia SEC–captura V7'
            rows[end]={'Cierre':end,'Inicio':start,'Beneficio neto':value,'Fuente':'https://data.sec.gov/api/xbrl/companyfacts/CIK'+str(facts['cik']).zfill(10)+'.json',
                       'SHA256':fingerprint,'Componentes':parts,'Estado':state}
    d=pd.DataFrame(rows.values())
    if d.empty:return pd.DataFrame(columns=['Cierre','Beneficio neto','QoQ (%)','Motivo QoQ','Fuente','Estado'])
    d=d.sort_values('Cierre').reset_index(drop=True)
    d['QoQ (%)']=np.nan;d['Motivo QoQ']='Sin trimestre anterior'
    for i in range(1,len(d)):
        a,b=d.iloc[i-1],d.iloc[i];reason=''
        if not 70<=(b['Cierre']-a['Cierre']).days<=105:reason='Periodos no consecutivos de aproximadamente tres meses'
        elif pd.notna(b.get('Inicio')) and b['Inicio']!=a['Cierre']+pd.Timedelta(days=1):reason='Periodos oficiales no contiguos'
        elif not np.isfinite(number(a['Beneficio neto'])) or not np.isfinite(number(b['Beneficio neto'])):reason='Beneficio ausente/conflictivo'
        elif a['Beneficio neto']<=0:reason='Referencia nula o negativa: porcentaje no representativo'
        else:d.loc[i,'QoQ (%)']=100*(b['Beneficio neto']/a['Beneficio neto']-1)
        d.loc[i,'Motivo QoQ']=reason or 'Beneficio neto reportado; no ajustado por extraordinarios; no anualizado'
    end=d['Cierre'].max()
    return d[d['Cierre']>end-pd.DateOffset(years=5)].tail(20).reset_index(drop=True)


def cohort_stats(peers,column,allowed,cohort=None,period='TTM',currency=None):
    if peers.empty or column not in peers:return {'mean':None,'median':None,'n':0,'period':period,'warning':'Sin comparables con evidencia suficiente','rows':[]}
    p=peers[peers.get(allowed,pd.Series(False,index=peers.index)).eq(True)].copy()
    p=p[pd.to_numeric(p[column],errors='coerce').gt(0)]
    if currency and 'Divisa cotización' in p:p=p[p['Divisa cotización'].eq(currency)]
    p['issuer']=[str(r.get('Emisor económico') or r.get('Emisor id') or r.get('Ticker')).upper() for _,r in p.iterrows()]
    p=p.drop_duplicates('issuer')
    v=pd.to_numeric(p[column],errors='coerce');reason=''
    if cohort and (cohort not in p or p[cohort].nunique(dropna=False)!=1):reason='Cohortes contables/temporales/perímetros heterogéneos'
    if len(v)<3:reason='Menos de tres comparables válidos homogéneos'
    if len(v) and (v.max()/v.min()>3.5):reason='Dispersión >3,5×: no se presenta una media representativa'
    return clean({'mean':float(v.mean()) if not reason else None,'median':float(v.median()) if len(v) else None,'n':len(v),'period':period,
                  'warning':reason,'rows':p.drop(columns=['Evidencia TTM','Evidencia múltiplos'],errors='ignore').to_dict('records')})


def fiscal_ev(payload,annual,qualified):
    # V7 no publica un EV FY auditado en su snapshot: el EV aproximado del Excel
    # heredado no acredita por sí solo acciones al cierre/perímetro/D&A pura.
    # Sólo se presentan valores ya acreditados explícitamente, nunca un TTM/NTM.
    return {'last':None,'median':None,'n':0,'warning':'V7 no aporta EV/EBITDA FY acreditado: falta puente EV al cierre, perímetro y D&A pura; no se sustituye por Yahoo TTM/NTM'}


def summarize(payload,result,quarters=None):
    q=restore_frame(payload['frames']['quarterly']) if payload['frames'].get('quarterly') else pd.DataFrame()
    a=restore_frame(payload['frames']['annual']);s=result.summary
    series=quarter_series(q,s['as_of']) if quarters is None else quarters
    stats=result.history_statistics
    h=stats[stats['Indicador'].eq('PER histórico')&stats['Ventana (ejercicios)'].eq(5)]
    hrow=h.iloc[0] if len(h) else {};median=number(hrow.get('Mediana'));count=int(hrow.get('Observaciones',0))
    metric=result.metrics[result.metrics['Indicador'].eq('PER TTM')];pe=number(metric.iloc[0]['Valor']) if len(metric) else np.nan
    peers=result.peers.copy()
    if 'PER TTM verificado' in peers:
        peers['ttm_ok']=pd.to_numeric(peers['PER TTM verificado'],errors='coerce').between(2,100)
    per=cohort_stats(peers,'PER TTM verificado','ttm_ok',period='TTM',currency=s['currency'])
    # No se sustituye la media TTM principal por una mezcla de observaciones forward.
    ntm=cohort_stats(peers,'PER NTM verificado','PER admisible','PER cohorte',period='NTM',currency=s['currency'])
    ev=cohort_stats(peers,'EV/EBITDA (x)','EV/EBITDA admisible','EV cohorte',period='NTM',currency=s['currency'])
    fy=fiscal_ev(payload,a,result.qualified_history)
    values=pd.to_numeric(series['QoQ (%)'],errors='coerce') if len(series) else pd.Series(dtype=float)
    latest=list(values.tail(3).iloc[::-1])+[np.nan]*3
    warnings=[str(x) for x in [per['warning'],ev['warning'],fy['warning']] if x]
    from revision_economica import investment_amounts
    gains=investment_amounts(q).tail(4)
    if len(gains) and gains.abs().sum()>0:
        warnings.append('El beneficio neto/EPS TTM reportado contiene resultados de inversiones; PER y QoQ no son beneficios recurrentes normalizados')
    if count<3:warnings.append(f'PER histórico: {count}/5 FY limpios; referencia exploratoria, no valoración automática suficiente')
    if len(series)<20 or values.notna().sum()<20:warnings.append(f'QoQ: {int(values.notna().sum())}/20 variaciones válidas; {len(series)}/20 cierres disponibles')
    warnings.append('QoQ del neto reportado, no recurrente; extraordinarios y estacionalidad pueden distorsionar la comparación')
    info=payload['kwargs'].get('info') or {}
    row={'Empresa':info.get('longName') or info.get('shortName') or s['ticker'],'Ticker':s['ticker'],'Precio':s['price'],'Moneda':s['currency'],'Fecha precio':s.get('quote_date'),
         'PER actual TTM':pe,'PER mediana 5 FY':median,'Descuento PER (%)':100*(median-pe)/median if median>0 and pe>0 else np.nan,
         'PER comparables TTM':per['mean'],'QoQ neto reciente (%)':latest[0],'QoQ neto anterior (%)':latest[1],'QoQ neto tercero (%)':latest[2],
         'QoQ media 5a (%)':values.mean(),'QoQ mediana 5a (%)':values.median(),'Cobertura QoQ':f'{int(values.notna().sum())}/20',
         'EV/EBITDA último FY':fy['last'],'EV/EBITDA mediana 5 FY':fy['median'],'EV/EBITDA comparables NTM':ev['mean'],
         'Últimos resultados':str(q.index.max().date()) if len(q) else None,'Origen':s['source'],'Advertencias':' · '.join(warnings)}
    return clean({'row':row,'per_peers':per,'per_ntm':ntm,'ev_peers':ev,'ev_fy':fy,'per_history_n':count,'quarters':series.to_dict('records'),
                  'historical_pe':result.qualified_history.to_dict('records'),'assumptions':result.settings,'targets':result.valuation.to_dict('records')})


def discount_color(value):
    n=number(value)
    return 'background-color: #dcfce7; color: #14532d' if n>0 else 'background-color: #fee2e2; color: #7f1d1d' if n<0 else ''
