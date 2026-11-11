"""Contraste fechado de IR, separado de cobertura SEC y sin completar CF ausentes."""
from pathlib import Path
import hashlib
import json
import pandas as pd
import requests
from bs4 import BeautifulSoup


def comprobar_ir(ticker, quarterly, currency, as_of, requests_get=None, references=None):
    refs=references if references is not None else json.loads(Path(__file__).with_name('referencias_oficiales.json').read_text())
    ref=refs.get(ticker,{})
    result={'status':'NO_VERIFICADO','source_url':ref.get('source',''),'newer_filing_confirmed':False,
            'detail':'Sin referencia IR configurada para este ticker','comparisons':[],
            'extraordinary':ref.get('extraordinary',[])}
    if not ref or pd.Timestamp(ref['published'])>pd.Timestamp(as_of):return result
    try:
        response=(requests_get or requests.get)(ref['source'],timeout=25)
        response.raise_for_status()
        text=' '.join(BeautifulSoup(response.text,'html.parser').stripped_strings)
        if not all(token in text for token in ref['evidence_tokens']):
            raise ValueError('La página ya no acredita los datos de la referencia; revisar extracción')
        result['source_sha256']=hashlib.sha256(response.content).hexdigest()
        if currency!=ref['currency']:raise ValueError('Divisa IR distinta a la contabilidad; no comparar unidades nativas')
        latest=pd.to_datetime(quarterly.index).max() if quarterly is not None and len(quarterly) else pd.NaT
        period=pd.Timestamp(ref['period_end'])
        result.update(status='VERIFICADO_PERIODO',detail='IR contrastado para '+str(period.date())+'; no acredita ausencia de publicaciones posteriores')
        if pd.isna(latest) or latest<period:
            result.update(status='BLOQUEO',newer_filing_confirmed=True,
                detail=f'IR confirma periodo {period.date()} posterior a Yahoo {latest}; faltan estados completos; no inventar TTM')
        for field,value in ref['values'].items():
            official=value*ref['multiplier']
            matching=quarterly.loc[pd.to_datetime(quarterly.index)==period,field] if quarterly is not None and field in quarterly else pd.Series(dtype=float)
            yahoo=float(matching.iloc[0]) if len(matching) else None
            diff=abs(yahoo-official)/abs(official) if yahoo is not None and pd.notna(yahoo) else None
            state='COINCIDE' if diff is not None and diff<.01 else 'N/D' if diff is None else 'BLOQUEO'
            if state=='BLOQUEO':result.update(status='BLOQUEO',detail='Diferencia IR/Yahoo >=1%; revisar '+field)
            result['comparisons'].append({'Campo':field,'Periodo':ref['period_end'],'Moneda':currency,
                'Unidad original':ref['unit'],'Multiplicador':ref['multiplier'],'IR (unidades)':official,
                'Yahoo (unidades)':yahoo,'Diferencia relativa':diff,'Estado':state,'Fuente':ref['source']})
    except Exception as exc:
        result.update(status='NO_VERIFICADO',detail=f'IR no verificable: {type(exc).__name__}: {exc}')
    return result
