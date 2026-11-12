# -*- coding: utf-8 -*-
"""Pruebas reproducibles del modelo sin internet. Ejecutar: python autoprueba_modelo.py"""
from datetime import datetime
import math
import pandas as pd
import numpy as np
from modelo_fundamental import build_fundamental_model, fx_rate
from comparables_inteligentes import selected_candidates, score_and_filter

rows=[]
for y in range(2022,2026):
    rev=70e12*(1.16**(y-2022))
    op=rev*.32
    rows.append({'Ejercicio':y,'Ingresos':rev,'Beneficio operativo':op,
                 'Beneficio neto':op*.73,'EPS diluido':42000,
                 'D&A':rev*.09,'CAPEX':rev*.19,'Flujo de caja libre':rev*.20,
                 'Tasa fiscal':.24,'Deuda neta':-10e12,'Deuda total':20e12,
                 'Capital invertido aproximado':40e12,'NOPAT aproximado':op*.76,
                 'Dividendos':rev*.012,'Recompras de acciones':rev*.015,
                 'Gastos por intereses':.4e12})
annual=pd.DataFrame(rows).set_index('Ejercicio')
# 6 trimestres consecutivos con salto (Q1 FY anterior reconstruible por diferencia)
qperiods=pd.to_datetime(['2025-03-31','2025-06-30','2025-09-30','2025-12-31','2026-03-31','2026-06-30'])
qrows=[]
for i,d in enumerate(qperiods):
    r=22e12*(1.15**i)
    qrows.append({'Cierre del trimestre':d,'Ingresos':r,
        'Beneficio operativo':r*.48,'Beneficio neto':r*.35,'D&A':r*.075,
        'CAPEX':r*.2,'Deuda total':19e12,'Deuda neta':-12e12-i*2e12})
quarterly=pd.DataFrame(qrows).set_index('Cierre del trimestre')
# Fixture conciliada: FY2025 debe ser la suma de los cuatro trimestres.
for field in ['Ingresos','Beneficio operativo','Beneficio neto','D&A','CAPEX']:
    annual.loc[2025,field]=quarterly.loc['2025',field].sum()
peers=pd.DataFrame([{'Ticker':t,'Empresa':'Memoria '+t,'PER forward':p,'EV/EBITDA':e,
   'Margen operativo (%)':35+i,'Crecimiento ventas (%)':20+i,
   'Capitalización (miles de millones)':40e3+i*500} for i,(t,p,e) in enumerate([
       ('MU',10,6),('005930.KS',11,7),('2408.TW',14,8),('2344.TW',600,-2)])])
peers=peers.assign(**{'PER periodo':'NTM','PER base':'GAAP','EV/EBITDA periodo':'NTM','Perímetro deuda':'Financiera sin leases'})
from tests.multiple_fixtures import with_evidence
peers=with_evidence(peers,'2026-10-27')
fx,fxsrc=fx_rate('KRW','KRW')
assert fx==1
assert math.isnan(fx_rate('KRW','USD')[0])
assert not selected_candidates('000660.KS'), 'La selección predeterminada no debe exigir catálogos'
# Clasificación y textos de actividad para que la selección sea verificable.
peers['Industria clave']='semiconductors'
peers['Sector clave']='technology'
peers['Descripción actividad']=[
 'manufactures dynamic random access memory DRAM NAND flash memory and HBM memory chips',
 'DRAM memory NAND memory chips and HBM high bandwidth storage chips',
 'manufactures DRAM semiconductor memory chips and modules',
 'designs semiconductor foundry chips and semiconductor manufacturing equipment',
]
target_profile={'valuation_accounting_basis':'GAAP','industryKey':'semiconductors','sectorKey':'technology',
 'longBusinessSummary':'Manufactures DRAM NAND flash high bandwidth HBM memory chips and data center memory products'}
