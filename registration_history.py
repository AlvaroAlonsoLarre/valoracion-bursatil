"""Estados anuales de registros de IPO sin CompanyFacts anual ni Inline XBRL.

Sólo tablas de estados consolidados con cabecera anual, escala expresa y años
únicos. Los conceptos son etiquetas de tabla, nunca hechos XBRL inventados.
"""
import hashlib
import re
import numpy as np
import pandas as pd
from lxml import html

LABELS={
 'Ingresos':r'revenue|revenues|total revenues',
 'Beneficio operativo':r'income \(loss\) from operations|operating income \(loss\)|operating income|operating loss',
 'Beneficio neto':r'net income \(loss\)|net income|net loss',
 'Beneficio neto común':r'net income \(loss\) attributable to shareholders - diluted',
 'Beneficio antes de impuestos':r'income \(loss\) before income taxes|income before income taxes|loss before income taxes',
 'Impuestos':r'provision for \(benefit from\) income taxes|income tax expense \(benefit\)|income tax expense',
 'Flujo de caja operativo':r'net cash provided by operating activities|net cash provided by \(used in\) operating activities',
 'CAPEX':r'purchases of property, plant, and equipment.*',
 'D&A':r'depreciation and amortization'}


def parse_registration(text,filing,currency='USD'):
    doc=html.fromstring(text);rows=[];source=[];full=' '.join(doc.text_content().split())
    gaap=bool(re.search(r'(generally accepted accounting principles|accounting principles generally accepted) in the United States|U\.S\. GAAP',full,re.I))
    for table in doc.xpath('//table'):
        content=' '.join(table.text_content().split())
        header_date=re.match(r'Year Ended ([A-Za-z]+) (\d{1,2}),',content)
        if not header_date or 'Three Months' in content[:180]:continue
        month,day=header_date.groups()
        # Escala y título pueden estar fuera de la tabla, en el encabezado de página.
        preceding=' '.join(table.xpath('preceding::text()')[-100:])[-3000:]
        if not re.search(r'CONSOLIDATED STATEMENTS OF (OPERATIONS|INCOME|CASH FLOWS)',preceding,re.I):continue
        unit_context=preceding+' '+content[:200]
        if not re.search(r'in millions',unit_context,re.I):continue
        if currency!='USD' or not re.search(r'(U\.S\.|United States|US) dollar|\(in millions',unit_context,re.I):continue
        matrix=[[' '.join(c.text_content().split()) for c in tr.xpath('./td|./th')] for tr in table.xpath('.//tr')]
        header=next((r for r in matrix if sum(bool(re.fullmatch(r'20\d\d',x)) for x in r)>=2),None)
        if header is None:continue
        indices=[i for i,x in enumerate(header) if re.fullmatch(r'20\d\d',x)];years=[int(header[i]) for i in indices]
        if len(set(years))!=len(years):continue
        section='';eps_seen=False
        for row in matrix:
            if len(row)<=max(indices) or not row:continue
            label=re.sub(r'\.{2,}','',row[0]).strip();lower=label.lower()
            if 'weighted average shares' in lower:section='shares'
            elif 'per share of common' in lower:section='eps'
            field=next((k for k,pattern in LABELS.items() if re.fullmatch(pattern,lower)),None)
            if lower=='diluted':field='Acciones diluidas medias' if section=='shares' else 'EPS diluido' if section=='eps' else None
            if field is None:continue
            for index,year in zip(indices,years):
                token=row[index].replace('$','').replace(',','').strip()
                if not re.fullmatch(r'\(?-?\d+(?:\.\d+)?\)?',token):continue
                value=float(token.strip('()'))*(-1 if token.startswith('(') else 1)
                if field!='EPS diluido':value*=1e6
                if field=='CAPEX':value=abs(value)
                rows.append((year,field,value))
                source.append({'Ejercicio':year,'Fecha cierre fiscal':str(pd.Timestamp(f'{month} {day}, {year}').date()),'Campo':field,'Valor original':value,
                    'Unidad':currency+'/shares' if field=='EPS diluido' else 'shares' if field=='Acciones diluidas medias' else currency,
                    'Concepto SEC':'Tabla: '+label,'Formulario':filing['form'],'Presentado':filing['filing_date'],
                    'Accession':filing['accession'],'Fuente':'Tabla consolidada registro SEC','URL':filing['url'],
                    'SHA256 documento':filing.get('document_sha256',hashlib.sha256(text.encode()).hexdigest()),'Escala explícita':'millones excepto EPS'})
    if not rows:return pd.DataFrame(),pd.DataFrame(),gaap
    data=pd.DataFrame(rows,columns=['Ejercicio','Campo','Valor'])
    # Duplicados con distinto valor no se resuelven eligiendo la cifra conveniente.
    bad=data.groupby(['Ejercicio','Campo'])['Valor'].nunique();bad=set(bad[bad>1].index)
    data=data[[ (y,f) not in bad for y,f in zip(data['Ejercicio'],data['Campo'])]]
    annual=data.pivot_table(index='Ejercicio',columns='Campo',values='Valor',aggfunc='first')
    dates={int(r['Ejercicio']):pd.Timestamp(r['Fecha cierre fiscal']) for r in source}
    annual['Fecha cierre fiscal']=[dates[y] for y in annual.index]
    for out,left,right in [('Flujo de caja libre','Flujo de caja operativo','CAPEX')]:
        if left in annual and right in annual:annual[out]=annual[left]-annual[right]
    for out,col in [('Margen operativo','Beneficio operativo'),('Margen neto','Beneficio neto')]:
        if col in annual and 'Ingresos' in annual:annual[out]=annual[col]/annual['Ingresos']
    if 'Impuestos' in annual and 'Beneficio antes de impuestos' in annual:annual['Tasa fiscal']=annual['Impuestos']/annual['Beneficio antes de impuestos']
    annual['EPS fuente presentado']=filing['filing_date'];annual['Acciones fuente presentado']=filing['filing_date']
    return annual,pd.DataFrame(source),gaap


