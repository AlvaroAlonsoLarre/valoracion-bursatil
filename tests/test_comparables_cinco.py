import json
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pandas as pd
import pytest
from auditoria_io import restore_frame
from comparables_inteligentes import (activity_tags,activity_conflict,score_and_filter,
    basic_peer_row,select_display_peers)
from comparables_proveedores import provider_candidates,yahoo_symbol
from seguimiento_metricas import informative_peers


@pytest.mark.parametrize('ticker,expected',[
    ('MSFT',{'ORCL','SAP','CRM','NOW','ADBE'}),
    ('000660.KS',{'005930.KS','MU','2408.TW','2344.TW','285A.T'}),
    ('JNJ',{'ABBV','LLY','MRK','AMGN','GILD'}),
    ('JPM',{'BAC','C','WFC','RY','TD'}),
])
def test_archived_real_profiles_keep_top_five_and_expand_to_ten(ticker,expected):
    # Capturas fechadas del repositorio: regresión económica, NO una consulta de hoy.
    path=Path('docs/v6_simplificada_2026-11-12/inputs')/(ticker+'_after.json')
    p=json.loads(path.read_text());peers=restore_frame(p['frames']['peers'])
    *_,universe=score_and_filter(peers,ticker,target_info=p['kwargs']['info'],return_universe=True,as_of=p['kwargs']['as_of'])
    result=informative_peers(universe,p['kwargs']['info'])
    assert {r['Ticker'] for r in result['rows'][:5]}==expected
    assert 5<=len(result['rows'])<=10 and result['target_count']==10


def test_secondary_foundry_and_hbm_ip_are_not_memory_manufacturers():
    target=activity_tags('Manufactures DRAM NAND. Also engages in foundry business.')
    assert activity_conflict(target,activity_tags('Operates wafer foundry fabrication services.'))
    design=activity_tags('ASIC and SoC design services; high bandwidth memory IPs.')
    assert 'memoria' not in design and 'diseno_chips' in design
    assert not activity_conflict(target,activity_tags('Manufactures DRAM NAND and flash memory.'))


def test_customer_industry_and_secondary_bank_stakes_do_not_define_peer_group():
    target=software_profile('Chip Designer')
    target.update(industryKey='semiconductors',longBusinessSummary='Designs GPUs and CPUs for data centers and electric vehicle applications.')
    good={**target,'longName':'Processor Peer','longBusinessSummary':'Designs microprocessors and GPUs for data center applications.'}
    memory={**target,'longName':'Memory Peer','longBusinessSummary':'Develops and manufactures semiconductor devices. Offers DRAM memory and NAND. Also foundry business.'}
    analog={**target,'longName':'Analog Peer','longBusinessSummary':'Designs semiconductors. Operates Analog and Embedded Processing segments. The Analog segment offers power products.'}
    rows=pd.DataFrame([basic_peer_row('GOOD',good),basic_peer_row('MEMORY',memory),basic_peer_row('ANALOG',analog)])
    assert select_display_peers(rows,target)['Ticker'].tolist()==['GOOD']
    bank={**target,'industryKey':'banks-diversified','sectorKey':'financial-services','longName':'Bank','longBusinessSummary':'Commercial bank offering lending and deposit accounts.'}
    insurer={**bank,'industryKey':'insurance-diversified','longName':'Insurance Conglomerate'}
    assert select_display_peers(pd.DataFrame([basic_peer_row('INS',insurer)]),bank).empty


def software_profile(name='Peer'):
    return {'longName':name,'longBusinessSummary':'Enterprise software ERP cloud services for finance and workflow automation.',
        'industryKey':'software-application','sectorKey':'technology','marketCap':10e9,
        'currency':'USD','financialCurrency':'USD','currentPrice':100.,'totalRevenue':2e9,
        'trailingPE':np.nan,'forwardPE':20.,'enterpriseToEbitda':12.}


def test_one_missing_ratio_keeps_peer_and_one_peer_is_not_padded():
    profile=software_profile();p=pd.DataFrame([basic_peer_row('P',profile)])
    b=informative_peers(p,software_profile('Target'))
    assert len(b['rows'])==1 and b['rows'][0]['PER TTM Yahoo'] is None
    assert b['stats']['PER TTM Yahoo']['n']==0
    assert b['stats']['EV/EBITDA Yahoo']['n']==1 and b['warning']


def test_same_sector_and_duplicate_classes_do_not_create_five_peers():
    target=software_profile('Target');peer=software_profile('Same Issuer')
    rows=[basic_peer_row(t,peer) for t in ['CLASS-A','CLASS-C']]
    rows.append(basic_peer_row('UNRELATED',{**peer,'longName':'Unrelated','longBusinessSummary':'Manufactures smartphones and wearable consumer devices.','industryKey':'consumer-electronics'}))
    selected=select_display_peers(pd.DataFrame(rows),target)
    assert len(selected)==1 and selected.iloc[0]['Ticker']=='CLASS-A'


def test_provider_discovery_failure_isolated_and_keys_never_logged(tmp_path):
    calls=[]
    def get(url,**kwargs):
        calls.append(url)
        return SimpleNamespace(status_code=403 if 'financialmodelingprep' in url else 200,
            json=lambda:['ORCL','SAP','TARGET','ORCL','WRONG:CODE'])
    candidates,errors=provider_candidates('TARGET',get=get,env={'FMP_API_KEY':'SECRET1','FINNHUB_API_KEY':'SECRET2','VALUACION_SOURCE_CACHE':str(tmp_path)})
    assert set(candidates)=={'ORCL','SAP'} and errors==['FMP: HTTP 403; continúa Yahoo']
    assert 'SECRET' not in json.dumps([candidates,errors])
    assert yahoo_symbol('BRK.B')=='BRK-B' and yahoo_symbol('005930.KS')=='005930.KS'
    assert yahoo_symbol('005930.KRX') is None


def test_no_api_key_does_not_make_provider_requests():
    def forbidden(*args,**kwargs):raise AssertionError('No debe acceder a la red')
    assert provider_candidates('MSFT',get=forbidden,env={})==({},[])


def test_refreshed_missing_and_multicurrency_ratios_do_not_mix_with_ntm():
    profile=software_profile();row=basic_peer_row('P',profile)
    refreshed={**profile,'trailingPE':15.,'forwardPE':30.,'currency':'EUR','financialCurrency':'EUR'}
    b=informative_peers(pd.DataFrame([row]),software_profile('Target'),{'P':refreshed})
    assert b['rows'][0]['PER TTM Yahoo']==15. and b['rows'][0]['PER forward Yahoo']==30.
    assert b['stats']['PER TTM Yahoo']['n']==0  # Política conservadora vigente de moneda.
    assert 'no acreditado' in b['rows'][0]['Periodo PER']
