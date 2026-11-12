"""Revisión acotada de filings oficiales a la fecha de valoración, sin inferir US-GAAP."""
import hashlib
import re
import pandas as pd
import requests
from bs4 import BeautifulSoup


def review_filings(config,as_of,requests_get=None,max_documents=8):
    if not config:return []
    get=requests_get or requests.get;today=pd.Timestamp(as_of).normalize();rows=[]
    headers={'User-Agent':'StockValuationProject/1.0'}
    cik=str(config['cik']).lstrip('0');url=f'https://data.sec.gov/submissions/CIK{int(cik):010d}.json'
    try:
        response=get(url,headers=headers,timeout=20);response.raise_for_status();data=response.json()
        if str(data.get('cik','')).lstrip('0')!=cik:raise ValueError('Emisor del índice distinto')
        recent=data['filings']['recent'];count=0
        for i,filed in enumerate(recent.get('filingDate',[])):
            if recent['form'][i] not in ('6-K','6-K/A','20-F','20-F/A'):continue
            if pd.Timestamp(filed)>today or pd.Timestamp(filed)<pd.Timestamp(config['period_end']):continue
            if count>=max_documents:break
            count+=1;acc=recent['accessionNumber'][i]
            primary=recent['primaryDocument'][i]
            source=f'https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace("-","")}/{primary}'
            row={'Emisor':data.get('name'),'CIK':cik,'Presentado':filed,'Formulario':recent['form'][i],
                 'Accession':acc,'Fuente':source,'SHA256 índice':hashlib.sha256(response.content).hexdigest(),
                 'Periodo buscado':config['period_end'],'Estado':'NO_VERIFICADO'}
            try:
                doc=get(source,headers=headers,timeout=15);doc.raise_for_status()
                text=' '.join(BeautifulSoup(doc.content,'html.parser').stripped_strings)
                has_cash=bool(re.search(r'(?:consolidated.{0,60}cash flows|cash flows.{0,60}consolidated)',text,re.I))
                row.update({'SHA256 documento':hashlib.sha256(doc.content).hexdigest(),
                    'Estado':'CANDIDATO_PARA_CONCILIAR' if has_cash else 'SIN_ESTADO_CASHFLOW_EN_DOCUMENTO',
                    'Detalle':'No convierte un 6-K en cobertura CompanyFacts US-GAAP; requiere periodo, unidad y extractores validados'})
            except Exception as exc:row['Detalle']=type(exc).__name__+': '+str(exc)[:140]
            rows.append(row)
    except Exception as exc:rows.append({'Fuente':url,'Estado':'NO_VERIFICADO','Detalle':type(exc).__name__+': '+str(exc)[:160]})
    dart=config.get('dart_index')
    if dart:
        row={'Fuente':dart,'Estado':'NO_VERIFICADO','Periodo buscado':config['period_end']}
        try:
            doc=get(dart,headers=headers,timeout=20);doc.raise_for_status()
            ids=sorted(set(re.findall(r'20\d{12}',doc.text)))
            row.update({'SHA256 documento':hashlib.sha256(doc.content).hexdigest(),'IDs observados':','.join(ids),
                'Estado':'INDICE_DART_REVISADO','Detalle':'Índice público: no acredita por sí solo CAPEX/D&A ni ausencia global de otros documentos'})
        except Exception as exc:row['Detalle']=type(exc).__name__+': '+str(exc)[:140]
        rows.append(row)
    return rows


def components_reconciliation(q):
    rows=[]
    if q is None:return pd.DataFrame()
    for date,row in q.sort_index().iterrows():
        ppe=row.get('CAPEX PP&E');intangibles=row.get('CAPEX intangibles');total=row.get('CAPEX')
        complete=all(pd.notna(v) for v in [ppe,intangibles,total])
        residual=total-ppe-intangibles if complete else None
        cfo=row.get('D&A cash flow');operating=row.get('D&A operativa')
        da_gap=cfo-operating if pd.notna(cfo) and pd.notna(operating) else None
        rows.append({'Cierre':str(pd.Timestamp(date).date()),'CAPEX PP&E':ppe,'CAPEX intangibles':intangibles,
            'CAPEX total':total,'Residual CAPEX':residual,'CAPEX completo':complete,
            'D&A cash flow':cfo,'D&A operativa publicada':operating,'Diferencia D&A CFO-operativa':da_gap,
            'Estado D&A':'PENDIENTE_PUENTE' if da_gap is not None else 'SIN_DOS_DEFINICIONES_COMPARABLES',
            'Fuente':row.get('Fuente financiera','Yahoo cash-flow; no revisión oficial adicional acreditada')})
    return pd.DataFrame(rows)
