"""Sensibilidad reproducible y validación de supuestos, sin elegir un precio deseado."""
import numpy as np
import pandas as pd

SHOCKS=[('Base',{}),('WACC -1 pp',{'wacc':-.01}),('WACC +1 pp',{'wacc':.01}),
        ('CAPEX/ventas -1 pp',{'capex_sales':-.01}),('CAPEX/ventas +1 pp',{'capex_sales':.01}),
        ('D&A/ventas -1 pp',{'da_sales':-.01}),('D&A/ventas +1 pp',{'da_sales':.01}),
        ('g terminal -0.5 pp',{'terminal_growth':-.005}),('g terminal +0.5 pp',{'terminal_growth':.005})]


def audit_dcf(annual,peers,kwargs,baseline=None):
    from modelo_fundamental import build_fundamental_model
    arguments=dict(kwargs);arguments.pop('sensitivity_shocks',None)
    base=baseline or build_fundamental_model(annual,peers,**arguments)
    rows=[]
    for label,shocks in SHOCKS:
        result=base if not shocks else build_fundamental_model(annual,peers,**arguments,sensitivity_shocks=shocks)
        values=result.valuation
        for horizon in [0,1,3]:
            match=values[(values['Escenario']=='Base')&(values['Horizonte (años)']==horizon)&values['Método'].str.contains('DCF')] if len(values) else pd.DataFrame()
            row=match.iloc[0] if len(match) else {}
            value=row.get('Precio objetivo (divisa cotización)',np.nan)
            rows.append({'Experimento':label,'Horizonte (años)':horizon,'Precio condicional':value,
                'Moneda':kwargs['quote_currency'],'Estado':'CONDICIONAL' if pd.notna(value) else 'BLOQUEO/N-D',
                'WACC (%)':row.get('WACC (%)'),'g (%)':row.get('G terminal (%)'),
                'ROIC terminal implícito (%)':row.get('ROIC terminal implícito (%)'),
                'Peso terminal (%)':row.get('Peso terminal EV (%)'),
                'Shocks':str(shocks),'Alcance':'Recalcula trayectoria, reinversión, caja y DCF; Kd, payout y datos fuente fijos; no es probabilidad'})
    validation=[]
    for _,row in base.risk_parameters.iterrows():
        validation.append({'Comprobación':row['Parámetro'],'Valor':row['Valor'],'Estado':row['Estado'],
            'Evidencia/limitación':str(row['Fuente'])+'; fecha '+str(row['Fecha fuente'])+'; '+str(row['Moneda'])})
    if not base.valuation.empty:
        valuations=base.valuation[(base.valuation['Escenario']=='Base')&base.valuation['Método'].str.contains('DCF')]
        for _,row in valuations.iterrows():
            roc=row.get('ROIC terminal implícito (%)',np.nan);wacc=row.get('WACC (%)',np.nan)
            validation.append({'Comprobación':f'ROIC terminal vs WACC h={row["Horizonte (años)"]}',
                'Valor':roc-wacc if pd.notna(roc) and pd.notna(wacc) else np.nan,
                'Estado':'REVISAR' if pd.notna(roc) and roc<wacc else 'NO_VERIFICADO',
                'Evidencia/limitación':'Diferencial en pp. Crecimiento con ROIC marginal inferior al WACC no acredita creación de valor; no se cambia CAPEX para corregirlo'})
            validation.append({'Comprobación':f'Concentración terminal h={row["Horizonte (años)"]}',
                'Valor':row.get('Peso terminal EV (%)'),'Estado':'DESCRIPTIVO',
                'Evidencia/limitación':'Porcentaje del EV sustentado por Gordon; no es validación económica del terminal'})
    for name,note in [('Reinversión y D&A','Ratios sobre ventas; sin calendario de activos/mantenimiento/expansión verificado'),
       ('Capital circulante','Supuesto sobre incremento de ingresos; no calendario de cobros/pagos verificado'),
       ('Leases y caja','Convención declarada; calendario integral de pagos, activos y caja distribuible pendiente'),
       ('Acciones y payouts','Acciones constantes salvo calendario documentado; recompra estimada no prueba cancelación')]:
        validation.append({'Comprobación':name,'Valor':np.nan,'Estado':'NO_VERIFICADO','Evidencia/limitación':note})
    return pd.DataFrame(rows),pd.DataFrame(validation)
