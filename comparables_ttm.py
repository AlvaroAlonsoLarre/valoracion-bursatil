"""Evidencia TTM separada de los forecasts; no convierte forwardPE en trailing.

Fuentes Yahoo para estados trimestrales, SEC para marco contable del emisor.
La evidencia íntegra del SDK se conserva con hash canónico y fecha de consulta.
"""
from datetime import datetime,timezone
import json
import re
import numpy as np
import pandas as pd
import requests
from auditoria_io import clean,frame_payload,restore_frame
from multiple_evidence import digest
from historico_acciones import number


def validate_ttm_evidence(row,as_of,target_end,expected_basis):
    try:
        ev=row.get('Evidencia TTM')
        if not isinstance(ev,dict) or ev.get('schema')!='reported-ttm-v1':raise ValueError('Sin evidencia TTM')
        p=ev['payload']
        if digest(p)!=ev['sha256']:raise ValueError('Hash TTM no coincide')
        day=pd.Timestamp(as_of).tz_localize(None).normalize()
        acquired=pd.to_datetime(ev['retrieved_at'],errors='coerce',utc=True)
        if pd.isna(acquired) or acquired.tz_localize(None).normalize()>day:raise ValueError('Fecha consulta TTM ausente/futura')
        if p['issuer_id']!=str(row.get('Emisor id') or row['Ticker']):raise ValueError('Emisor distinto')
        if p['accounting_basis']!=expected_basis or expected_basis not in ('US_GAAP','IFRS','K_IFRS'):raise ValueError('Marco contable incompatible/no verificado')
        if not re.match(r'^https://data.sec.gov/',p['basis_source']):raise ValueError('Marco contable sin procedencia oficial')
        if p.get('share_basis')!='ordinary':raise ValueError('ADR o clase de acciones sin puente')
        if p['financial_currency']!=p['quote_currency']:raise ValueError('Sin FX TTM documentado')
        q=restore_frame(p['quarters']).sort_index();end=pd.Timestamp(target_end)
        if pd.isna(end):raise ValueError('Sin cierre TTM objetivo')
        if len(q)!=4 or q.index.has_duplicates or q.isna().any().any() or not np.isfinite(q.to_numpy(dtype=float)).all():raise ValueError('Cuatro trimestres completos requeridos')
        if any(not 65<=(b-a).days<=115 for a,b in zip(q.index,q.index[1:])):raise ValueError('Trimestres no consecutivos')
        if abs((q.index[-1]-end).days)>7 or q.index[-1]>day or (day-q.index[-1]).days>125:raise ValueError('Ventana TTM no homogénea con objetivo')
        quoted=pd.to_datetime(p['quote_date'],errors='coerce',utc=True)
        if pd.isna(quoted):raise ValueError('Precio TTM sin fecha')
        quoted=quoted.tz_localize(None).normalize()
        if quoted>day or (day-quoted).days>7:raise ValueError('Precio TTM futuro/caducado')
        # Cada trimestre debe cerrar el puente común/diluido; no presumir cero minoritarios.
        if (q['shares']<=0).any() or (q['revenue']<=0).any():raise ValueError('Acciones o ingresos no positivos')
        residual=(q['eps']*q['shares']/q['common_net'].replace(0,np.nan)-1).abs()
        if residual.isna().any() or (residual>=.01).any():raise ValueError('EPS × acciones no concilia con beneficio común (<1%)')
        if (q['common_net']<=0).any():raise ValueError('Pérdida trimestral: beneficios no comparables por PER automático')
        if ((q['normalized_net']-q['common_net']).abs()/q['common_net']).max()>.20:raise ValueError('Ajustes de beneficios >20%; revisar extraordinarios')
        # Días implícitos desde cada cierre anterior; aproximación declarada de media diluida TTM.
        days=pd.Series([91.25]+[(b-a).days for a,b in zip(q.index,q.index[1:])],index=q.index)
        diluted=float((q['shares']*days).sum()/days.sum());eps=float(q['common_net'].sum()/diluted)
        price=number(p['price']);value=price/eps
        if not np.isfinite(value) or not 2<=value<=100:raise ValueError('PER TTM no representativo (rango 2–100)')
        return True,value,'TTM reportado; ponderación diluida aproximada; revisión extraordinarios proveedor, no auditoría independiente'
    except (KeyError,TypeError,ValueError,AttributeError,ZeroDivisionError,OverflowError) as exc:
        return False,np.nan,str(exc)


