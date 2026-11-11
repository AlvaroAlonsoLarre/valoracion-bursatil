# -*- coding: utf-8 -*-
"""Control conservador de nuevas publicaciones frente a Yahoo.

Un 10-Q/10-K SEC con reportDate más nuevo que el último trimestre de Yahoo
confirma que existe un estado publicado más reciente. El dato de calendario
Yahoo nunca se trata por sí solo como publicación confirmada.
"""
from __future__ import annotations
import datetime as dt
import pandas as pd
import requests


def _day(v):
    try:
        t=pd.Timestamp(v)
        if pd.isna(t):return None
        return t.tz_localize(None).date() if t.tzinfo is not None else t.date()
    except (TypeError,ValueError):return None


def comprobar_actualidad(*,sec_cik=None,sec_user_agent='',quarterly_dates=None,
                         earnings_dates=None,as_of=None,requests_get=None):
    today=_day(as_of) or dt.date.today()
    periods=sorted([x for x in (_day(v) for v in (quarterly_dates or [])) if x and x<=today])
    last_q=periods[-1] if periods else None
    age=(today-last_q).days if last_q else None
    base={'newer_filing_confirmed':False,'status':'NO_VERIFICADO',
          'latest_quarter_yahoo':str(last_q) if last_q else '',
          'days_since_latest_quarter':age,'sec_report_end':'','sec_filing_date':'',
          'earnings_calendar_alert':'','sec_earnings_8k_date':'',
          'source_url':'','detail':''}
    earnings=sorted([x for x in (_day(v) for v in (earnings_dates or [])) if x and x<=today])
    if last_q and earnings:
        after=[x for x in earnings if x>last_q+dt.timedelta(days=35)]
        if after:
            base['earnings_calendar_alert']=str(after[-1])
    if not last_q:
        base.update(status='BLOQUEO',detail='Yahoo no contiene cierre trimestral verificable')
        return base
    if age>125:
        base.update(status='REVISAR',detail=f'Último cierre trimestral Yahoo hace {age} días; confirmar nueva publicación')
    else:
        base.update(status='OK',detail=f'Último cierre trimestral Yahoo: {last_q} ({age} días)')
    cik=str(sec_cik or '').strip().lstrip('0')
    if not cik and base['status']=='OK':
        base['status']='NO_VERIFICADO'
        base['detail']+='; emisor sin CIK SEC: revisar fuentes oficiales del país'
    if cik and (not sec_user_agent or 'replace-with-your-email' in sec_user_agent):
        if base['status']=='OK':base['status']='NO_VERIFICADO'
        base['detail']+='; CIK conocido; falta User-Agent con contacto SEC para verificar presentaciones'
    if cik and sec_user_agent and 'replace-with-your-email' not in sec_user_agent:
        cik=cik.zfill(10)
        url=f'https://data.sec.gov/submissions/CIK{cik}.json'
        base['source_url']=url
        try:
            request=(requests_get or requests.get)(url,headers={'User-Agent':sec_user_agent},timeout=20)
            request.raise_for_status()
            recent=request.json().get('filings',{}).get('recent',{})
            n=min(len(recent.get('form',[])),len(recent.get('reportDate',[])),len(recent.get('filingDate',[])))
            confirmed=[]
            for i in range(n):
                form=str(recent['form'][i]).upper()
                report=_day(recent['reportDate'][i]); filed=_day(recent['filingDate'][i])
                if form not in ('10-Q','10-K','10-Q/A','10-K/A','20-F','40-F'):continue
                if report and filed and last_q<report<=today and filed<=today:
                    confirmed.append((report,filed,form))
            if n==0:raise ValueError('SEC no devuelve presentaciones verificables')
            if confirmed:
                report,filed,form=max(confirmed)
                base.update(newer_filing_confirmed=True,status='BLOQUEO',
                            sec_report_end=str(report),sec_filing_date=str(filed),
                            detail=f'{form} de SEC presentado {filed} incluye periodo {report}, posterior a Yahoo {last_q}; actualizar antes de valorar')
            else:
                # El 8-K ítem 2.02 comunica resultados, pero NO da por sí solo
                # un cierre contable inequívoco. Se etiqueta REVISAR, nunca
                # se afirma que el trimestre Yahoo deba reemplazarse.
                items=recent.get('items',[])
                news=[]
                for i in range(min(n,len(items))):
                    form=str(recent['form'][i]).upper()
                    filed=_day(recent['filingDate'][i])
                    if (form in ('8-K','8-K/A') and '2.02' in str(items[i])
                        and filed and last_q+dt.timedelta(days=40)<filed<=today):
                        news.append(filed)
                if news:
                    last=max(news)
                    base['sec_earnings_8k_date']=str(last)
                    if base['status']=='OK':base['status']='REVISAR'
                    base['detail']+=f'; SEC 8-K resultados ítem 2.02 presentado {last}: posible trimestre nuevo, revisar fecha del periodo'
                elif base['status']=='OK':
                    base['status']='VERIFICADO'
                    base['detail']+='; SEC sin 10-Q/10-K con periodo más reciente (no descarta comunicado de resultados externo)'
        except Exception as ex:
            if base['status']=='OK':base['status']='NO_VERIFICADO'
            base['detail']+=f'; SEC no pudo verificarse: {type(ex).__name__}: {str(ex)[:90]}'
    if base['earnings_calendar_alert'] and not base['newer_filing_confirmed']:
        if base['status'] in ('OK','VERIFICADO'):base['status']='REVISAR'
        base['detail']+=('; Yahoo marca una fecha de resultados anterior a hoy ('+
                        base['earnings_calendar_alert']+'); NO confirma publicación: revisar web del emisor')
    return base
