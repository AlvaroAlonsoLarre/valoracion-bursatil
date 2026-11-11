"""Registro único de métodos y snapshots JSON de entradas financieras, sin código ejecutable."""
from datetime import date, datetime
from importlib.metadata import version, PackageNotFoundError
from pathlib import Path
import hashlib
import json
import math
import os
import subprocess
import numpy as np
import pandas as pd


def clean(value):
    if isinstance(value,dict):return {str(k):clean(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [clean(v) for v in value]
    if value is None or value is pd.NaT or value is pd.NA:return None
    if isinstance(value,(pd.Timestamp,datetime,date)):return value.isoformat()
    if isinstance(value,np.generic):return clean(value.item())
    if isinstance(value,float):return value if math.isfinite(value) else None
    return value


def frame_payload(df):
    return {'columns':list(df.columns),'index':clean(df.index.tolist()),'data':clean(df.to_numpy().tolist()),
            'datetime_index':isinstance(df.index,pd.DatetimeIndex),'index_name':df.index.name,'attrs':clean(df.attrs),
            'frequency':df.index.freqstr if isinstance(df.index,pd.DatetimeIndex) else None}


def restore_frame(payload):
    index=pd.to_datetime(payload['index']) if payload['datetime_index'] else payload['index']
    df=pd.DataFrame(payload['data'],columns=payload['columns'],index=index)
    if payload.get('frequency'):df.index=pd.DatetimeIndex(df.index,freq=payload['frequency'])
    df.index.name=payload['index_name'];df.attrs.update(payload.get('attrs',{}))
    return df


def provenance():
    try:sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=Path(__file__).parent,text=True).strip()
    except (OSError,subprocess.SubprocessError):sha='N/D'
    packages={}
    for name in ['pandas','numpy','yfinance','requests','openpyxl']:
        try:packages[name]=version(name)
        except PackageNotFoundError:packages[name]='N/D'
    return {'sha':sha,'run_id':os.getenv('GITHUB_RUN_ID','local'),'attempt':os.getenv('GITHUB_RUN_ATTEMPT','1'),
            'dependencies':packages}


def write_snapshot(path,annual,peers,kwargs,historical=None,evidence=None):
    frames={'annual':annual,'peers':peers}
    scalar=dict(kwargs)
    if scalar.get('quarterly') is not None:frames['quarterly']=scalar.pop('quarterly')
    else:scalar.pop('quarterly',None)
    payload={'schema':'audit-inputs-v1','frames':{k:frame_payload(v) for k,v in frames.items()},
       'kwargs':clean(scalar),'historical':{k:frame_payload(v) for k,v in (historical or {}).items()},
       'provenance':provenance(),'evidence':clean(evidence or {}),
       'assumption_environment':{k:v for k,v in os.environ.items() if k.startswith('VALUACION_') and not any(x in k for x in ['USER_AGENT','EMAIL','TOKEN','SECRET','PASSWORD','KEY','SNAPSHOT','TICKER','NUM_TRIMESTRES'])}}
    # Environment values are evidence, never instructions for the replay process.
    encoded=json.dumps(payload,ensure_ascii=False,allow_nan=False,sort_keys=True,indent=2).encode()
    Path(path).write_bytes(encoded)
    return hashlib.sha256(encoded).hexdigest()


def read_snapshot(path):
    payload=json.loads(Path(path).read_text())
    if payload['schema']!='audit-inputs-v1':raise ValueError('Schema snapshot no compatible')
    frames={k:restore_frame(v) for k,v in payload['frames'].items()}
    kwargs=payload['kwargs']
    kwargs['quarterly']=frames.get('quarterly')
    return frames['annual'],frames['peers'],kwargs,payload


def valuation_registry(fundamental,historical_eps,historical_fcf,*,as_of,fy_date,ttm_date,currency,source,freshness):
    rows=[]
    as_of=str(pd.Timestamp(as_of).date())
    fy_date=str(pd.Timestamp(fy_date).date())
    ids={'PER forward':'peer_pe_ntm','EV/EBITDA forward':'peer_ev_ebitda_ntm',
         'DCF FCFF (valor futuro)':'dcf_fcff_future','DCF FCFF (valor presente)':'dcf_fcff_present'}
    if fundamental.empty:
        for scenario in ['Pesimista','Base','Optimista']:
            for method,horizons in [('dcf_fcff_present',[0]),('dcf_fcff_future',[1,3]),('peer_pe_ntm',[1,3]),('peer_ev_ebitda_ntm',[1,3])]:
                for horizon in horizons:
                    rows.append({'method_id':method,'scenario':scenario,'scenario_type':'sensibilidad_fundamental',
                        'base_date':str(ttm_date),'flow_period':'TTM/proyección explícita','horizon_years':horizon,
                        'valuation_date':as_of,'target_date':str((pd.Timestamp(as_of)+pd.DateOffset(years=horizon)).date()),
                        'currency':currency,'price':np.nan,'validation_state':'BLOQUEO','source':source,
                        'freshness':freshness,'limitation':'Requisitos del modelo incumplidos; consultar Control modelo'})
    for _,r in fundamental.iterrows():
        target=r.get('Precio objetivo (divisa cotización)')
        rows.append({'method_id':ids[r['Método']],'scenario':r['Escenario'],'scenario_type':'sensibilidad_fundamental',
            'base_date':str(ttm_date),'flow_period':'TTM/proyección explícita','horizon_years':int(r['Horizonte (años)']),
            'valuation_date':str(as_of),'target_date':r.get('Fecha objetivo aprox.'),'currency':currency,
            'price':target,'validation_state':r.get('Estado validación','CONDICIONAL') if pd.notna(target) else 'N/D',
            'source':source,'freshness':freshness,'limitation':r.get('Limitación','')})
    for method,table in [('historical_eps_pe',historical_eps),('historical_fcf_yield',historical_fcf)]:
        for _,r in table.iterrows():
            h=int(r['Horizonte (años)'])
            rows.append({'method_id':method,'scenario':r['Escenario'],'scenario_type':'sensibilidad_historica_no_pronostico',
                'base_date':str(fy_date),'flow_period':'FY','horizon_years':h,'valuation_date':str(as_of),
                'target_date':str((pd.Timestamp(fy_date)+pd.DateOffset(years=h)).date()),'currency':currency,
                'price':r['Precio objetivo'],'validation_state':'SENSIBILIDAD_HISTORICA','source':source,
                'freshness':freshness,'limitation':'Media aritmética ± desviación conjunta; no probabilidad ni consenso; no agregar con DCF'})
    return pd.DataFrame(rows,columns=['method_id','scenario','scenario_type','base_date','flow_period','horizon_years',
        'valuation_date','target_date','currency','price','validation_state','source','freshness','limitation'])


def assess(sheets):
    control=sheets.get('Control modelo',pd.DataFrame())
    blockers=int(control.get('Estado',pd.Series(dtype=str)).eq('BLOQUEO').sum())
    registry=sheets.get('Registro valoraciones',pd.DataFrame())
    fundamental=registry[registry.get('scenario_type',pd.Series(index=registry.index,dtype=str)).eq('sensibilidad_fundamental')]
    available=int(pd.to_numeric(fundamental.get('price',pd.Series(dtype=float)),errors='coerce').notna().sum())
    status='BLOQUEO' if blockers or not available else 'PARCIAL' if fundamental['price'].isna().any() else 'CONDICIONAL'
    return {'errores_bloqueantes':blockers,'objetivos_fundamentales_disponibles':available,'estado_financiero':status,
        'publicable':False, # No convertir una sensibilidad en estimación validada sin revisión financiera.
        'exit_code':2 if blockers or not available else 0}
