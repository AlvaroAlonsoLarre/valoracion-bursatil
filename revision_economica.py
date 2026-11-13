"""Revisión económica sin cotización como entrada: recurrencia, ciclo y PER.

Las cifras publicadas no se reescriben. Los filtros sólo califican su uso como
referencia económica; ningún umbral relaja la conciliación contable.
"""
import numpy as np
import pandas as pd
from historico_acciones import number

# Importes pretax, signos positivos = ganancias. Agregado FV-NI y su componente
# unrealized son alternativas, nunca se suman entre sí.
INVESTMENT_TAGS={
 'Ganancia FV inversiones':['EquitySecuritiesFvNiGainLoss','EquitySecuritiesFvNiUnrealizedGainLoss'],
 'Revalorizacion inversiones privadas':['EquitySecuritiesWithoutReadilyDeterminableFairValueUpwardPriceAdjustmentAnnualAmount'],
 'Deterioro inversiones privadas':['EquitySecuritiesWithoutReadilyDeterminableFairValueImpairmentLossAnnualAmount'],
 'Ganancias deuda realizadas':['DebtSecuritiesAvailableForSaleRealizedGain'],
 'Perdidas deuda realizadas':['DebtSecuritiesAvailableForSaleRealizedLoss'],
 'Intereses inversiones':['InvestmentIncomeInterest','InterestIncomeNonOperating','InterestIncomeOther']}


def numeric(a,key):return pd.to_numeric(a.get(key,pd.Series(index=a.index,dtype=float)),errors='coerce')


def is_cyclical(info):
    text=' '.join(str(info.get(k) or '') for k in ['industryKey','industry','longBusinessSummary']).lower()
    return any(w in text for w in ['semiconductor','oil','gas','automaker','steel','coal','flash memory','nand','dram'])


def cagr(a,window):
    s=numeric(a,'Ingresos').tail(window)
    if len(s)<2 or s.isna().any() or (s<=0).any():return np.nan
    span=int(s.index[-1])-int(s.index[0])
    if span<=0 or len(s)!=span+1:return np.nan
    return (s.iloc[-1]/s.iloc[0])**(1/span)-1


def changed_regime(a):
    margin=(numeric(a,'Beneficio operativo')/numeric(a,'Ingresos')).dropna()
    if len(margin)<6:return False
    old=number(margin.iloc[-6:-3].median());recent=number(margin.tail(3).median())
    return bool(old>0 and recent>0 and abs(recent-old)>=.05 and (recent/old>=2 or recent/old<=.5))


def investment_amounts(a):
    """Suma sólo partidas observadas; NaN si no se identificó ninguna.

    Es cobertura parcial, nunca afirmación de ausencia del resto de ajustes.
    Un deterioro se presenta como gasto positivo; se resta de las ganancias.
    """
    columns=[k for k in INVESTMENT_TAGS if k!='Intereses inversiones' and k in a]
    if not columns:return pd.Series(np.nan,index=a.index)
    values=pd.DataFrame({k:numeric(a,k)*(-1 if k in ['Deterioro inversiones privadas','Perdidas deuda realizadas'] else 1) for k in columns})
    return values.sum(axis=1,min_count=1)


def qualified_history(a,history,info,financial=False):
    result=history.copy()
    if result.empty:return result
    pt=numeric(a,'Beneficio antes de impuestos');tax=numeric(a,'Impuestos')/pt.where(pt>0)
    typical=number(tax[(tax>=0)&(tax<=.6)].tail(5).median())
    gains=investment_amounts(a);margin=numeric(a,'Beneficio neto')/numeric(a,'Ingresos')
    positive=margin[(margin>0)&np.isfinite(margin)].tail(10);normal=number(positive.median())
    regime=changed_regime(a);latest=int(a.index.max()) if len(a) else 0
    for index,row in result.iterrows():
        year=row['Ejercicio'];reasons=[]
        if year not in a.index or a.index.duplicated().any():reasons.append('Ejercicio ausente o duplicado')
        else:
            rate=number(tax.loc[year]);gain=number(gains.loc[year]);pretax=number(pt.loc[year]);m=number(margin.loc[year])
            if not financial and np.isfinite(gain) and abs(gain)>0 and abs(pretax)>0 and abs(gain/pretax)>.10:
                reasons.append('Ganancias/pérdidas financieras identificadas >10% del PBT; cobertura parcial')
            interest=number(net_interest(a).loc[year])
            nonop=pretax-number(numeric(a,'Beneficio operativo').loc[year])
            if not financial and np.isfinite(interest) and np.isfinite(nonop) and abs(pretax)>0 and abs((nonop-interest)/pretax)>.10:
                reasons.append('Otros no operativos >10% del PBT sin recurrencia acreditada')
            if pretax<=0 and number(numeric(a,'Beneficio neto').loc[year])>0:reasons.append('Beneficio positivo con PBT no positivo: revisar beneficio fiscal')
            if np.isfinite(rate) and (rate<0 or rate>.6 or (np.isfinite(typical) and abs(rate-typical)>.10)):
                reasons.append('Fiscalidad atípica: diferencia >10 pp o tasa no representativa')
            if not financial and is_cyclical(info) and len(positive)>=3 and normal>0 and np.isfinite(m) and (m<.5*normal or m>2*normal):
                reasons.append('Beneficio de pico/valle: margen neto fuera de 0,5–2× mediana positiva')
            if regime and year<latest-2:reasons.append('Régimen de margen distinto: cambio ≥2× y ≥5 pp; sólo últimos 3 FY')
        pe=number(row.get('PER histórico'))
        if not pe>0:reasons.append('EPS no positivo o base de acción/precio sin conciliar')
        result.loc[index,'PER admisible económicamente']=bool(not reasons)
        result.loc[index,'Motivo PER económico']='; '.join(reasons) or 'Sin distorsión material detectada; no prueba de ausencia de extraordinarios'
    return result


