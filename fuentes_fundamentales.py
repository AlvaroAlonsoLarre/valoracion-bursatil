"""Enriquecimiento desde documentos oficiales; ningún número se toma del catálogo.

El catálogo declara emisor, URL y selectores. Los valores se extraen en cada
consulta, con fechas, unidad, precisión, hash y sin completar campos ausentes.
"""
from __future__ import annotations
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import hashlib
import json
import re
import numpy as np
import pandas as pd
import requests
from bs4 import BeautifulSoup
from sec_historical import parse_inline_xbrl


@dataclass
class Enrichment:
    annual: pd.DataFrame
    quarterly: pd.DataFrame
    evidence: dict


def _number(token):
    value=float(token.strip('()').replace(',',''))
    return -value if token.startswith('(') else value


def pure_da_facts(html, *, currency, entity_id, source, published):
    """Componentes disjuntos de la misma duración, moneda y contexto consolidado.

    Depreciation incluye la amortización de activos finance-lease de PP&E; no
    se vuelve a sumar FinanceLeaseRightOfUseAssetAmortization.
    """
    soup=BeautifulSoup(html,'html.parser')
    units={}
    for unit in soup.find_all(lambda t:t.name and t.name.split(':')[-1].lower()=='unit'):
        measure=unit.find(lambda t:t.name and t.name.split(':')[-1].lower()=='measure')
        if measure:units[unit.get('id')]=measure.get_text(strip=True).split(':')[-1].upper()
    contexts={}
    for context in soup.find_all(lambda t:t.name and t.name.split(':')[-1].lower()=='context'):
        identifier=context.find(lambda t:t.name and t.name.split(':')[-1].lower()=='identifier')
        if identifier:contexts[context.get('id')]=identifier.get_text(strip=True).lstrip('0')
    for fact in soup.find_all(lambda t:t.name and t.name.split(':')[-1].lower()=='nonfraction'):
        name=fact.get('name','')
        if name not in ('us-gaap:Depreciation','us-gaap:AmortizationOfIntangibleAssets'):continue
        context=fact.get('contextref')
        if contexts.get(context)!=entity_id.lstrip('0'):raise ValueError('Emisor XBRL distinto del solicitado')
        if units.get(fact.get('unitref'))!=currency:continue
    parsed=parse_inline_xbrl(html,{'url':source,'filing_date':published})
    grouped={}
    for fact in parsed:
        if fact['dimensions'] or fact['name'] not in ('us-gaap:Depreciation','us-gaap:AmortizationOfIntangibleAssets'):continue
        if units.get(fact['unitref'])!=currency or not fact['start'] or not fact['end']:continue
        if not 65<=(pd.Timestamp(fact['end'])-pd.Timestamp(fact['start'])).days+1<=400:continue
        key=(fact['start'],fact['end']);parts=grouped.setdefault(key,{})
        if fact['name'] in parts and parts[fact['name']]!=fact['value']:
            raise ValueError('Componentes D&A consolidados conflictivos')
        parts[fact['name']]=fact['value']
    result={}
    for period,parts in grouped.items():
        if len(parts)==2:
            result[period]={'value':sum(parts.values()),'components':parts,'source':source,'published':published,
                'precision':'Valores de notas redondeados; no precisión adicional inferida','derivation':'Depreciation + AmortizationOfIntangibleAssets'}
    return result


def quarter_da(intervals):
    """Resta intervalos anidados, nunca reparte un acumulado proporcionalmente."""
    result=dict(intervals)
    for _ in range(5):
        additions={}
        for (a,b),outer in list(result.items()):
            for (c,d),inner in list(result.items()):
                period=None
                if a==c and d<b:period=(str((pd.Timestamp(d)+pd.Timedelta(days=1)).date()),b)
                elif b==d and a<c:period=(a,str((pd.Timestamp(c)-pd.Timedelta(days=1)).date()))
                if period is None or period in result:continue
                days=(pd.Timestamp(period[1])-pd.Timestamp(period[0])).days+1
                if not 65<=days<=300:continue
                value=outer['value']-inner['value']
                if value<0:raise ValueError('D&A residual negativa: periodos o definiciones incompatibles')
                rec={'value':value,'components':{},'source':outer['source']+' ; '+inner['source'],
                     'published':max(outer['published'],inner['published']),
                     'precision':'Hereda redondeo de ambos intervalos',
                     'derivation':f'{a}/{b} menos {c}/{d}'}
                if period in additions and not np.isclose(additions[period]['value'],value,rtol=1e-12,atol=1):
                    raise ValueError('Derivaciones D&A incompatibles')
                additions[period]=rec
        if not additions:break
        result.update(additions)
    return {period:row for period,row in result.items() if 65<=(pd.Timestamp(period[1])-pd.Timestamp(period[0])).days+1<=115}