rank,pe,ev,refs=score_and_filter(peers,'000660.KS',target_margin=35,target_growth=25,
                                  target_cap=40e3,target_info=target_profile,as_of='2026-10-27')
assert rank['PER admisible'].sum()>=3 and 10<=pe<=15,rank.to_string()
assert not rank.loc[rank['Ticker']=='2344.TW','PER admisible'].any()

res=build_fundamental_model(annual,peers,price=400000,market_cap=280e12,shares_outstanding=700e6,
    financial_currency='KRW',quote_currency='KRW',fx=fx,source='Yahoo',quarterly=quarterly,
    fiscal_end_date='2025-12-31',as_of='2026-10-27',ticker='000660.KS',
    info={**target_profile,'beta':1.2,'forwardPE':10.})
assert len(res.projected)==24 and len(res.valuation)==21
assert (res.assumptions.set_index('Supuesto').loc['Empresa cíclica','Valor']=='Sí')
assert (res.assumptions.set_index('Supuesto').loc['Base operativa','Valor']=='TTM')
assert res.assumptions.set_index('Supuesto').loc['Deuda neta reciente (miles MM)','Valor']==-22e3
assert res.fiscal_bridge['Trimestres reales'].iloc[0]==2
assert res.valuation.loc[res.valuation['Método']=='PER forward','Precio objetivo (divisa cotización)'].notna().any()
assert res.projected.loc[res.projected['Escenario']=='Base','Deuda neta proyectada (miles MM)'].notna().all()
# Sin FX, no se autoriza mostrar precios.
res_fx=build_fundamental_model(annual,peers,price=300,market_cap=280e12,shares_outstanding=700e6,
    financial_currency='KRW',quote_currency='USD',fx=float('nan'),source='Yahoo',quarterly=quarterly,
    fiscal_end_date='2025-12-31',as_of='2026-10-27',ticker='000660.KS',info={})
assert res_fx.valuation.empty
# Para cíclicas sin tres peers válidos se bloquea PER y EV/EBITDA, no se inventan comparables.
res_no_peers=build_fundamental_model(annual,peers.iloc[:1],price=400000,market_cap=280e12,shares_outstanding=700e6,
    financial_currency='KRW',quote_currency='KRW',fx=fx,source='Yahoo',quarterly=quarterly,
    fiscal_end_date='2025-12-31',as_of='2026-10-27',ticker='000660.KS',info={**target_profile,'forwardPE':4,'enterpriseToEbitda':9})
assert res_no_peers.valuation.loc[res_no_peers.valuation['Método']=='PER forward','Precio objetivo (divisa cotización)'].isna().all()
assert res_no_peers.valuation.loc[res_no_peers.valuation['Método']=='EV/EBITDA forward','Precio objetivo (divisa cotización)'].isna().all()
# Con solo dos trimestres parciales sin comparables previos, no se debe
# volver al FY antiguo para publicar un precio aparentemente válido.
partial=build_fundamental_model(annual,peers,price=400000,market_cap=280e12,shares_outstanding=700e6,
    financial_currency='KRW',quote_currency='KRW',fx=1,quarterly=quarterly.tail(2),
    fiscal_end_date='2025-12-31',as_of='2026-10-27',ticker='000660.KS',info={**target_profile,'beta':1.2})
assert partial.valuation.empty
assert 'BLOQUEO' in partial.checks['Estado'].values
# Rechazar diferencias de más del 10% entre valor bursátil, precio y acciones.
invalid_shares=build_fundamental_model(annual,peers,price=400000,market_cap=280e12,shares_outstanding=500e6,
    financial_currency='KRW',quote_currency='KRW',fx=1,quarterly=quarterly,
    fiscal_end_date='2025-12-31',as_of='2026-10-27',ticker='000660.KS',info={**target_profile,'beta':1.2})
assert invalid_shares.valuation.empty
print('PASS: TTM, cierre fiscal parcial, deuda reciente, ciclo, peers, FX y bloqueos de calidad')
