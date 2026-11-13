"""Referencias nominales oficiales por moneda; diagnóstico sin recalibrar el WACC."""
import hashlib
import math
from datetime import datetime,timezone
import pandas as pd
import requests
from bs4 import BeautifulSoup


def treasury_10y(html,as_of):
    """Columna exacta 10 Yr, no 10 años reales ni tipos de letras a corto plazo."""
    today=pd.Timestamp(as_of).tz_localize(None).normalize();values=[]
    soup=BeautifulSoup(html,'html.parser')
    for table in soup.find_all('table'):
        headers=[h.get_text(' ',strip=True) for h in table.find_all('th')]
        if headers.count('Date')!=1 or headers.count('10 Yr')!=1:continue
        for row in table.find_all('tr'):
            cells=[c.get_text(' ',strip=True) for c in row.find_all('td')]
            if len(cells)!=len(headers):continue
            try:
                date=pd.to_datetime(cells[headers.index('Date')],format='%m/%d/%Y')
                rate=float(cells[headers.index('10 Yr')])/100
                if date<=today and math.isfinite(rate) and 0<rate<.30:values.append((date,rate))
            except (ValueError,TypeError):continue
    if not values:raise ValueError('No hay referencia nominal 10 Yr con fecha admisible')
    latest=max(date for date,_ in values);rates={v for d,v in values if d==latest}
    if len(rates)!=1:raise ValueError('Referencia 10 Yr ambigua para la misma fecha')
    if (today-latest).days>7:raise ValueError('Referencia 10 Yr caducada (>7 días)')
    return str(latest.date()),rates.pop()


def official_risk_reference(currency,as_of,requests_get=None):
    if currency.upper()!='USD':return [{'Moneda':currency,'Estado':'SIN_FUENTE_CONFIGURADA',
        'Detalle':'No usar Treasury USD para descontar otra moneda'}]
    today=pd.Timestamp(as_of);source='https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?field_tdr_date_value_month='+today.strftime('%Y%m')+'&type=daily_treasury_yield_curve'
    row={'Parámetro':'TIPO_LIBRE_RIESGO','Moneda':'USD','Fuente':source,'Estado':'NO_VERIFICADO',
         'Fecha consulta':datetime.now(timezone.utc).isoformat(),'Plazo':'10 años','Base':'Nominal par yield CMT, % anual / 100'}
    try:
        response=(requests_get or requests.get)(source,headers={'User-Agent':'StockValuationProject/1.0'},timeout=20)
        response.raise_for_status();date,value=treasury_10y(response.content,as_of)
        row.update({'Fecha fuente':date,'Valor observado':value,'SHA256 documento':hashlib.sha256(response.content).hexdigest(),
            'Estado':'REFERENCIA_OFICIAL','Detalle':'Referencia de contraste; no reemplaza automáticamente el supuesto ni acredita ERP, beta o coste de deuda'})
    except Exception as exc:row['Detalle']=type(exc).__name__+': '+str(exc)[:160]
    return [row]
