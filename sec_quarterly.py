"""Conciliación SEC–Yahoo por flujo: fechas reales, trimestres y diferencias YTD.

Nunca diferencia EPS ni medias de acciones. Conserva ambos importes y los
componentes de cada reconstrucción; una divergencia sólo invalida ese campo.
"""
import hashlib
import json
import numpy as np
import pandas as pd
from historico_acciones import number

TAGS={
 'Ingresos':['RevenueFromContractWithCustomerExcludingAssessedTax','Revenues','SalesRevenueNet','RevenuesNetOfInterestExpense'],
 'Beneficio operativo':['OperatingIncomeLoss'], 'Beneficio neto':['NetIncomeLoss','ProfitLoss'],
 'Beneficio antes de impuestos':['IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest','IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments'],
 'Impuestos':['IncomeTaxExpenseBenefit'], 'EPS diluido':['EarningsPerShareDiluted'],
 'Acciones diluidas medias':['WeightedAverageNumberOfDilutedSharesOutstanding'],
 'Flujo de caja operativo':['NetCashProvidedByUsedInOperatingActivities'],
 'CAPEX':['PaymentsToAcquirePropertyPlantAndEquipment'],
 'Recompras de acciones':['PaymentsForRepurchaseOfCommonStock'], 'Dividendos':['PaymentsOfDividends','PaymentsOfDividendsCommonStock']}
FORMS={'10-Q','10-Q/A','10-K','10-K/A','S-1','S-1/A','424B4','10-12B','10-12B/A'}
NON_ADDITIVE={'EPS diluido','Acciones diluidas medias'}


def records(facts,tags,unit,as_of):
    for tag in tags:
        data=facts.get('facts',{}).get('us-gaap',{}).get(tag,{}).get('units',{}).get(unit,[])
        data=[dict(r,concept='us-gaap:'+tag,unit=unit) for r in data if r.get('form') in FORMS
              and r.get('start') and r.get('end') and r.get('filed')
              and pd.Timestamp(r['filed'])<=as_of and pd.Timestamp(r['end'])<=as_of and np.isfinite(number(r.get('val')))]
        if data:return data
    return []


def quarter_fact(data,end,additive=True):
    direct=[r for r in data if pd.Timestamp(r['end'])==end and 65<=(end-pd.Timestamp(r['start'])).days+1<=115]
    if direct:
        r=max(direct,key=lambda r:r['filed']);return number(r['val']),[r]
    if additive:
        cumulative=sorted([r for r in data if pd.Timestamp(r['end'])==end
                           and 150<=(end-pd.Timestamp(r['start'])).days+1<=400],key=lambda r:r['filed'],reverse=True)
        for r in cumulative:
            prior=[p for p in data if p['start']==r['start'] and 65<=(end-pd.Timestamp(p['end'])).days<=115
                   and p['filed']<=r['filed']]
            if prior:
                p=max(prior,key=lambda p:(p['end'],p['filed']))
                return number(r['val'])-number(p['val']),[r,dict(p,coefficient=-1)]
    return np.nan,[]


def reconcile_quarters(quarterly,facts,currency,as_of,prices=None):
    q=quarterly.copy();day=pd.Timestamp(as_of).tz_localize(None);audit=[]
    source='https://data.sec.gov/api/xbrl/companyfacts/CIK'+str(facts['cik']).zfill(10)+'.json'
    fingerprint=hashlib.sha256(json.dumps(facts,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    data={k:records(facts,tags,'shares' if k=='Acciones diluidas medias' else currency+'/shares' if k=='EPS diluido' else currency,day) for k,tags in TAGS.items()}
    ends=sorted({pd.Timestamp(r['end']) for rows in data.values() for r in rows if (day-pd.Timestamp(r['end'])).days<=1000})
    splits=pd.Series(dtype=float) if prices is None else prices.get('Stock Splits',pd.Series(dtype=float))
    if len(splits):splits.index=pd.to_datetime(splits.index).tz_localize(None);splits=splits[(splits>0)&(splits!=1)&(splits.index<=day)]
    def value(field,end):
        v,parts=quarter_fact(data[field],end,field not in NON_ADDITIVE)
        if parts and field in NON_ADDITIVE:
            factor=splits[splits.index>pd.Timestamp(parts[0]['filed'])].prod()
            v=v/factor if field=='EPS diluido' else v*factor
        return v,parts
    for original in list(q.index):
        original=pd.Timestamp(original);candidates=[end for end in ends if abs((end-original).days)<=7]
        end=original
        if original not in candidates:
            # Fecha de calendario del proveedor sólo se reemplaza si DOS importes
            # independientes acreditan el mismo periodo. No se ignora un filing nuevo.
            matches=[]
            for possible in candidates:
                count=0
                for field in ['Ingresos','Beneficio operativo','Beneficio neto']:
                    official,_=value(field,possible);observed=number(q.loc[original].get(field))
                    count+=int(np.isfinite(official) and np.isfinite(observed) and np.isclose(official,observed,rtol=.009999,atol=1.))
                if count>=2:matches.append(possible)
            if len(matches)==1:
                end=matches[0];q=q.rename(index={original:end})
                audit.append({'Campo':'Fecha cierre','Fecha Yahoo':str(original.date()),'Fecha SEC':str(end.date()),'Estado':'DISPONIBLE','Detalle':'Mismo trimestre acreditado por ≥2 flujos (<1%); calendario 52/53 semanas','Fuente':source,'SHA256':fingerprint})
        if end not in ends:continue
        for field in TAGS:
            official,parts=value(field,end)
            if not np.isfinite(official):continue
            observed=number(q.loc[end].get(field));official=abs(official) if field in ['CAPEX','Recompras de acciones','Dividendos'] else official
            ok=not np.isfinite(observed) or np.isclose(observed,official,rtol=.009999,atol=.005 if field=='EPS diluido' else 1.)
            q.loc[end,field]=official if ok else np.nan
            audit.append({'Campo':field,'Fecha Yahoo':str(original.date()),'Fecha SEC':str(end.date()),'Valor Yahoo':observed,'Valor SEC':official,
                'Estado':'DISPONIBLE' if ok else 'BLOQUEADO','Detalle':'SEC completa ausencia' if not np.isfinite(observed) else 'Conciliado <1%' if ok else 'Divergencia material SEC–Yahoo; sólo este flujo se omite',
                'Fuente':source,'SHA256':fingerprint,'Componentes':json.dumps(parts,sort_keys=True)})
    # Las columnas derivadas no pueden conservar un valor anterior a la conciliación.
    for output,left,right in [('Flujo de caja libre','Flujo de caja operativo','CAPEX'),('EBITDA aproximado','Beneficio operativo','D&A')]:
        if left in q and right in q:q[output]=pd.to_numeric(q[left],errors='coerce')+(-1 if output=='Flujo de caja libre' else 1)*pd.to_numeric(q[right],errors='coerce')
    q.attrs['field_conflicts']={field:sorted({r['Fecha SEC'] for r in audit if r.get('Campo')==field and r['Estado']=='BLOQUEADO'}) for field in TAGS}
    return q.sort_index(),pd.DataFrame(audit)


def download_reconciliation(quarterly,cik,currency,as_of,user_agent,prices=None):
    from sec_historical import _get_json,SEC_FACTS_URL
    facts=_get_json(SEC_FACTS_URL.format(cik=str(cik).zfill(10)),user_agent)
    if str(facts.get('cik')).lstrip('0')!=str(cik).lstrip('0'):raise ValueError('CompanyFacts: CIK distinto')
    return reconcile_quarters(quarterly,facts,currency,as_of,prices)
