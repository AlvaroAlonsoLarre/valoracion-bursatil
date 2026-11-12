"""Reconstrucción de múltiplos desde evidencia inmutable, sin inferir NTM/GAAP.

El modelo puede reproducir esta comprobación offline. Un cambio de etiquetas en
una fila no crea evidencia: se verifican el payload, su hash, emisor, fechas,
divisas, base por acción, marco contable, EBITDA y puente EV-equity.
"""
from __future__ import annotations
import hashlib
import json
import math
import re
from datetime import datetime,timezone
import pandas as pd


def digest(payload):
    return hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def _finite(value,positive=False):
    try:
        if isinstance(value,bool):raise ValueError()
        n=float(value)
        if not math.isfinite(n) or (positive and n<=0):raise ValueError()
        return n
    except (TypeError,ValueError):raise ValueError('Importe ausente/no finito o no positivo')


def _day(value):
    if value is None or not isinstance(value,(str,pd.Timestamp)) or not str(value).strip():raise ValueError('Fecha ausente')
    result=pd.Timestamp(value)
    if pd.isna(result):raise ValueError('Fecha no válida')
    if result.tzinfo:result=result.tz_localize(None)
    return result.normalize()


def validate_multiple(row,method,as_of,expected_basis=None):
    errors=[];normalized={}
    try:
        evidence=row.get('Evidencia múltiplos')
        if not isinstance(evidence,dict) or evidence.get('schema')!='multiple-evidence-v1':raise ValueError('Falta evidencia estructurada')
        payload=evidence['payload']
        if not isinstance(payload,dict):raise ValueError('Payload no estructurado')
        if digest(payload)!=evidence.get('sha256'):raise ValueError('Hash de evidencia no coincide')
        if not re.match(r'^https://[^/]+/.+',str(evidence.get('source_url',''))):raise ValueError('Falta URL HTTPS de origen')
        today=_day(as_of)
        acquired=_day(evidence['retrieved_at'])
        if acquired>today:raise ValueError('Evidencia obtenida después de la valoración')
        issuer=str(row.get('Emisor id') or row['Ticker']).upper()
        if str(payload.get('issuer_id','')).upper()!=issuer:raise ValueError('Emisor de la evidencia distinto')
        market=payload['market']; forecast=payload['forecasts'][method]
        quoted=_day(market['date'])
        if quoted>today or (today-quoted).days>7:raise ValueError('Precio futuro o fuera de vigencia')
        start=_day(forecast['start']);end=_day(forecast['end'])
        estimate_date=_day(forecast['date'])
        if estimate_date>today or (today-estimate_date).days>30:raise ValueError('Forecast futuro o sin vigencia')
        # Un FY1 no se transforma en NTM por renombrarlo: ventana exacta desde la valoración.
        if forecast.get('period')!='NTM' or start!=today+pd.Timedelta(days=1) or end!=today+pd.DateOffset(years=1):
            raise ValueError('Ventana de beneficios no es el NTM requerido')
        basis=forecast.get('accounting_basis')
        if expected_basis not in ('US_GAAP','IFRS','K_IFRS','GAAP') or basis!=expected_basis:
            raise ValueError('Base contable no declarada, ajustada o incompatible')
        if not re.match(r'^https://[^/]+/.+',str(forecast.get('definition_source',''))):raise ValueError('Sin documentación de la definición')
        if forecast.get('consolidation_perimeter')!='consolidated':raise ValueError('Forecast sin perímetro consolidado documentado')
        if forecast.get('share_basis')!='ordinary' or market.get('share_basis')!='ordinary':
            raise ValueError('Base acción/ADR sin reconciliar')
        fin_currency=forecast['currency'];quote_currency=market['currency']
        if not fin_currency or not quote_currency:raise ValueError('Divisas ausentes')
        fx=1.
        if fin_currency!=quote_currency:
            forex=payload['fx'];fx=_finite(forex['value'],True)
            if (forex.get('from'),forex.get('to'))!=(fin_currency,quote_currency):raise ValueError('FX con par incompatible')
            date=_day(forex['date'])
            if date>today or (today-date).days>7 or not forex.get('source'):raise ValueError('FX sin vigencia/procedencia')
        px=_finite(market['price'],True);shares=_finite(market['shares'],True);cap=_finite(market['market_cap'],True)
        if abs(px*shares/cap-1)>=.01:raise ValueError('Capitalización no concilia con precio × acciones')
        if method=='PER':
            if forecast.get('eps_definition')!='diluted_common_eps':raise ValueError('EPS sin base diluida común documentada')
            value=px/(_finite(forecast['eps'],True)*fx)
        elif method=='EV/EBITDA':
            balance=payload['balance'];date=_day(balance['date'])
            if date>today or (today-date).days>400:raise ValueError('Balance futuro o fuera de vigencia')
            if balance['currency']!=fin_currency:raise ValueError('Deuda/caja y EBITDA en monedas incompatibles')
            if balance.get('debt_perimeter')!='financial_ex_leases' or balance.get('cash_perimeter')!='cash_and_liquid_investments':
                raise ValueError('Deuda o caja con perímetro no homogéneo')
            if forecast.get('lease_perimeter')!='financial_ex_leases' or forecast.get('da_definition')!='pure_operating_da':
                raise ValueError('EBITDA/D&A/leases sin definición compatible')
            if balance.get('consolidation_perimeter')!='consolidated':raise ValueError('Balance sin perímetro consolidado documentado')
            # El modelo objetivo aplica EV = capitalización + deuda financiera - caja.
            # Un peer con minoritarios/preferentes necesita otro puente; no se omiten.
            if _finite(balance['noncontrolling_interests'])!=0 or _finite(balance['preferred_equity'])!=0:
                raise ValueError('Minoritarios/preferentes requieren puente EV compatible')
            debt=_finite(balance['financial_debt']);cash=_finite(balance['cash'])
            if min(debt,cash)<0 or not re.match(r'^https://[^/]+/.+',str(balance.get('definition_source',''))):raise ValueError('Deuda/caja no documentadas')
            ebitda=_finite(forecast['ebitda'],True);ebit=_finite(forecast['ebit']);da=_finite(forecast['da'])
            if da<0 or abs((ebit+da)/ebitda-1)>=.01:raise ValueError('EBITDA no concilia con EBIT + D&A pura')
            value=(cap+(debt-cash)*fx)/(ebitda*fx)
        else:raise ValueError('Método no admitido')
        if not math.isfinite(value) or value<=0:raise ValueError('Múltiplo no positivo')
        observed=row.get('PER forward' if method=='PER' else 'EV/EBITDA')
        if observed is not None and pd.notna(observed) and abs(float(observed)/value-1)>=.01:
            raise ValueError('Ratio observado y reconstruido difieren >=1%')
        normalized={'basis':basis,'start':str(start.date()),'end':str(end.date()),'debt_perimeter':
            'financial_ex_leases' if method=='EV/EBITDA' else 'equity','source':evidence['source_url'],'date':str(quoted.date())}
        return True,value,[],normalized
    except (KeyError,TypeError,ValueError,OverflowError,ZeroDivisionError) as exc:
        errors.append('Falta campo documental: '+str(exc) if isinstance(exc,KeyError) else str(exc))
        return False,float('nan'),errors,normalized


