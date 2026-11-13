"""Evidencia financiera sintética explícita; no son forecasts ni fuentes reales."""
import math
import pandas as pd
from multiple_evidence import digest


def with_evidence(peers,as_of='2026-10-27',basis=None):
    peers=peers.copy()
    def number(value,default):
        try:return float(value) if math.isfinite(float(value)) else default
        except (TypeError,ValueError):return default
    docs=[]
    day=pd.Timestamp(as_of).normalize()
    for _,row in peers.iterrows():
        px=number(row.get('Precio actual'),100.)
        cap=number(row.get('Capitalización (miles de millones)'),.000001)*1e9
        pe=number(row.get('PER forward'),10.);ev=number(row.get('EV/EBITDA'),8.)
        ccy=row.get('Divisa cotización') or 'USD';fin=ccy
        standard=basis or row.get('PER base') or 'GAAP'
        horizon={'start':str((day+pd.Timedelta(days=1)).date()),'end':str((day+pd.DateOffset(years=1)).date()),
                 'date':str(day.date()),'eps_definition':'diluted_common_eps','currency':fin,'accounting_basis':standard,'definition_source':'https://example.invalid/synthetic/definitions','share_basis':'ordinary','consolidation_perimeter':'consolidated'}
        ebitda=cap/ev if ev else float('nan')
        payload={'issuer_id':str(row.get('Emisor id') or row['Ticker']),
            'market':{'date':str(day.date()),'price':px,'shares':cap/px,'market_cap':cap,'currency':ccy,'share_basis':'ordinary','consolidation_perimeter':'consolidated'},
            'forecasts':{
             'PER':{**horizon,'period':row.get('PER periodo','UNKNOWN'),'eps':px/pe if pe else None},
             'EV/EBITDA':{**horizon,'period':row.get('EV/EBITDA periodo','UNKNOWN'),
                'ebitda':ebitda,'ebit':ebitda*.8,'da':ebitda*.2,
                'lease_perimeter':'financial_ex_leases' if row.get('Perímetro deuda')=='Financiera sin leases' else 'UNKNOWN',
                'da_definition':'pure_operating_da'}},
            'balance':{'date':str(day.date()),'currency':fin,'financial_debt':0.,'cash':0.,'noncontrolling_interests':0.,'preferred_equity':0.,'consolidation_perimeter':'consolidated',
                'debt_perimeter':'financial_ex_leases','cash_perimeter':'cash_and_liquid_investments',
                'definition_source':'https://example.invalid/synthetic/balance'}}
        docs.append({'schema':'multiple-evidence-v1','payload':payload,'sha256':digest(payload),
                     'retrieved_at':str(day.date()),'source_url':'https://example.invalid/synthetic/source'})
    peers['Evidencia múltiplos']=docs
    return peers
