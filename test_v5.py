"""Pruebas automáticas sin Internet, sin alterar los resultados publicados."""
from datetime import date
from io import StringIO
import json
import math
import pandas as pd
from actualidad_financiera import comprobar_actualidad
from comparables_inteligentes import score_and_filter
from ejecutar_analisis import safe_records

class MockResponse:
    def raise_for_status(self):pass
    def json(self):
        return {'filings':{'recent':{'form':['8-K','10-Q','10-K'],
          'reportDate':['2026-10-23','2026-09-30','2026-06-30'],
          'filingDate':['2026-10-28','2026-10-27','2026-07-25']}}}
def mock_get(url,headers,timeout):
    assert 'CIK0000789019.json' in url
    assert 'User-Agent' in headers
    return MockResponse()
r=comprobar_actualidad(sec_cik='0000789019',sec_user_agent='Valuation Project (contact: hello@example.com)',
    quarterly_dates=['2026-06-30'],as_of='2026-11-11',requests_get=mock_get)
assert r['newer_filing_confirmed'] and r['status']=='BLOQUEO'
assert r['sec_report_end']=='2026-09-30'
r2=comprobar_actualidad(sec_cik=None,quarterly_dates=['2026-09-30'],
    earnings_dates=['2027-01-22'],as_of='2026-11-11')
assert not r2['newer_filing_confirmed'] and r2['status']=='NO_VERIFICADO'
r3=comprobar_actualidad(sec_cik=None,quarterly_dates=['2026-06-30'],
    earnings_dates=['2026-10-28'],as_of='2026-11-11')
assert r3['status']=='REVISAR' and not r3['newer_filing_confirmed']

info={'longBusinessSummary':'SK Hynix manufactures DRAM HBM memory NAND flash memory chips for data centers',
      'industryKey':'semiconductors','sectorKey':'technology','currency':'KRW'}
rows=[
 {'Ticker':'MU','Descripción actividad':'DRAM high bandwidth HBM memory semiconductor manufacturing and NAND flash memory products',
  'Industria clave':'semiconductors','Sector clave':'technology','PER forward':10,'EV/EBITDA':8,'Margen operativo (%)':30},
 {'Ticker':'2408.TW','Descripción actividad':'DRAM dynamic random access memory semiconductor company',
  'Industria clave':'semiconductors','Sector clave':'technology','PER forward':8,'EV/EBITDA':9,'Margen operativo (%)':22},
 {'Ticker':'285A.T','Descripción actividad':'NAND flash memory manufacturer for SSD storage systems',
  'Industria clave':'semiconductors','Sector clave':'technology','PER forward':11,'EV/EBITDA':10,'Margen operativo (%)':40},
 {'Ticker':'TSM','Descripción actividad':'Foundry company wafer fabrication and contract semiconductor manufacturing',
  'Industria clave':'semiconductors','Sector clave':'technology','PER forward':18,'EV/EBITDA':13,'Margen operativo (%)':47},
 {'Ticker':'UMC','Descripción actividad':'Foundry company wafer fabrication semiconductor integrated circuits',
  'Industria clave':'semiconductors','Sector clave':'technology','PER forward':20,'EV/EBITDA':7,'Margen operativo (%)':17},
]
for row in rows:row.update({'PER periodo':'NTM','PER base':'GAAP','EV/EBITDA periodo':'NTM','Perímetro deuda':'Financiera sin leases'})
selected,pe,ev,refs,universe=score_and_filter(pd.DataFrame(rows),'000660.KS',target_info=info,return_universe=True)
assert set(selected['Ticker'])=={'MU','2408.TW','285A.T'}, selected['Ticker'].tolist()
assert set(universe.loc[~universe['Elegible'],'Ticker'])=={'TSM','UMC'}
assert pe==10 and ev==9
assert set(selected['Confianza en comparabilidad'])<=set(['Media','Alta'])
assert len(universe)==5
empty,per,ev,refs,all_rows=score_and_filter(pd.DataFrame(rows[:2]),'000660.KS',target_info=info,return_universe=True)
assert math.isnan(per) and math.isnan(ev) and refs['Estado'].str.contains('BLOQUEADO').all()
records=safe_records(pd.DataFrame({'A':[float('nan'),3.5], 'B':['x','y']}))
assert records[0]['A'] is None and records[1]['A']==3.5
assert json.dumps(records,allow_nan=False)
print('PASS V5: publicación SEC posterior, fecha Yahoo solo alerta, selección única, bloqueo N<3 y JSON válido')