def net_interest(a):
    expense=numeric(a,'Gastos por intereses')
    if 'Concepto gasto intereses' in a:
        # El neto de gasto/ingreso no se vuelve a restar de un ingreso separado.
        expense=expense.mask(a['Concepto gasto intereses'].astype(str).str.contains('NetOfInterestIncome',case=False,regex=False))
    return numeric(a,'Intereses inversiones')-expense


def recurrent_financial(a,financial=False):
    reported=(numeric(a,'Beneficio antes de impuestos')-numeric(a,'Beneficio operativo'))/numeric(a,'Ingresos')
    gains=investment_amounts(a);pt=numeric(a,'Beneficio antes de impuestos')
    interest=net_interest(a)
    unexplained=(numeric(a,'Beneficio antes de impuestos')-numeric(a,'Beneficio operativo')-interest)/pt.abs().replace(0,np.nan)
    material=((gains.abs()/pt.abs().replace(0,np.nan)>.10)|unexplained.abs().gt(.10)).tail(5).any()
    if not financial and material:
        income=numeric(a,'Intereses inversiones');expense=numeric(a,'Gastos por intereses')
        values=(net_interest(a)/numeric(a,'Ingresos')).tail(5)
        if values.notna().sum()>=2:
            return number(values.median()),'Intereses de inversiones − gasto de intereses; otros no operativos no extrapolados sin evidencia de recurrencia'
        return np.nan,'Ganancias financieras materiales; falta puente de intereses recurrentes (≥2 FY). Requiere supuesto explícito'
    return number(reported.tail(5).median()),'Mediana PBT−EBIT / ventas; recurrencia no plenamente acreditada; revisar otros resultados'


def bridge(a):
    result=pd.DataFrame({'Ejercicio':a.index,'Ingresos':numeric(a,'Ingresos').values,
        'No operativo reportado':(numeric(a,'Beneficio antes de impuestos')-numeric(a,'Beneficio operativo')).values,
        'Ganancias inversiones identificadas':investment_amounts(a).values,
        'Intereses netos identificados':net_interest(a).values})
    result['Otros no operativos sin recurrencia acreditada']=result['No operativo reportado']-result['Intereses netos identificados']
    result['Nota']='Ajustes pretax; cobertura parcial. No atribuir impuesto ni EPS ajustado sin evidencia; estados reportados intactos'
    return result


def sensitivity(result,financial_currency,quote_currency):
    """Sensibilidad aislada: ±5 pp de crecimiento, ±3 pp de margen y ±20% PER.

    Recalcula el camino de ventas; los cambios de crecimiento/margen se aplican
    a ambos extremos. No cambia el precio observado ni recomienda parámetros.
    """
    rows=[];assumptions=result.assumptions
    if result.projected.empty or not result.summary['primary_available']:return pd.DataFrame()
    base=assumptions[assumptions['Escenario'].eq('Base')].set_index('Parámetro')['Valor'].to_dict()
    projected=result.projected[result.projected['Escenario'].eq('Base')].set_index('Año futuro')
    for h in [1,3]:
        for parameter,shifts in [('growth',[-.05,0,.05]),('margin',[-.03,0,.03]),('pe',[-.2,0,.2])]:
            for shift in shifts:
                values=dict(base);v=values[parameter]*(1+shift) if parameter=='pe' else values[parameter]+shift
                values[parameter]=v
                if parameter in ('growth','margin'):values[parameter+'_terminal']+=shift
                sales=result.summary['revenue_ttm']
                year=h+1 if result.valuation.iloc[0]['Periodo PER']=='NTM' else h
                for step in range(1,year+1):
                    w=min(1.,(step-1)/2);sales*=1+values['growth']+(values['growth_terminal']-values['growth'])*w
                margin=values['margin']+(values['margin_terminal']-values['margin'])*min(1.,(year-1)/2)
                pbt=sales*(margin+values['financial_sales'])
                original=projected.loc[year];original_after=original['PBT']-original['Impuestos']
                attribution=original['Beneficio común normalizado']/original_after if original_after else np.nan
                eps=(pbt-max(0.,pbt)*values['tax'])*attribution/original['Acciones diluidas']
                target=eps*values['pe']*result.summary['per_share_fx'] if eps>0 and number(values['pe'])>0 else np.nan
                rows.append({'Horizonte (años)':h,'Parámetro':parameter,'Cambio':shift,'Valor supuesto':v,
                    'Crecimiento año 1':values['growth'],'Crecimiento año 3':values['growth_terminal'],'Margen año 1':values['margin'],'Margen año 3':values['margin_terminal'],
                    'EPS aplicado':eps,'PER aplicado':values['pe'],'Precio sensibilidad':target,'Moneda':quote_currency,'Estado':'ESTIMADO' if target>0 else 'NO DISPONIBLE',
                    'Nota':'Variación aislada; no consenso ni ajuste a la cotización'})
    return pd.DataFrame(rows)


