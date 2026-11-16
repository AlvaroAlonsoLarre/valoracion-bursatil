"""Persistencia local transaccional y caché de datos públicos, nunca pickle."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import time
import pandas as pd
from auditoria_io import clean,frame_payload,restore_frame

TTL={'quote':900,'financial':86400,'history':604800,'peers':259200,'search':3600,'submissions':3600}


def storage_path():
    from platformdirs import user_data_path
    return Path(os.environ['VALUACION_WATCHLIST_DIR']) if os.environ.get('VALUACION_WATCHLIST_DIR') else user_data_path('ValoracionBursatil',appauthor=False)/'seguimiento'


def ticker_key(value):
    key=str(value).strip().upper()
    if not re.fullmatch(r'[A-Z0-9][A-Z0-9.\-^=]{0,24}',key):raise ValueError('Ticker no válido')
    return key


def dumps(value):return json.dumps(clean(value),ensure_ascii=False,allow_nan=False,separators=(',',':'))


class Store:
    def __init__(self,path=None,clock=time.time):
        self.path=Path(path) if path is not None else storage_path()
        self.path.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.db=self.path/'seguimiento.sqlite3';self.clock=clock
        with self.connection() as c:
            c.executescript('''CREATE TABLE IF NOT EXISTS companies(ticker TEXT PRIMARY KEY,name TEXT NOT NULL,exchange TEXT,created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS analyses(ticker TEXT PRIMARY KEY REFERENCES companies(ticker) ON DELETE CASCADE,payload TEXT NOT NULL,metrics TEXT NOT NULL,updated REAL NOT NULL,attempted REAL NOT NULL,error TEXT);
            CREATE TABLE IF NOT EXISTS cache(key TEXT PRIMARY KEY,value TEXT NOT NULL,expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS failures(key TEXT PRIMARY KEY,detail TEXT NOT NULL,attempted REAL NOT NULL);''')
            c.execute('CREATE TABLE IF NOT EXISTS preferences(key TEXT PRIMARY KEY,value TEXT NOT NULL)')

    def preferences(self):
        with self.connection() as c:row=c.execute("SELECT value FROM preferences WHERE key='columns'").fetchone()
        return json.loads(row[0]) if row else None

    def set_preferences(self,columns):
        with self.connection() as c:c.execute("INSERT OR REPLACE INTO preferences VALUES('columns',?)",(dumps(columns),))

    @contextmanager
    def connection(self):
        c=sqlite3.connect(self.db,timeout=30)
        c.execute('PRAGMA foreign_keys=ON');c.execute('PRAGMA busy_timeout=30000')
        try:
            with c:yield c
        finally:c.close()

    def add(self,ticker,name='',exchange=''):
        ticker=ticker_key(ticker)
        with self.connection() as c:
            c.execute('INSERT OR IGNORE INTO companies VALUES(?,?,?,?)',(ticker,name or ticker,exchange,self.clock()))
            return c.execute('SELECT changes()').fetchone()[0]==1

    def remove(self,ticker):
        with self.connection() as c:c.execute('DELETE FROM companies WHERE ticker=?',(ticker_key(ticker),))

    def entries(self):
        with self.connection() as c:
            c.row_factory=sqlite3.Row
            rows=c.execute('SELECT c.*,a.payload,a.metrics,a.updated,a.attempted,a.error FROM companies c LEFT JOIN analyses a USING(ticker) ORDER BY c.created,c.ticker').fetchall()
        return [{**dict(row),'payload':json.loads(row['payload']) if row['payload'] else None,'metrics':json.loads(row['metrics']) if row['metrics'] else {}} for row in rows]

    def entry(self,ticker):return next((r for r in self.entries() if r['ticker']==ticker_key(ticker)),None)

    def save(self,ticker,payload,metrics,error=None):
        ticker=ticker_key(ticker);now=self.clock()
        with self.connection() as c:
            c.execute('INSERT INTO analyses VALUES(?,?,?,?,?,?) ON CONFLICT(ticker) DO UPDATE SET payload=excluded.payload,metrics=excluded.metrics,updated=excluded.updated,attempted=excluded.attempted,error=excluded.error',(ticker,dumps(payload),dumps(metrics),now,now,error))

    def failed(self,ticker,error):
        with self.connection() as c:c.execute("INSERT INTO analyses VALUES(?,'null','{}',0,?,?) ON CONFLICT(ticker) DO UPDATE SET attempted=excluded.attempted,error=excluded.error",(ticker_key(ticker),self.clock(),str(error)[:1500]))

    def cached(self,key,fetch,ttl,force=False):
        digest=hashlib.sha256(key.encode('utf-8')).hexdigest()
        with self.connection() as c:
            row=c.execute('SELECT value,expires FROM cache WHERE key=?',(digest,)).fetchone()
            failed=c.execute('SELECT 1 FROM failures WHERE key=?',(digest,)).fetchone()
        if row and row[1]>self.clock() and not force and not failed:
            try:
                value=self.decode(json.loads(row[0]))
                if not isinstance(value,(pd.DataFrame,pd.Series)) or not value.empty:return value
            except (ValueError,TypeError,KeyError):pass  # Caché incompatible: volver a obtenerla, sin tocar la última captura.
        try:
            value=fetch()
            if isinstance(value,(pd.DataFrame,pd.Series)) and value.empty:raise ValueError('Respuesta financiera/histórica vacía; no se guarda como descarga válida')
            encoded=dumps(self.encode(value))
        except Exception as exc:
            from entorno_ejecucion import network_diagnostic
            with self.connection() as c:c.execute('INSERT OR REPLACE INTO failures VALUES(?,?,?)',(digest,network_diagnostic(exc,'SEC' if 'sec.gov' in key else 'Yahoo'),self.clock()))
            raise
        with self.connection() as c:
            c.execute('INSERT OR REPLACE INTO cache VALUES(?,?,?)',(digest,encoded,self.clock()+ttl))
            c.execute('DELETE FROM failures WHERE key=?',(digest,))
        return self.decode(json.loads(encoded))

    def errors_since(self,since):
        with self.connection() as c:return [r[0] for r in c.execute('SELECT DISTINCT detail FROM failures WHERE attempted>=?',(since,))]

    @staticmethod
    def encode(value):
        if isinstance(value,pd.DataFrame):
            original=value;value=value.copy();tz=None
            if isinstance(value.index,pd.DatetimeIndex) and value.index.tz is not None:
                tz=str(value.index.tz);value.index=value.index.tz_convert('UTC')
            return {'type':'frame','value':frame_payload(value),'tz':tz,'index_frequency':original.index.freqstr if isinstance(original.index,pd.DatetimeIndex) else None,'datetime_columns':isinstance(original.columns,pd.DatetimeIndex),'columns_name':original.columns.name}
        if isinstance(value,pd.Series):return {'type':'series','value':Store.encode(value.to_frame()),'name':value.name}
        return {'type':'json','value':value}

    @staticmethod
    def decode(value):
        if value['type']=='frame':
            frame=restore_frame(value['value'])
            if value.get('tz'):frame.index=frame.index.tz_convert(value['tz'])
            if value.get('index_frequency'):frame.index=pd.DatetimeIndex(frame.index,freq=value['index_frequency'])
            if value.get('datetime_columns'):frame.columns=pd.to_datetime(frame.columns)
            frame.columns.name=value.get('columns_name');return frame
        if value['type']=='series':
            f=Store.decode(value['value']) if 'type' in value['value'] else restore_frame(value['value'])
            s=f.iloc[:,0];s.name=value.get('name');return s
        return value['value']