def pdf_rows(text, selectors, multiplier):
    records={}
    for field,label in selectors.items():
        matches=[line for line in text.splitlines() if re.match(r'^\s*'+re.escape(label)+r'\s+',line)]
        if not matches:continue
        rows=[]
        for line in matches:
            suffix=re.sub(r'^\s*'+re.escape(label), '',line)
            tokens=re.findall(r'\(?-?\d[\d,]*(?:\.\d+)?\)?',suffix)
            if len(tokens)>=3:rows.append([_number(token)*multiplier for token in tokens[:3]])
        if rows and any(row!=rows[0] for row in rows):raise ValueError('Filas PDF ambiguas: '+label)
        if rows:records[field]=rows[0]
    return records


def earnings_pdf(content, document, entity_name):
    from pypdf import PdfReader
    reader=PdfReader(BytesIO(content))
    texts={name:reader.pages[number-1].extract_text(extraction_mode='layout') for name,number in document['pages'].items()}
    full=' '.join(page.extract_text() for page in reader.pages)
    normalized=' '.join(full.split())
    if not all(token in normalized for token in document['required_text']):raise ValueError('Fecha, periodo o base consolidada del PDF no coinciden')
    if entity_name.lower() not in normalized.lower():raise ValueError('Emisor PDF no acreditado')
    if document['unit_text'] not in full:raise ValueError('Unidad monetaria PDF no acreditada')
    if document['income_header'] not in texts['income'] or document['cashflow_header'] not in texts['cashflow']:
        raise ValueError('Orden o periodo de columnas PDF no acreditado')
    # Las columnas tienen periodos distintos en balance y flujos: solo columna actual.
    output={};comparatives={}
    for name in ['cashflow','income','balance']:
        rows=pdf_rows(texts[name],document[name+'_fields'],document['multiplier'])
        for key,row in rows.items():output[key]=row[0];comparatives[key]=row[1:]
    required=['Ingresos','Beneficio operativo','Beneficio neto','EBITDA publicado','Flujo de caja operativo','CAPEX PP&E','Deuda total','Efectivo e inversiones']
    if any(field not in output for field in required):raise ValueError('Documento no contiene campos requeridos')
    for field in ['CAPEX PP&E','Dividendos']:output[field]=abs(output.get(field,np.nan))
    output['D&A operativa']=output['EBITDA publicado']-output['Beneficio operativo']
    # EPS es por acción, no miles de millones; no se inventa desde beneficio/acciones redondeadas.
    eps_section=texts['income'].split('EPS(KRW)')[-1].split('Shares')[0]
    eps=pdf_rows(eps_section,{'EPS diluido':'Diluted'},1.)
    if eps:output['EPS diluido']=eps['EPS diluido'][0]
    output['Deuda neta']=output['Deuda total']-output['Efectivo e inversiones']
    output['Tasa fiscal']=output.get('Impuestos',np.nan)/output.get('Beneficio antes de impuestos',np.nan)
    return output,comparatives


