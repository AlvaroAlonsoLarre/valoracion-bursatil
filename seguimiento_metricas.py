"""Presentación de métricas V7 y QoQ reportado con periodos fiscales auditables."""
import hashlib
import json
import numpy as np
import pandas as pd
from auditoria_io import clean,restore_frame
from historico_acciones import number
from sec_quarterly import records,quarter_fact


def quarter_series(quarterly,as_of,facts=None,currency='USD',include_predecessor=False):
    day=pd.Timestamp(as_of).normalize();q=quarterly.sort_index();rows={}
    conflicts=set(q.attrs.get('field_conflicts',{}).get('Beneficio neto',[]))
    for date,row in q.iterrows():
        date=pd.Timestamp(date).normalize()
        if date>day:continue
        value=number(row.get('Beneficio neto'))
        if str(date.date()) in conflicts or 'Beneficio neto' in q.attrs.get('invalid_flows',[]):value=np.nan
        start=pd.to_datetime(row.get('Inicio'),errors='coerce')
        if pd.notna(start) and not 70<=(date-start).days+1<=105:value=np.nan
        rows[date]={'Cierre':date,'Inicio':start if pd.notna(start) else None,'Beneficio neto':value,'Fuente':row.get('Fuente') or 'Captura trimestral V7 SEC/Yahoo','Componentes':row.get('Componentes',[]),
                    'SHA256':row.get('SHA256'),'Estado':'Reportado; duración contrastada por cadencia' if np.isfinite(value) else 'Sin dato / conflicto V7'}
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
    selected=d[d['Cierre']>end-pd.DateOffset(years=5)].tail(20)
    if include_predecessor and len(selected):
        prior=d[d['Cierre']<selected.iloc[0]['Cierre']].tail(1)
        selected=pd.concat([prior,selected])
    return selected.reset_index(drop=True)


def cohort_stats(peers,column,allowed,cohort=None,period='TTM',currency=None):
    if peers.empty or column not in peers:return {'mean':None,'median':None,'n':0,'period':period,'warning':'Sin comparables con evidencia suficiente','rows':[]}
    p=peers[peers.get(allowed,pd.Series(False,index=peers.index)).eq(True)].copy()
    p=p[pd.to_numeric(p[column],errors='coerce').gt(0)]
    if currency and 'Divisa cotización' in p:p=p[p['Divisa cotización'].eq(currency)]
    p['issuer']=[next((str(r[k]).upper() for k in ['Emisor económico','Emisor id','Ticker'] if k in r and pd.notna(r[k]) and str(r[k]).strip()),'') for _,r in p.iterrows()]
    p=p[p['issuer'].ne('')]
    p=p.drop_duplicates('issuer')
    v=pd.to_numeric(p[column],errors='coerce');reason=''
    if cohort and (cohort not in p or p[cohort].nunique(dropna=False)!=1):reason='Cohortes contables/temporales/perímetros heterogéneos'
    if len(v)<3:reason='Menos de tres comparables válidos homogéneos'
    if len(v) and (v.max()/v.min()>3.5):reason='Dispersión >3,5×: no se presenta una media representativa'
    return clean({'mean':float(v.mean()) if not reason else None,'median':float(v.median()) if len(v) else None,'n':len(v),'period':period,
                  'warning':reason,'rows':p.drop(columns=['Evidencia TTM','Evidencia múltiplos'],errors='ignore').to_dict('records')})


def fiscal_ev(payload,annual,qualified):
    from seguimiento_ev import fiscal_history
    return fiscal_history(payload,annual)


def informative_peers(universe,info,provider_infos=None):
    """Nivel B descriptivo; jamás se devuelve al selector ni al motor de valoración."""
    provider_infos=provider_infos or {};rows=[]
    def text(x):return str(x).casefold() if pd.notna(x) else ''
    for _,r in universe.iterrows():
        ticker=str(r.get('Ticker') or '');provider=provider_infos.get(ticker,{})
        same_ind=(r.get('Misma industria') is True or bool(text(r.get('Industria clave')) and text(r.get('Industria clave'))==text(info.get('industryKey'))))
        same_sector=(r.get('Mismo sector') is True or bool(text(r.get('Sector clave')) and text(r.get('Sector clave'))==text(info.get('sectorKey')))
                     or bool(text(r.get('Sector')) and text(r.get('Sector'))==text(info.get('sector'))))
        similarity=number(r.get('Similitud de actividad (0-100)'))
        related=same_ind or same_sector or similarity>=25
        if not related:continue
        currency=provider.get('currency') or r.get('Divisa cotización')
        financial=provider.get('financialCurrency') or r.get('Divisa financiera')
        reported_end=pd.to_datetime(provider.get('mostRecentQuarter'),unit='s',utc=True,errors='coerce')
        end_label=str(reported_end.date()) if pd.notna(reported_end) else None
        vals={label:number(provider.get(key,r.get(raw))) for label,key,raw in [('PER TTM Yahoo','trailingPE','PER trailing'),('PER forward Yahoo','forwardPE','PER forward'),('EV/EBITDA Yahoo','enterpriseToEbitda','EV/EBITDA')]}
        rows.append({'Ticker':ticker,'Empresa':r.get('Empresa') or ticker,'Moneda cotización':currency,'Moneda financiera':financial,
            **vals,'Relación B':'Misma industria' if same_ind else 'Mismo sector' if same_sector else 'Actividad relacionada',
            'Nivel':'B · informativo, no validado para objetivos','Periodo PER':'TTM reportado / forward Yahoo no acreditado como NTM',
            'Periodo EV':'LTM Yahoo; ventana exacta no acreditada','Cierre reportado Yahoo':end_label,'Origen':'Yahoo Finance','Estado A':r.get('Observación','No reúne evidencia A'),
            'Prioridad':(2 if same_ind else 1)+(.1 if any(v>0 for v in vals.values()) else 0)+(similarity/1000 if np.isfinite(similarity) else 0)})
    rows=sorted(rows,key=lambda r:(-r['Prioridad'],r['Ticker']));seen=set();unique=[]
    for row in rows:
        if row['Ticker'] not in seen:unique.append(row);seen.add(row['Ticker'])
    chosen=unique[:6];summary={}
    for column in ['PER TTM Yahoo','PER forward Yahoo','EV/EBITDA Yahoo']:
        eligible=[r[column] for r in chosen if number(r[column])>0 and r['Moneda cotización']==info.get('currency') and r['Moneda financiera']==r['Moneda cotización']]
        summary[column]={'mean':float(np.mean(eligible)) if eligible else None,'median':float(np.median(eligible)) if eligible else None,'n':len(eligible),
                         'confidence':'Baja · descriptivo; sin validar periodos/perímetro/beneficios','period':column,
                         'warning':'No utilizar en objetivos. Cada media conserva su definición; forward Yahoo no se renombra NTM. Sólo misma moneda; no se usan valores no positivos.'}
    return clean({'rows':chosen,'candidates':unique,'stats':summary})