def download_registration_history(submissions,cik,user_agent,currency,as_of):
    from sec_historical import _headers
    import requests
    recent=submissions.get('filings',{}).get('recent',{});observations=[]
    for i,form in enumerate(recent.get('form',[])):
        if form not in ('424B4','S-1/A','S-1','10-12B/A','10-12B'):continue
        filed=recent['filingDate'][i]
        if pd.Timestamp(filed)>as_of:continue
        accn=recent['accessionNumber'][i];document=recent['primaryDocument'][i]
        filing=dict(form=form,filing_date=filed,accession=accn,url=f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accn.replace('-','')}/{document}")
        try:
            response=requests.get(filing['url'],headers=_headers(user_agent),timeout=60);response.raise_for_status()
            filing['document_sha256']=hashlib.sha256(response.content).hexdigest()
            a,audit,gaap=parse_registration(response.text,filing,currency)
            observations.append({**filing,'Estado':'DISPONIBLE' if not a.empty else 'NO DISPONIBLE','SHA256':hashlib.sha256(response.content).hexdigest()})
            if not a.empty and 'Ingresos' in a and 'Beneficio neto' in a:
                return a,audit,{'CIK':cik,'Empresa SEC':submissions.get('name'),'Estado':'DISPONIBLE','Base contable':'US_GAAP' if gaap else 'UNKNOWN','Fuentes registro':observations,'Registro separación':form.startswith('10-12B')}
        except (requests.RequestException,ValueError) as exc:observations.append({**filing,'Estado':'NO DISPONIBLE','Detalle':str(exc)[:180]})
        # Un registro reciente incluye comparativas; máximo dos intentos.
        if len(observations)>=2:break
    return pd.DataFrame(),pd.DataFrame(),{'CIK':cik,'Estado':'Sin tabla anual de registro validada','Fuentes registro':observations}
