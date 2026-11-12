"""Cinco estados públicos; la severidad y la interpretación permanecen separadas."""
import numpy as np
import pandas as pd
from historico_acciones import number

STATES={'DISPONIBLE','ESTIMADO','ADVERTENCIA','NO DISPONIBLE','BLOQUEADO'}
LEGACY={'OK':'DISPONIBLE','INFO':'DISPONIBLE','CONDICIONAL':'ESTIMADO','BLOQUEO':'BLOQUEADO',
        'ERROR':'BLOQUEADO','REVISAR':'ADVERTENCIA','NO_REPRESENTATIVO':'NO DISPONIBLE',
        'NO_EJECUTADO':'NO DISPONIBLE','SOLICITADO':'NO DISPONIBLE'}


def public_states(frame):
    result=frame.copy()
    for col in ['Estado','validation_state','Estado validación']:
        if col in result:result[col]=result[col].map(lambda v:LEGACY.get(v,v))
    return result


def metric_coverage(ttm,annual,summary,invalid=()):
    """Disponibilidad por dependencias, sin propagar CAPEX a EPS ni ROIC a ingresos."""
    rows=[]
    def add(name,value,detail='',dependencies=(),warning=False):
        blocked=bool(set(dependencies)&set(invalid))
        state='BLOQUEADO' if blocked else 'ADVERTENCIA' if np.isfinite(number(value)) and warning else 'DISPONIBLE' if np.isfinite(number(value)) else 'NO DISPONIBLE'
        rows.append({'Indicador':name,'Valor':number(value) if not blocked else np.nan,'Estado':state,
                     'Periodo':'TTM' if name not in ['Acciones diluidas','Deuda','Efectivo','ROIC'] else 'Último cierre / FY indicado',
                     'Motivo':detail or ('Datos completos' if state=='DISPONIBLE' else 'Falta cobertura de los componentes: '+', '.join(dependencies))})
    for name,key in [('Ingresos','Ingresos'),('EBIT','Beneficio operativo'),('Beneficio neto','Beneficio neto'),('EPS diluido','EPS diluido'),('OCF','Flujo de caja operativo'),('CAPEX','CAPEX'),('FCF','Flujo de caja libre')]:
        deps=('Flujo de caja operativo','CAPEX') if name=='FCF' else (key,)
        add(name,ttm.get(key),dependencies=deps)
    add('Acciones diluidas',summary['diluted_base'],summary['diluted_source'],('Acciones diluidas medias',))
    add('Deuda',ttm.get('Deuda total reciente'),'Balance observado; no sumar flujos',('Deuda total',))
    add('Efectivo',ttm.get('Efectivo reciente'),'Balance observado; no sumar flujos',('Efectivo',))
    roic=number(annual.iloc[-1].get('ROIC')) if len(annual) else np.nan
    add('ROIC',roic,'ROIC FY aproximado sobre capital al cierre; no es ROIC TTM sobre capital medio',('NOPAT','Capital invertido'),True)
    eps=number(ttm.get('EPS diluido'));factor=number(summary.get('per_share_fx'))
    pe=summary['price']/(eps*factor) if eps>0 and factor>0 and summary['quote_verified'] else np.nan
    add('PER TTM',pe,'Precio de esta clase / EPS TTM diluido positivo; no forward',('EPS diluido',))
    # No llamar EBITDA puro a EBIT + una D&A no acreditada como consolidada.
    add('EV/EBITDA',np.nan,'Requiere D&A consolidada pura y puente EV del mismo perímetro; ver método opcional',('D&A consolidada','EV'))
    return pd.DataFrame(rows)