def summarize(payload,result,quarters=None):
    q=restore_frame(payload['frames']['quarterly']) if payload['frames'].get('quarterly') else pd.DataFrame()
    a=restore_frame(payload['frames']['annual']);s=result.summary
    stored=payload.get('historical',{}).get('Seguimiento neto trimestral')
    if quarters is None and stored:
        saved=restore_frame(stored)
        if 'Cierre' in saved:saved.index=pd.to_datetime(saved['Cierre']);series=quarter_series(saved,s['as_of'])
        else:series=quarter_series(q,s['as_of'])
    else:series=quarter_series(q,s['as_of']) if quarters is None else quarters
    series=series.tail(20)
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
    from seguimiento_ev import yahoo_ratio
    watched=payload.get('evidence',{}).get('watch_provider',{})
    provider=yahoo_ratio(watched.get('info') or info,watched.get('queried_at') or s['as_of'])
    profiles=payload.get('evidence',{}).get('watch_peer_profiles',{})
    informative=informative_peers(result.universe,info,{ticker:source.get('info',{}) for ticker,source in profiles.items()})
    for candidate in informative['rows']+informative['candidates']:
        candidate['Ratios consultados (UTC)']=pd.to_datetime(profiles.get(candidate['Ticker'],{}).get('queried_at'),unit='s',utc=True,errors='coerce') if profiles.get(candidate['Ticker']) else s['as_of']+' · captura archivada'
    row={'Empresa':info.get('longName') or info.get('shortName') or s['ticker'],'Ticker':s['ticker'],'Precio':s['price'],'Moneda':s['currency'],'Fecha precio':s.get('quote_date'),
         'PER actual TTM':pe,'PER mediana 5 FY':median,'Descuento PER (%)':100*(median-pe)/median if median>0 and pe>0 else np.nan,
         'PER comparables TTM':per['mean'],'QoQ neto reciente (%)':latest[0],'QoQ neto anterior (%)':latest[1],'QoQ neto tercero (%)':latest[2],
         'QoQ media 5a (%)':values.mean(),'QoQ mediana 5a (%)':values.median(),'Cobertura QoQ':f'{int(values.notna().sum())}/20',
         'EV/EBITDA Yahoo':provider['value'],'Periodo EV Yahoo':provider['period'],'EV/EBITDA último FY':fy['last'],'EV/EBITDA mediana 5 FY':fy['median'],'Calidad EV FY':fy['last_type']+' · '+fy['last_confidence'] if fy['last'] else 'No disponible',
         'EV/EBITDA comparables NTM':ev['mean'],'PER TTM comparables B':informative['stats']['PER TTM Yahoo']['mean'],'PER forward comparables B':informative['stats']['PER forward Yahoo']['mean'],'EV/EBITDA comparables B':informative['stats']['EV/EBITDA Yahoo']['mean'],
         'Últimos resultados':str(q.index.max().date()) if len(q) else None,'Origen':s['source'],'Advertencias':' · '.join(warnings)}
    return clean({'schema_version':3,'summary':s,'methods':result.methods.to_dict('records'),'informative_peers':informative,'provider_ev':provider,'row':row,'per_peers':per,'per_ntm':ntm,'ev_peers':ev,'ev_fy':fy,'per_history_n':count,'quarters':series.to_dict('records'),
                  'historical_pe':result.qualified_history.to_dict('records'),'assumptions':result.settings,'targets':result.valuation.to_dict('records')})


def discount_color(value):
    n=number(value)
    return 'background-color: #dcfce7; color: #14532d' if n>0 else 'background-color: #fee2e2; color: #7f1d1d' if n<0 else ''
