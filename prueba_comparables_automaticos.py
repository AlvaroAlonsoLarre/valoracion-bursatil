"""Prueba SINTÉTICA y SIN INTERNET del selector automático.
No utiliza cotizaciones reales ni garantiza resultados de Yahoo.
"""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
import pandas as pd
from comparables_inteligentes import score_and_filter,discover_candidates

profiles={
'MSFT':{'industryKey':'software-infrastructure','sectorKey':'technology','industry':'Software - Infrastructure','longBusinessSummary':'Microsoft provides Azure cloud computing infrastructure, enterprise software Microsoft 365, Office, Windows operating systems, database software and AI cloud platforms, business productivity and subscription software.'},
'000660.KS':{'industryKey':'semiconductors','sectorKey':'technology','industry':'Semiconductors','longBusinessSummary':'SK Hynix manufactures DRAM high bandwidth memory HBM NAND flash memory semiconductors for datacenter AI cloud servers memory storage.'}
}

msft=[
('ORCL','Oracle','software-infrastructure','enterprise cloud computing infrastructure database software applications subscription software enterprise systems',22,29,16),
('SAP','SAP','software-application','ERP enterprise software subscription cloud enterprise resource planning businesses applications',26,25,17),
('CRM','Salesforce','software-application','enterprise software cloud customer relationship management SaaS applications sales marketing business productivity',18,22,14),
('PANW','Palo Alto','software-infrastructure','cybersecurity company provides network security firewall platforms cyber attack prevention enterprise threat intelligence',55,5,9),
('CRWD','Crowdstrike','software-infrastructure','cybersecurity endpoint protection threat detection identity network security cloud platform cyber attacks',65,-3,30),
('NET','Cloudflare','software-infrastructure','internet content delivery cybersecurity network edge security firewall cloud traffic services',60,-6,30),
('IBM','IBM','information-technology-services','enterprise hybrid cloud software infrastructure data AI IT services',20,16,9),
]
sk=[
('MU','Micron','semiconductors','manufactures DRAM high bandwidth memory HBM NAND flash memory chips for AI datacenter storage devices servers',11,44,53),
('2408.TW','Nanya','semiconductors','manufacturer of DRAM memory chips dynamic random access semiconductor memory products data storage',9,48,35),
('005930.KS','Samsung Electronics','consumer-electronics','designs smartphones consumer electronics and semiconductor memory chips including DRAM and NAND flash memory',7,30,45),
('000990.KS','DB HiTek','semiconductors','foundry semiconductor wafer fabrication analog mixed signal integrated circuits chips automotive display',19,17,10),
('036540.KQ','SFA Semicon','semiconductors','semiconductor assembly packaging testing outsourced fab support services',16,-3,70),
]
for ticker, test in [('MSFT',msft),('000660.KS',sk)]:
 peers=pd.DataFrame([{'Ticker':t,'Empresa':name,'Industria clave':ind,'Sector clave':'technology','Descripción actividad':desc,
     'PER forward':pe,'EV/EBITDA':12,'Margen operativo (%)':margin,'Crecimiento ventas (%)':growth,
     'Capitalización (miles de millones)':100} for t,name,ind,desc,pe,margin,growth in test])
 ranked,pe,ev,ref,universe=score_and_filter(peers,ticker,target_margin=30,target_growth=20,target_cap=200,
                                   target_info=profiles[ticker],max_peers=10,return_universe=True)
 print('\n',ticker, 'median',pe, ev)
 print(universe[['Ticker','Puntuación económica (0-100)','Similitud de actividad (0-100)','Elegible','PER admisible']].to_string(index=False))
 assert ranked['Elegible'].any()
 if ticker=='MSFT':
  assert universe.loc[universe.Ticker=='PANW','Elegible'].iloc[0]==False
  assert ranked.loc[ranked.Ticker=='ORCL','Elegible'].iloc[0]==True
 if ticker=='000660.KS':
  assert ranked.loc[ranked.Ticker=='MU','Elegible'].iloc[0]==True
  assert universe.loc[universe.Ticker=='000990.KS','Elegible'].iloc[0]==False

class Industry:
 def __init__(self,key,region='US'):
  self.top_companies=pd.DataFrame({'symbol':{'US':['MU','INTC','NVDA'],'KR':['005930.KS','000990.KS'],'TW':['2408.TW','2344.TW'],'JP':['285A.T']} .get(region,[])})
  self.top_growth_companies=pd.DataFrame({'symbol':[]})
class Sector:
 def __init__(self,key,region='US'):
  self.top_companies=pd.DataFrame({'symbol':['AVGO','AMD']})
class Search:
 def __init__(self,*args,**kwargs):self.quotes=[{'quoteType':'EQUITY','symbol':'WDC'}, {'quoteType':'ETF','symbol':'SMH'}]
class Yf:
 Industry=Industry; Sector=Sector; Search=Search
candidates,errors=discover_candidates(Yf,'000660.KS',profiles['000660.KS'],region='KR')
print('Discovered:',list(candidates),'errors',errors)
assert {'MU','2408.TW','005930.KS','WDC'}<=set(candidates)
assert 'SMH' not in candidates
print('PASS autodiscovery and relevance tests')