def implied_requirements(result):
    """Una incógnita cada vez, al precio observado, manteniendo las otras hipótesis.

    Es una identidad de contraste, no un nuevo pronóstico. El crecimiento uniforme
    implícito no sustituye al camino desacelerado del escenario.
    """
    rows=[]
    if result.projected.empty or not result.summary.get('quote_verified'):return pd.DataFrame()
    values=result.assumptions.query("Escenario=='Base'").set_index('Parámetro')['Valor'];quote=result.summary['price'];fx=result.summary['per_share_fx']
    p=result.projected.query("Escenario=='Base'").set_index('Año futuro')
    for _,v in result.valuation.query("Método=='EPS × PER' and Escenario=='Base'").iterrows():
        h=int(v['Horizonte (años)']);year=h+1 if v['Periodo PER']=='NTM' else h;r=p.loc[year];tax=values['tax'];pe=values['pe']
        eps=r['EPS financiero'];net=r['PBT']-r['Impuestos'];attribution=r['Beneficio común normalizado']/net if net else np.nan
        required_eps=quote/(pe*fx) if quote>0 and pe>0 and fx>0 else np.nan
        required_pbt=required_eps*r['Acciones diluidas']/((1-tax)*attribution) if (1-tax)*attribution>0 else np.nan
        pbt_margin=r['PBT']/r['Ingresos'] if r['Ingresos']>0 else np.nan
        sales=required_pbt/pbt_margin if pbt_margin>0 and required_pbt>0 else np.nan
        rows.append({'Horizonte (años)':h,'Año EPS':year,'Precio observado':quote,'Precio objetivo Base':v['Precio objetivo'],
            'Crecimiento uniforme implícito':(sales/result.summary['revenue_ttm'])**(1/year)-1 if sales>0 else np.nan,
            'Margen implícito':required_pbt/r['Ingresos']-values['financial_sales'] if r['Ingresos']>0 else np.nan,
            'PER implícito':quote/(eps*fx) if eps>0 and fx>0 else np.nan,'PER supuesto':pe,
            'Nota':'Cada incógnita por separado, resto Base fijo; sin descuento/dividendos. No es objetivo ni optimización'})
    return pd.DataFrame(rows)


def official_investment_notes(filing,currency,user_agent,requests_get=None):
    """Desglose oficial trazable; no se suman periodos YTD con trimestres.

    Nombres locales documentados, independientes del prefijo del emisor. Los
    importes son evidencia pretax; no producen un EPS ajustado ficticio.
    """
    import requests,hashlib,re
    from sec_historical import parse_inline_xbrl
    url=filing.get('url','')
    if not re.match(r'^https://www\.sec\.gov/Archives/edgar/data/\d+/\d+/[^/]+$',url):raise ValueError('URL filing no oficial')
    response=(requests_get or requests.get)(url,headers={'User-Agent':user_agent},timeout=45);response.raise_for_status()
    fingerprint=hashlib.sha256(response.content).hexdigest()
    records=parse_inline_xbrl(response.text,filing);allowed={name for group in INVESTMENT_TAGS.values() for name in group}
    allowed.add('DebtSecuritiesAvailableForSaleReclassificationAdjustmentFromAOCI')
    rows=[]
    for r in records:
        name=r['name'].split(':')[-1]
        if name not in allowed or not r.get('start') or not r.get('end'):continue
        if currency.lower() not in r['unitref'].lower():continue
        if pd.Timestamp(r['end'])>pd.Timestamp(filing['report_date']):continue
        rows.append({'Concepto':r['name'],'Perímetro':'Consolidado' if not r['dimensions'] else ', '.join(r.get('members',[])) or 'Dimensional',
            'Escala XBRL':int(r.get('scale') or 0),'Inicio':r['start'],'Fin':r['end'],'Duración días':r['days'],
            'Importe pretax':r['value'],'Unidad':currency,'URL':url,'SHA256 documento':fingerprint,'Presentado':filing['filing_date'],
            'Nota':'No sumar periodos superpuestos; total emisor, no atribución a una participada concreta'})
    if not rows:return pd.DataFrame()
    return pd.DataFrame(rows).sort_values('Escala XBRL').drop_duplicates(['Concepto','Perímetro','Inicio','Fin'],keep='first')