def collect_ttm_evidence(peers,yf,as_of,target_end,user_agent='StockValuationProject/1.0',requests_get=None):
    output=peers.copy();records=[];get=requests_get or requests.get
    if output.empty:return output,records
    output['Evidencia TTM']=None
    headers={'User-Agent':user_agent}
    try:
        r=get('https://www.sec.gov/files/company_tickers.json',headers=headers,timeout=20);r.raise_for_status()
        mapping=r.json();mapping=list(mapping.values()) if isinstance(mapping,dict) and 'fields' not in mapping else []
        tickers={str(x.get('ticker','')).upper():str(int(x['cik_str'])).zfill(10) for x in mapping if x.get('cik_str')}
    except Exception as exc:
        return output,[{'Estado':'NO_VERIFICADO','Fuente':'https://www.sec.gov/files/company_tickers.json','Detalle':str(exc)[:180]}]
    for index,row in output.iterrows():
        ticker=str(row['Ticker']);record={'Ticker':ticker,'Estado':'NO_VERIFICADO','Fecha consulta':datetime.now(timezone.utc).isoformat()}
        try:
            cik=tickers.get(ticker)
            if not cik:raise ValueError('Sin CIK SEC exacto; no inferir identidad por ticker base')
            source=f'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json'
            r=get(source,headers=headers,timeout=20);r.raise_for_status();facts=r.json()
            if str(facts.get('cik','')).lstrip('0')!=cik.lstrip('0'):raise ValueError('CIK distinto')
            # No basta registrar en EE.UU.; un 20-F IFRS no se etiqueta US-GAAP.
            concepts=facts.get('facts',{}).get('us-gaap',{})
            if 'EarningsPerShareDiluted' not in concepts:raise ValueError('Sin concepto US-GAAP de EPS diluido')
            now=pd.Timestamp(as_of).tz_localize(None).normalize()
            filed=[x for values in concepts['EarningsPerShareDiluted'].get('units',{}).values() for x in values
                   if x.get('filed') and pd.Timestamp(x['filed'])<=now and pd.Timestamp(x.get('end'))<=now]
            if not filed:raise ValueError('Sin EPS oficial presentado a la fecha')
            obj=yf.Ticker(ticker);raw=obj.get_income_stmt(freq='quarterly')
            if raw is None or raw.empty:raise ValueError('Sin estados trimestrales')
            required={'DilutedEPS':'eps','DilutedAverageShares':'shares','NetIncomeCommonStockholders':'common_net',
                      'TotalRevenue':'revenue','NormalizedIncome':'normalized_net'}
            if any(key not in raw.index for key in required):raise ValueError('Falta EPS, acciones, neto común, ingresos o revisión normalized')
            q=raw.loc[list(required)].T.rename(columns=required).apply(pd.to_numeric,errors='coerce')
            q.index=pd.to_datetime(q.index).tz_localize(None);q=q[q.index<=now].sort_index().tail(4)
            if q.empty:raise ValueError('Sin trimestres a la fecha')
            currency=row.get('Divisa financiera')
            latest=[x for unit,values in concepts['EarningsPerShareDiluted'].get('units',{}).items()
                if unit==str(currency)+'/shares' for x in values
                if x.get('start') and x.get('filed') and x.get('form') in ('10-Q','10-K')
                and pd.Timestamp(x['filed'])<=now and abs((pd.Timestamp(x['end'])-q.index[-1]).days)<=7
                and 65<=(pd.Timestamp(x['end'])-pd.Timestamp(x['start'])).days<=115]
            if not latest:raise ValueError('Sin EPS trimestral doméstico US-GAAP contemporáneo; ADR/20-F requiere puente')
            fact=max(latest,key=lambda x:x['filed'])
            if abs(number(fact['val'])/number(q.iloc[-1]['eps'])-1)>=.01:raise ValueError('EPS Yahoo/SEC no concilia (<1%)')
            actions=obj.splits
            # Para un split reciente se requiere comprobar que las cuatro cifras ya están reexpresadas.
            # No tratar la mera fecha de consulta como prueba de esa reexpresión.
            if actions is not None and len(actions):
                dates=pd.to_datetime(actions.index).tz_localize(None)
                if ((dates>q.index.min())&(dates<=now)).any():raise ValueError('Split dentro del TTM: requiere puente explícito')
            name=str(row.get('Empresa',''))
            if re.search(r'\b(ADR|ADS|depositary)\b',name,re.I):raise ValueError('ADR sin puente documentado')
            payload={'issuer_id':str(row.get('Emisor id') or ticker),'cik':cik,'accounting_basis':'US_GAAP',
                'basis_source':source,'basis_document_sha256':__import__('hashlib').sha256(r.content).hexdigest(),
                'share_basis':'ordinary','financial_currency':row.get('Divisa financiera'),
                'quote_currency':row.get('Divisa cotización'),'quote_date':row.get('Fecha cotización'),
                'price':clean(row.get('Precio actual')),'quarters':frame_payload(q),
                'sdk_source':'https://query2.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/'+ticker,
                'definition':'TTM neto común / media diluida ponderada por días aproximados; normalized sólo prueba de diferencias, no denominador'}
            ev={'schema':'reported-ttm-v1','payload':payload,'sha256':digest(payload),'retrieved_at':record['Fecha consulta']}
            output.at[index,'Evidencia TTM']=ev
            ok,value,note=validate_ttm_evidence(output.loc[index],as_of,target_end,'US_GAAP')
            record.update({'Estado':'EVIDENCIA_TTM' if ok else 'NO_VERIFICADO','PER TTM calculado':value,
                'Fuente':payload['sdk_source'],'Fuente marco contable':source,'SHA256 payload':ev['sha256'],'Detalle':note})
        except Exception as exc:record['Detalle']=type(exc).__name__+': '+str(exc)[:180]
        records.append(record)
    return output,records
