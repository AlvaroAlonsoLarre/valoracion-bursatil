"""Adaptador opt-in de consultas V7; conserva datos y controles del motor."""
import json
import os
from seguimiento_store import Store,TTL


class Lazy:
    def __init__(self,factory):self.factory=factory;self.value=None
    def __getattr__(self,name):
        if self.value is None:self.value=self.factory()
        return getattr(self.value,name)


class CachedObject:
    def __init__(self,obj,store,key,ttl,force=False):self.obj=obj;self.store=store;self.key=key;self.ttl=ttl;self.force=force
    def __getattr__(self,name):
        if name.startswith('_'):return getattr(self.obj,name)
        if name=='fast_info':
            outer=self
            class Fast:
                def get(self,key,default=None):return outer.store.cached(outer.key+':fast:'+key,lambda:outer.obj.fast_info.get(key,default),TTL['quote'],outer.force)
            return Fast()
        methods={'history','get_info','get_income_stmt','get_balance_sheet','get_cash_flow','get_sec_filings'}
        properties={'info','income_stmt','balance_sheet','cashflow','cash_flow','quarterly_income_stmt','quarterly_balance_sheet','quarterly_cashflow','quarterly_cash_flow','sec_filings','quotes','top_companies'}
        if name not in methods|properties:return getattr(self.obj,name)
        def fetch(*args,**kwargs):
            ttl=TTL['history'] if name=='history' and kwargs.get('period')=='max' else TTL['quote'] if name=='history' else self.ttl
            key=json.dumps([self.key,name,args,kwargs],sort_keys=True,default=str)
            if name!='history':key+=':ttl='+str(ttl)  # El objetivo usa 24 h aunque antes figurase como peer a 72 h.
            return self.store.cached(key,lambda:getattr(self.obj,name)(*args,**kwargs) if name in methods else getattr(self.obj,name),ttl,self.force)
        return fetch if name in methods else fetch()


class CachedYahoo:
    def __init__(self,yf,path,target,force=False):self.yf=yf;self.store=Store(path);self.target=target;self.force=force
    def __getattr__(self,name):return getattr(self.yf,name)
    def Ticker(self,symbol,*args,**kwargs):
        return CachedObject(self.yf.Ticker(symbol,*args,**kwargs),self.store,'Ticker:'+symbol,TTL['financial'] if symbol==self.target else TTL['peers'],self.force)
    def Search(self,query,*args,**kwargs):
        from types import SimpleNamespace
        key='Search:'+json.dumps([query,args,kwargs],sort_keys=True,default=str)
        return SimpleNamespace(quotes=self.store.cached(key,lambda:self.yf.Search(query,*args,**kwargs).quotes,TTL['search'],self.force))
    def Industry(self,key,*args,**kwargs):return CachedObject(Lazy(lambda:self.yf.Industry(key,*args,**kwargs)),self.store,'Industry:'+str((key,args,kwargs)),TTL['peers'],self.force)
    def Sector(self,key,*args,**kwargs):return CachedObject(Lazy(lambda:self.yf.Sector(key,*args,**kwargs)),self.store,'Sector:'+str((key,args,kwargs)),TTL['peers'],self.force)


def cached_sec(url,fetch):
    path=os.environ.get('VALUACION_SOURCE_CACHE')
    if not path:return fetch()
    ttl=TTL['submissions'] if 'submissions/' in url else TTL['history'] if 'company_tickers' in url else TTL['financial']
    return Store(path).cached('SEC:'+url,fetch,ttl,os.environ.get('VALUACION_SOURCE_FORCE')=='1')