def attach_observed_evidence(peers,yf,as_of,limit=10):
    """Captura automática del SDK para candidatos relevantes, sin asumir definiciones.

    Yahoo publica forecasts FY0/FY1 y EBITDA de proveedor. Si no documenta la
    base GAAP/NTM/leases, el payload conserva UNKNOWN y NO habilita objetivos.
    """
    if peers is None or peers.empty:return peers,[]
    output=peers.copy();records=[]
    if 'Evidencia múltiplos' not in output:output['Evidencia múltiplos']=None
    candidates=output.sort_values('Prioridad origen',kind='stable') if 'Prioridad origen' in output else output
    for index,row in candidates.head(limit).iterrows():
        if isinstance(row.get('Evidencia múltiplos'),dict):continue
        ticker=str(row['Ticker']);record={'Ticker':ticker,'Estado':'NO_VERIFICADO','Fecha consulta':datetime.now(timezone.utc).isoformat()}
        try:
            obj=yf.Ticker(ticker); estimates=obj.get_earnings_estimate(as_dict=True) or {}
            from auditoria_io import clean
            estimates=clean(estimates)
            payload={'issuer_id':str(row.get('Emisor id') or ticker),'vendor_earnings_estimates':estimates,
                'observed_forward_pe':clean(row.get('PER forward')),'observed_enterprise_to_ebitda':clean(row.get('EV/EBITDA')),
                'market':{'date':clean(row.get('Fecha cotización')),'price':clean(row.get('Precio actual')),
                    'currency':row.get('Divisa cotización'),'share_basis':'UNKNOWN'},
                'forecasts':{'PER':{'period':'FY0/FY1 proveedor; no NTM documentado','accounting_basis':'UNKNOWN'},
                             'EV/EBITDA':{'period':'LTM proveedor; no NTM documentado','accounting_basis':'UNKNOWN'}}}
            source='https://query2.finance.yahoo.com/v10/finance/quoteSummary/'+ticker+'?modules=earningsTrend'
            output.at[index,'Evidencia múltiplos']={'schema':'multiple-evidence-v1','payload':payload,'sha256':digest(payload),
                 'source_url':source,'retrieved_at':record['Fecha consulta'],'hash_kind':'SDK result canonical JSON'}
            # El SDK puede devolver columnas -> periodos o periodos -> columnas.
            periods=sorted({str(k) for k in estimates if re.fullmatch(r'[+\-]?\d+[yq]',str(k))} |
                {str(k) for v in estimates.values() if isinstance(v,dict) for k in v if re.fullmatch(r'[+\-]?\d+[yq]',str(k))})
            def reported(metric,period):
                column=estimates.get(metric,{})
                if isinstance(column,dict) and period in column:return column[period]
                item=estimates.get(period,{})
                return item.get(metric) if isinstance(item,dict) else None
            methods=sorted({str(reported('methodology',period)) for period in periods if reported('methodology',period) is not None})
            record.update({'Fuente':source,'SHA256 payload':digest(payload),'Periodos devueltos':','.join(periods),
                'EPS FY0 proveedor':reported('avg','0y'),'EPS FY1 proveedor':reported('avg','+1y'),
                'Metodología publicada':','.join(methods) or 'No declarada',
                'Motivo':'No acredita GAAP/NTM; no inferir EBITDA forward ni perímetro de deuda'})
        except Exception as exc:record['Motivo']=type(exc).__name__+': '+str(exc)[:160]
        records.append(record)
    return output,records
