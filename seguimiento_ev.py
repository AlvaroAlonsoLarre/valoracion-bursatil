"""EV observado/informativo: fórmula V7, periodos y limitaciones explícitos."""
import numpy as np
import pandas as pd
from auditoria_io import clean,restore_frame
from historico_acciones import number,historical_multiples,enterprise_multiple
from analisis_acciones import needs_adr_bridge,sector_type


def _instant_shares(facts,date,as_of):
    rows=(facts or {}).get('facts',{}).get('us-gaap',{}).get('CommonStockSharesOutstanding',{}).get('units',{}).get('shares',[])
    valid=[r for r in rows if r.get('end')==str(date.date()) and not r.get('start') and r.get('filed') and pd.Timestamp(r['filed'])<=as_of and number(r.get('val'))>0]
    if not valid:return None
    latest=max(r['filed'] for r in valid);latest_rows=[r for r in valid if r['filed']==latest]
    if len({number(r['val']) for r in latest_rows})!=1:return None
    return latest_rows[0]


def fiscal_history(payload,annual=None,facts=None):
    # Guardar el subconjunto SEC usado permite reproducir el mismo FY al
    # importar una captura o editar hipótesis, sin volver a consultar la red.
    if facts is None:facts=payload.get('evidence',{}).get('watch_fy_shares')
    a=restore_frame(payload['frames']['annual']) if annual is None else annual
    k=payload['kwargs'];info=k.get('info') or {};day=pd.Timestamp(k['as_of']).normalize()
    prices=restore_frame(payload['historical']['Precios y splits']) if payload.get('historical',{}).get('Precios y splits') else pd.DataFrame()
    adr=needs_adr_bridge(info,k['financial_currency'],k['quote_currency']);kind=sector_type(info)
    h=historical_multiples(a,prices,k['financial_currency'],k['quote_currency'],day,is_adr=adr) if len(a) else pd.DataFrame()
    last=int(a.index.max()) if len(a) else 0;out=[]
    fc,qc=k['financial_currency'],k['quote_currency']
    expected_cik=info.get('valuation_cik') or (a['CIK SEC'].dropna().iloc[-1] if 'CIK SEC' in a and a['CIK SEC'].notna().any() else None)
    if facts and (not expected_cik or str(facts.get('cik','')).lstrip('0')!=str(expected_cik).split('.')[0].lstrip('0')):
        raise ValueError('CIK de acciones instantáneas distinto o identidad no acreditada')
    unit_fx=1. if fc==qc else 100. if fc=='GBP' and qc in ('GBp','GBX','GBPENCE') else .01 if fc in ('GBp','GBX','GBPENCE') and qc=='GBP' else np.nan
    for year,row in a.sort_index().iterrows():
        if int(year)<last-4:continue
        date=pd.to_datetime(row.get('Fecha cierre fiscal'),errors='coerce');warnings=[];blocked=[]
        rec={'Ejercicio':int(year),'Fecha cierre fiscal':date,'Periodo':'FY','Moneda financiera':fc,'Moneda precio':qc,'EV/EBITDA':np.nan}
        if pd.isna(date) or date>day:blocked.append('Fecha fiscal ausente/futura')
        ref=h[h['Ejercicio'].eq(year)].iloc[0] if len(h) and h['Ejercicio'].eq(year).any() else {}
        px=number(ref.get('Precio cierre fiscal'));shares=number(row.get('Acciones diluidas medias'));factor=number(ref.get('Factor split acciones'))
        share_source='Media diluida FY: aproximación a acciones al cierre';share_filed=row.get('Acciones fuente presentado')
        if kind!='OPERATIVA':blocked.append('EV/EBITDA genérico no aplicable a financiera/REIT')
        if adr:blocked.append('ADR: falta puente histórico de acciones ordinarias por título')
        if not np.isfinite(unit_fx):blocked.append('Falta FX histórico; no se aplica FX de hoy al FY')
        if not px>0:blocked.append('Sin cierre observado dentro de siete días del FY')
        splits=prices.get('Stock Splits',pd.Series(dtype=float)).copy()
        if len(splits):splits.index=pd.to_datetime(splits.index).tz_localize(None);splits=splits[(splits>0)&(splits!=1)&(splits.index<=day)]
        instant=_instant_shares(facts,date,day) if pd.notna(date) else None
        if instant:
            shares=number(instant['val']);share_filed=instant['filed'];factor=float(splits[splits.index>pd.Timestamp(share_filed)].prod()) if 'Stock Splits' in prices else np.nan
            share_source='CommonStockSharesOutstanding al cierre SEC · '+str(instant.get('accn',''))
        else:warnings.append('Acciones medias diluidas FY, no acciones exactas al cierre')
        if not (shares>0 and np.isfinite(factor) and factor>0):blocked.append('Base de acciones/splits no acreditada')
        if not instant and not bool(ref.get('Base acción conciliada',False)):blocked.append('EPS × acciones no concilia; no se supone un split')
        if number(info.get('impliedSharesOutstanding'))>0 and number(info.get('sharesOutstanding'))>0 and abs(info['impliedSharesOutstanding']/info['sharesOutstanding']-1)>.1:
            blocked.append('Clases múltiples: precio de clase y capitalización consolidada sin puente')
        debt=number(row.get('Deuda total'));cash=number(row.get('Efectivo'));operating=number(row.get('Beneficio operativo'))
        da=number(row.get('Depreciación y amortización pura'));flag=row.get('D&A validada');pure=np.isfinite(da) and isinstance(flag,(bool,np.bool_)) and bool(flag)
        if not pure:da=number(row.get('D&A'))
        definition=str(row.get('Definición D&A','No especificada'))
        if not pure and ('otros' in definition.lower() or not np.isfinite(da)):blocked.append('D&A mezcla otros ajustes o no está disponible')
        elif not pure:warnings.append('D&A reportada: definición consolidada no completamente reconciliada')
        debt_source=str(row.get('Origen deuda','Definición no detallada'))
        if 'parcial' in debt_source.lower() or 'solo ' in debt_source.lower():warnings.append('Deuda posiblemente parcial: EV puede estar infravalorado')
        if not (np.isfinite(debt) and debt>=0):blocked.append('Deuda financiera FY no disponible; ausencia no equivale a cero')
        if not (np.isfinite(cash) and cash>=0):blocked.append('Efectivo y equivalentes FY no disponible; no se sustituye por inversiones')
        leases=row.get('Deuda incluye arrendamientos');known_lease=isinstance(leases,(bool,np.bool_))
        perimeter='Incluye arrendamientos' if known_lease and leases else 'Excluye arrendamientos' if known_lease else 'Perímetro arrendamientos desconocido'
        warnings.append(perimeter+'; EBITDA sin ajuste uniforme de rentas/leases')
        ebitda=operating+da
        if not ebitda>0:blocked.append('EBITDA FY no positivo/incompleto')
        cap=px*shares*factor if px>0 and shares>0 and np.isfinite(factor) else np.nan
        ev,ratio=enterprise_multiple(cap,(debt-cash)*unit_fx,ebitda*unit_fx)
        contrasted=bool(instant and pure and known_lease and 'parcial' not in debt_source.lower() and 'solo ' not in debt_source.lower())
        rec.update({'Precio FY':px,'Acciones base cotización':shares*factor,'Origen acciones':share_source,'Acciones presentado':share_filed,'Factor split':factor,
                    'Capitalización histórica':cap,'Deuda financiera FY':debt,'Efectivo y equivalentes FY':cash,'Origen deuda':debt_source,'Perímetro leases':perimeter,
                    'EBIT FY':operating,'D&A FY':da,'Definición D&A':definition,'EBITDA FY':ebitda,'EV calculado':ev,'EV/EBITDA':ratio if not blocked and ev>0 else np.nan,
                    'Tipo':('Calculado y contrastado · no auditado' if contrasted else 'Histórico aproximado') if not blocked else 'No disponible','Confianza':'Media' if contrasted and not blocked else 'Baja','Validación':'No auditado: componentes FY contrastables, con aproximaciones explícitas',
                    'Advertencias':'; '.join(blocked+warnings)})
        out.append(rec)
    d=pd.DataFrame(out);valid=d[pd.to_numeric(d['EV/EBITDA'],errors='coerce').gt(0)] if len(d) else d
    latest=d[d['Ejercicio'].eq(last)] if len(d) else d
    # No mezclar en la mediana FY convenciones de deuda incl/excl arrendamientos.
    if len(latest):valid=valid[valid['Perímetro leases'].eq(latest.iloc[0]['Perímetro leases'])]
    return clean({'last':number(latest.iloc[0]['EV/EBITDA']) if len(latest) else None,'last_type':latest.iloc[0]['Tipo'] if len(latest) else 'No disponible','last_confidence':latest.iloc[0]['Confianza'] if len(latest) else 'Baja',
                  'median':valid['EV/EBITDA'].median() if len(valid) else None,'n':len(valid),'period':'FY',
                  'warning':f'Histórico aproximado, confianza Baja; cobertura {len(valid)}/5 FY de un mismo perímetro de leases. No se usa en precios objetivo.',
                  'rows':d.to_dict('records')})


def yahoo_ratio(info,as_of):
    value=number((info or {}).get('enterpriseToEbitda'))
    end=pd.to_datetime((info or {}).get('mostRecentQuarter'),unit='s',utc=True,errors='coerce')
    return clean({'value':value if value>0 else None,'period':'TTM/LTM proveedor; cierre '+str(end.date()) if pd.notna(end) else 'Periodo no informado por proveedor',
                  'source':'Yahoo enterpriseToEbitda','captured_at':str(as_of),'confidence':'Proveedor, no reconciliado','warning':'No es FY auditado ni una referencia NTM validada'})
