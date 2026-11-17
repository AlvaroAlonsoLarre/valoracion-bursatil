"""Fechas y cambios de componentes; reutiliza la misma caché/SQLite de seguimiento."""
import hashlib
import json
from datetime import datetime,timezone,timedelta
from zoneinfo import ZoneInfo,ZoneInfoNotFoundError
import pandas as pd
from auditoria_io import clean


def local_stamp(epoch,zone='UTC'):
    if not epoch:return '—'
    try:tz=ZoneInfo(zone)
    except (ZoneInfoNotFoundError,ValueError,TypeError):tz=timezone.utc
    return datetime.fromtimestamp(float(epoch),timezone.utc).astimezone(tz).strftime('%d/%m/%Y %H:%M:%S %Z')


def quote_ttl(epoch,zone):
    """Horario orientativo, sin fingir un calendario de festivos del mercado."""
    schedules={'America/New_York':(9,30,16,0),'Asia/Seoul':(9,0,15,30),'Europe/London':(8,0,16,30)}
    if zone not in schedules:return 900
    now=datetime.fromtimestamp(epoch,timezone.utc).astimezone(ZoneInfo(zone));oh,om,ch,cm=schedules[zone]
    opening=now.replace(hour=oh,minute=om,second=0,microsecond=0);closing=now.replace(hour=ch,minute=cm,second=0,microsecond=0)
    if now.weekday()<5 and opening<=now<closing:return 900
    # No prolongar un precio de preapertura más allá de la próxima apertura.
    if now.weekday()<5 and now<opening:return max(1,min(3600,int((opening-now).total_seconds())))
    return 21600 if now.weekday()>=5 else 3600


def fingerprint(value):return hashlib.sha256(json.dumps(clean(value),ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')).hexdigest()


def filing_fingerprint(data,as_of):
    recent=data.get('filings',{}).get('recent',{});required=['form','accessionNumber','filingDate','reportDate']
    if not all(isinstance(recent.get(k),list) for k in required):raise ValueError('Submissions SEC incompleto')
    if len({len(recent[k]) for k in required})!=1:raise ValueError('Submissions SEC: columnas no alineadas')
    rows=[];day=str(pd.Timestamp(as_of).date())
    for i,form in enumerate(recent['form']):
        if form not in ['10-Q','10-Q/A','10-K','10-K/A','20-F','20-F/A','40-F','40-F/A','8-K','8-K/A','S-1','S-1/A','10-12B','10-12B/A']:continue
        if recent['filingDate'][i]>day:continue
        if form in ['8-K','8-K/A']:
            items=recent.get('items',[])
            if i>=len(items) or '2.02' not in str(items[i]):continue
        rows.append({k:recent[k][i] for k in required})
    if not rows:raise ValueError('SEC no devuelve presentaciones financieras verificables')
    return {'hash':fingerprint(sorted(rows,key=lambda r:(r['filingDate'],r['accessionNumber']))),'filings':rows}


def normalized_prices(frame):
    d=frame.copy()
    if d.empty:return d
    d.index=pd.to_datetime(d.index).tz_localize(None).normalize()
    return d[~d.index.duplicated(keep='last')].sort_index()


def merge_history(old,new):
    old=normalized_prices(old);new=normalized_prices(new)
    split_change=False
    if 'Stock Splits' in new:
        events=pd.to_numeric(new['Stock Splits'],errors='coerce')
        for date,value in events[(events>0)&(events!=1)].items():
            previous=old.loc[date,'Stock Splits'] if date in old.index and 'Stock Splits' in old else 0
            if pd.isna(previous) or previous!=value:split_change=True
    # Las correcciones de días solapados prevalecen; conservar campos antiguos
    # cuando el nuevo endpoint no los devuelve. Nunca duplicar cierres.
    return new.combine_first(old).sort_index(),split_change