def enrich_financials(ticker,annual,quarterly,currency,as_of,*,requests_get=None,config=None):
    config=config if config is not None else json.loads(Path(__file__).with_name('fuentes_fundamentales.json').read_text())
    entry=config.get(ticker)
    a=annual.copy();q=quarterly.copy() if quarterly is not None else pd.DataFrame()
    evidence={'status':'SIN_COBERTURA','documents':[],'changes':[],'issues':[]}
    if not entry:return Enrichment(a,q,evidence)
    if currency!=entry['currency']:
        evidence['status']='BLOQUEO_DIVISA'
        evidence['issues'].append('Divisa de fuente oficial distinta de contabilidad');return Enrichment(a,q,evidence)
    intervals={}
    for doc in entry['documents']:
        if pd.Timestamp(doc['published'])>pd.Timestamp(as_of):continue
        source=doc['url']
        try:
            response=(requests_get or requests.get)(source,timeout=60);response.raise_for_status()
            digest=hashlib.sha256(response.content).hexdigest()
            evidence['documents'].append({'url':source,'published':doc['published'],'sha256':digest,'kind':doc['kind']})
            if doc['kind']=='inline_xbrl':
                facts=pure_da_facts(response.content.decode('utf-8'),currency=currency,entity_id=entry['entity_id'],source=source,published=doc['published'])
                if not facts:raise ValueError('Sin componentes D&A puros completos, consolidados y en divisa declarada')
                for key,value in facts.items():
                    if key not in intervals or value['published']>intervals[key]['published']:intervals[key]=value
            elif doc['kind']=='earnings_pdf':
                row,comparatives=earnings_pdf(response.content,doc,entry['entity_name'])
                end=pd.Timestamp(doc['period_end'])
                if end>pd.Timestamp(as_of):continue
                if end not in q.index:q.loc[end,:]=np.nan
                for field,value in row.items():
                    old=q.loc[end,field] if field in q else np.nan
                    q.loc[end,field]=value
                    evidence['changes'].append({'Campo':field,'Fin':str(end.date()),'Valor anterior':float(old) if pd.notna(old) else None,
                        'Valor oficial':value,'Moneda':currency,'Fuente':source,'Unidad':currency if field!='EPS diluido' else currency+'/acción'})
                # Identidades de extracción; no se hace pasar la caja IR por caja estricta.
                q.loc[end,'D&A']=row['D&A operativa']
                q.loc[end,'Definición D&A']='D&A operativa IR = EBITDA - EBIT; separada de D&A cash-flow'
                q.loc[end,'Deuda incluye arrendamientos']=False
                q.loc[end,'Origen deuda']='IR: interest-bearing debts, componentes préstamos/bonos; leases separados'
                q.loc[end,'Origen efectivo/inversiones']='IR: caja + instrumentos/inversiones a corto plazo; no caja estricta'
                q.loc[end,'Inicio periodo']=doc['period_start'];q.loc[end,'Tipo periodo']='3M'
                q.loc[end,'Fuente financiera']=source
                q.loc[end,'Estado fuente']='PRELIMINAR_NO_REVISADO'
                if not doc.get('complete_capex'):
                    q.loc[end,'CAPEX']=np.nan
                    q.attrs['invalid_flows']=sorted(set(q.attrs.get('invalid_flows',[]))|{'CAPEX'})
                    evidence['issues'].append('CAPEX total Q3 N/D: PDF solo revela PP&E; faltan adquisiciones de intangibles; no reemplazar por cero o FY')
                # El resto de trimestres Yahoo usa D&A de cash-flow; la D&A operativa IR tiene otra definición.
                q.attrs['invalid_flows']=sorted(set(q.attrs.get('invalid_flows',[]))|{'D&A'})
                evidence['issues'].append('D&A TTM para FCFF/EBITDA N/D: conciliar D&A operativa IR con la serie de cash-flow; no mezclar ambas definiciones')
                evidence['comparatives']=comparatives
        except Exception as exc:
            evidence['issues'].append(source+': '+type(exc).__name__+': '+str(exc)[:200])
    if not evidence['changes'] and not intervals:
        evidence['status']='PARCIAL' if evidence['issues'] else 'SIN_DATOS_UTILIZABLES'
        return Enrichment(a,q,evidence)
    # Solo se sustituyen componentes de D&A cuando hay evidencia completa.
    try:quarters=quarter_da(intervals)
    except ValueError as exc:quarters={};evidence['issues'].append(str(exc))
    for (start,end),record in intervals.items():
        days=(pd.Timestamp(end)-pd.Timestamp(start)).days+1
        year=pd.Timestamp(end).year
        if 330<=days<=400 and year in a.index and 'Fecha cierre fiscal' in a and pd.Timestamp(a.loc[year,'Fecha cierre fiscal'])==pd.Timestamp(end):
            _apply_da(a,year,record,start,end,currency,evidence)
    for (start,end),record in quarters.items():
        date=pd.Timestamp(end)
        if date in q.index:_apply_da(q,date,record,start,end,currency,evidence)
    for frame in [a,q]:
        if 'D&A' in frame and 'Beneficio operativo' in frame:frame['EBITDA aproximado']=frame['Beneficio operativo']+frame['D&A']
        if 'CAPEX' in frame and 'Flujo de caja operativo' in frame:frame['Flujo de caja libre']=frame['Flujo de caja operativo']-frame['CAPEX']
    evidence['status']='PARCIAL' if evidence['issues'] else 'CONTRASTADO'
    return Enrichment(a,q.sort_index(),evidence)


