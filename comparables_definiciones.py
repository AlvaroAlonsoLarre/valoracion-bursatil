"""Diagnóstico de homogeneidad por emisor y método, sin inferir GAAP/NTM.

forwardPE y enterpriseToEbitda son datos observados de proveedor. Su existencia
no acredita el periodo de los beneficios ni el perímetro de deuda. Este registro
expone qué evidencia falta, aunque la actividad económica sea comparable.
"""
import pandas as pd


def definition_coverage(peers):
    columns=['Ticker','Método','Periodo declarado','Base declarada','Perímetro declarado',
             'Fuente de definición','Fecha de definición','Requisitos pendientes','Definición completa']
    rows=[]
    if peers is None:return pd.DataFrame(columns=columns)
    for _,peer in peers.iterrows():
        for method in ['PER','EV/EBITDA']:
            period=peer.get(method+' periodo','No declarado')
            basis=peer.get('PER base','No declarado') if method=='PER' else 'EBITDA sin ajuste de perímetro inferido'
            perimeter=peer.get('Perímetro deuda','No declarado')
            source=peer.get(method+' fuente definición')
            date=peer.get(method+' fecha definición')
            missing=[]
            if period!='NTM':missing.append('periodo NTM documentado')
            if method=='PER' and basis!='GAAP':missing.append('beneficio GAAP documentado')
            if method=='EV/EBITDA' and perimeter!='Financiera sin leases':missing.append('deuda/EBITDA homogéneos sin leases')
            if not isinstance(source,str) or not source.strip():missing.append('fuente de la definición')
            if pd.isna(date) or not str(date or '').strip():missing.append('fecha de la definición')
            rows.append({'Ticker':peer['Ticker'],'Método':method,'Periodo declarado':period,'Base declarada':basis,
                'Perímetro declarado':perimeter,'Fuente de definición':source,'Fecha de definición':date,
                'Requisitos pendientes':'; '.join(missing),'Definición completa':not missing})
    return pd.DataFrame(rows,columns=columns)


def verified_coverage(peers,as_of,expected_basis=None):
    from multiple_evidence import validate_multiple
    rows=[]
    if peers is not None:
        for _,row in peers.iterrows():
            for method in ['PER','EV/EBITDA']:
                ok,value,issues,metadata=validate_multiple(row,method,as_of,expected_basis)
                rows.append({'Ticker':row['Ticker'],'Método':method,'Definición completa':ok,
                    'Múltiplo reconstruido':value,'Requisitos pendientes':'; '.join(issues),
                    'Base declarada':metadata.get('basis'),'Inicio NTM':metadata.get('start'),
                    'Fin NTM':metadata.get('end'),'Fuente de definición':metadata.get('source'),
                    'Fecha de definición':metadata.get('date')})
    return pd.DataFrame(rows,columns=['Ticker','Método','Definición completa','Múltiplo reconstruido',
        'Requisitos pendientes','Base declarada','Inicio NTM','Fin NTM','Fuente de definición','Fecha de definición'])
