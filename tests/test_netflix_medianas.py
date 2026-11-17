"""Regresiones de Netflix, diez emisores, mediana y capturas guardadas."""
from copy import deepcopy
from types import SimpleNamespace
import pandas as pd
import pytest
from comparables_inteligentes import basic_peer_row,select_display_peers
from seguimiento_metricas import informative_peers,summarize
from tests.test_v7_integrada import archived
from flujo_acciones import analysis_from_snapshot
from seguimiento_servicio import Service
from seguimiento_store import Store


def video(name,pe=20.,forward=15.,industry='entertainment'):
    return {'longName':name,'symbol':name,'industryKey':industry,
        'sectorKey':'communication-services','currency':'USD','financialCurrency':'USD',
        'longBusinessSummary':'Provides entertainment services with TV series, feature films and video streaming subscriptions.',
        'currentPrice':100.,'marketCap':50e9,'totalRevenue':10e9,
        'trailingPE':pe,'forwardPE':forward,'enterpriseToEbitda':12.}


def test_netflix_video_activity_finds_ten_and_excludes_unrelated_music():
    target=video('NFLX')
    rows=[basic_peer_row('V'+str(i),video('Video '+str(i),pe=10.+i)) for i in range(12)]
    rows.append(basic_peer_row('MUSIC',{**video('Music'),'longBusinessSummary':'Produces recorded music and distributes albums, songs and music publishing rights.'}))
    rows.append(basic_peer_row('SPORT',{**video('Sport'),'longBusinessSummary':'Operates in motorsports with sports rights and a TV series and video streaming platform.'}))
    b=informative_peers(pd.DataFrame(rows),target)
    assert len(b['rows'])==10 and b['target_count']==10
    assert not {'MUSIC','SPORT'} & {r['Ticker'] for r in b['rows']}
    assert not b['warning']
    assert b['stats']['PER TTM Yahoo']['n']==10


def test_missing_ttm_does_not_become_forward_and_median_ignores_missing():
    target=video('NFLX')
    rows=[basic_peer_row(str(i),video('Video '+str(i),pe=x)) for i,x in enumerate([10.,20.,1000.,None,-4.])]
    b=informative_peers(pd.DataFrame(rows),target)
    assert b['stats']['PER TTM Yahoo']['median']==20.
    assert b['stats']['PER TTM Yahoo']['n']==3
    assert b['stats']['PER TTM Yahoo']['mean']!=20.
    assert len(b['rows'])==5


def test_watchlist_uses_median_and_explicit_informative_origin():
    p=deepcopy(archived('NFLX'));result,_=analysis_from_snapshot(p)
    p['kwargs']['info']={**p['kwargs']['info'],**video('NFLX')}
    rows=pd.DataFrame([basic_peer_row('V'+str(i),video('Video '+str(i),pe=x)) for i,x in enumerate([10.,20.,1000.,None])])
    r=SimpleNamespace(**{**vars(result),'peers':pd.DataFrame(),'universe':rows})
    m=summarize(p,r)
    assert m['row']['PER comparables TTM']==20.
    assert m['row']['PER TTM comparables B']==20.
    assert m['row']['N PER comparables']==3
    assert 'Yahoo informativo' in m['row']['Origen PER comparables']
    assert m['row']['PER TTM comparables validado'] is None
    assert m['row']['PER forward comparables B']==15.
    assert m['schema_version']==4


def test_saved_schema_three_is_recalculated_without_network(tmp_path,monkeypatch):
    store=Store(tmp_path);service=Service(store,None)
    p=deepcopy(archived('NFLX'));service.save_capture(p);entry=store.entry('NFLX')
    metrics=deepcopy(entry['metrics']);metrics['schema_version']=3
    metrics['row']['PER comparables TTM']=999999.;metrics['components']={'old':'preserved'}
    store.update_metrics('NFLX',metrics)
    monkeypatch.setattr('seguimiento_servicio.provider_profile',lambda *a,**k:pytest.fail('Migración no debe acceder a la red'))
    upgraded=service.ensure_metrics(store.entry('NFLX'))
    assert upgraded['metrics']['schema_version']==4
    assert upgraded['metrics']['row']['PER comparables TTM']!=999999.
    assert upgraded['metrics']['components']=={'old':'preserved'}
    assert upgraded['payload']['kwargs']['ticker']=='NFLX'