def _apply_da(frame,index,record,start,end,currency,evidence):
    original=frame.loc[index,'D&A']
    if 'D&A y otros' not in frame:frame['D&A y otros']=np.nan
    frame.loc[index,'D&A y otros']=original
    frame.loc[index,'D&A']=record['value']
    frame.loc[index,'Depreciación y amortización pura']=record['value']
    frame.loc[index,'Otros ajuste D&A']=original-record['value'] if pd.notna(original) else np.nan
    frame.loc[index,'Definición D&A']='D&A consolidada pura: depreciación PP&E + amortización intangibles'
    frame.loc[index,'Origen D&A']=record['source']+'; '+record['derivation']
    frame.loc[index,'D&A validada']=True
    evidence['changes'].append({'Campo':'D&A','Inicio':start,'Fin':end,'Valor anterior':float(original) if pd.notna(original) else None,
       'Valor oficial':record['value'],'Moneda':currency,'Fuente':record['source'],
       'Derivación':record['derivation'],'Componentes':record['components'],'Precisión':record['precision'],
       'Otros residual (no identificado)':original-record['value'] if pd.notna(original) else None})


def ttm_reconciliation(quarterly,annual,as_of,fiscal_end):
    """Cobertura de periodos y contraste FY por flujo; no cuenta ausencias como coincidencia."""
    from modelo_fundamental import quarterly_snapshot
    ttm,_,validated,notes=quarterly_snapshot(quarterly,annual,pd.Timestamp(as_of),fiscal_end)
    raw=quarterly.sort_index().tail(4) if quarterly is not None else pd.DataFrame()
    recent=validated.tail(4)
    rows=[]
    for metric in ['Ingresos','Beneficio operativo','Flujo de caja operativo','CAPEX','D&A','Flujo de caja libre','EBITDA aproximado']:
        count=int(pd.to_numeric(raw.get(metric,pd.Series(dtype=float)),errors='coerce').notna().sum())
        usable=int(pd.to_numeric(recent.get(metric,pd.Series(dtype=float)),errors='coerce').notna().sum())
        value=ttm.get(metric,np.nan)
        fy_status='N/D: sin cuatro trimestres FY completos'
        if len(annual) and not validated.empty and fiscal_end is not None and pd.notna(fiscal_end):
            end=pd.Timestamp(fiscal_end)
            matching=validated[(validated.index>end-pd.DateOffset(years=1))&(validated.index<=end)]
            if metric in annual and metric in matching and len(matching)==4 and matching[metric].notna().all():
                reference=annual.loc[annual.index.max(),metric]
                if pd.notna(reference):fy_status='CONCILIA' if np.isclose(matching[metric].sum(),reference,rtol=.009999,atol=1.) else 'DISCREPA'
        rows.append({'Campo':metric,'Periodo inicial':str((raw.index.min()-pd.DateOffset(months=3)+pd.Timedelta(days=1)).date()) if len(raw) else None,
            'Periodo final':str(raw.index.max().date()) if len(raw) else None,'Observaciones fuente':count,
            'Periodos utilizables':usable,'TTM (unidades)':value,'Estado':'COMPLETO' if pd.notna(value) else 'N/D',
            'Conciliación FY':fy_status,'Motivo':'Flujo invalidado por definición o integridad' if metric in validated.attrs.get('invalid_flows',[]) else ''})
    return pd.DataFrame(rows)
