"""Valoración principal EPS × PER. Importes contables en unidades, tasas decimales.

Cada método decide su suficiencia. La falta de CAPEX, D&A o un WACC no invalida
una proyección de EPS que sí dispone de ingresos, márgenes, impuestos y acciones.
"""
from dataclasses import dataclass
import json
import numpy as np
import pandas as pd
from historico_acciones import number,historical_statistics
from modelo_fundamental import quarterly_snapshot,ttm_yoy
from comparables_inteligentes import score_and_filter
from multiple_evidence import validate_multiple
from estados_datos import public_states,metric_coverage
from revision_economica import qualified_history,recurrent_financial,is_cyclical,cagr,changed_regime

SCENARIOS=('Pesimista','Base','Optimista')
DEFAULT_POLICY={'required_return':.10,'margin_of_safety':.20,'sell_premium':.20,
    'uncertainty_penalty':.10,'max_position_weight':.10,'max_downside':.15}


@dataclass
class StockAnalysis:
    valuation:pd.DataFrame
    projected:pd.DataFrame
    assumptions:pd.DataFrame
    methods:pd.DataFrame
    controls:pd.DataFrame
    summary:dict
    diagnostics:pd.DataFrame
    peers:pd.DataFrame
    universe:pd.DataFrame
    history_statistics:pd.DataFrame
    base_ttm:pd.DataFrame
    settings:dict
    metrics:pd.DataFrame
    qualified_history:pd.DataFrame


def series(frame,column):
    return pd.to_numeric(frame.get(column,pd.Series(index=frame.index,dtype=float)),errors='coerce').replace([np.inf,-np.inf],np.nan)


def median(frame,column,years=5):return number(series(frame.tail(years),column).median())


def sector_type(info):
    text=' '.join(str(info.get(k) or '') for k in ['sector','sectorKey','industry','industryKey']).lower()
    if any(x in text for x in ['reit','real estate investment trust']):return 'REIT'
    if any(x in text for x in ['financial services','financial-services','banks','insurance','capital markets','capital-markets']):return 'FINANCIERA'
    return 'OPERATIVA'


def needs_adr_bridge(info,financial_currency,quote_currency):
    name=str(info.get('longName',''))+' '+str(info.get('shortName',''))
    import re
    return bool(info.get('is_adr') or re.search(r'\b(ADR|ADS|depositary|depositaria)\b',name,re.I)
       or (quote_currency=='USD' and financial_currency!='USD' and info.get('exchange') in ('NYQ','NMS','NGM','NCM','ASE')))


def _range(name,value,lo,hi):
    if isinstance(value,bool):raise ValueError(name+': un booleano no es un importe')
    value=number(value)
    if not np.isfinite(value) or not lo<=value<=hi:raise ValueError(f'{name}: debe estar entre {lo} y {hi}; no finitos no válidos')
    return value


def validate_settings(settings):
    settings=dict(settings or {})
    allowed={'scenarios','per_basis','per_reason','policy','adr','advanced','allow_turnaround','turnaround_reason','optional_assumptions','exploratory_pe'}
    if set(settings)-allowed:raise ValueError('Ajuste desconocido: '+str(set(settings)-allowed))
    if 'exploratory_pe' in settings and not isinstance(settings['exploratory_pe'],bool):raise ValueError('exploratory_pe debe ser booleano')
    scenarios=settings.get('scenarios',{})
    if not isinstance(scenarios,dict) or set(scenarios)-set(SCENARIOS):raise ValueError('Escenarios no válidos')
    bounds={'growth':(-.8,1.),'margin':(-.8,.9),'tax':(0.,.6),'financial_sales':(-.5,.5),'dilution':(-.15,.5),'pe':(.1,200.),'growth_terminal':(-.8,1.),'margin_terminal':(-.8,.9)}
    for name,values in scenarios.items():
        if not isinstance(values,dict) or set(values)-set(bounds):raise ValueError('Campos de escenario no válidos')
        for key,value in values.items():_range(name+' '+key,value,*bounds[key])
    if settings.get('per_basis','TTM') not in ('TTM','NTM'):raise ValueError('Base del PER debe ser TTM o NTM')
    if any('pe' in v for v in scenarios.values()) and not str(settings.get('per_reason','')).strip():
        raise ValueError('El PER manual requiere una justificación explícita')
    if 'allow_turnaround' in settings and not isinstance(settings['allow_turnaround'],bool):raise ValueError('allow_turnaround debe ser booleano')
    adr=settings.get('adr')
    if adr is not None:
        if not isinstance(adr,dict) or set(adr)-{'ordinary_per_quote_share','source','date'}:raise ValueError('Puente ADR no válido')
        _range('Acciones por ADR',adr.get('ordinary_per_quote_share'),.000001,1e6)
        if not isinstance(adr.get('source'),str) or not isinstance(adr.get('date'),str):raise ValueError('ADR requiere fuente y fecha documentadas')
    if settings.get('allow_turnaround') and not str(settings.get('turnaround_reason','')).strip():raise ValueError('Turnaround requiere justificación')
    policy=settings.get('policy',{})
    if not isinstance(policy,dict) or set(policy)-set(DEFAULT_POLICY):raise ValueError('Umbral desconocido')
    for key,value in policy.items():_range(key,value,0.,.8)
    if 'advanced' in settings and not isinstance(settings['advanced'],bool):raise ValueError('advanced debe ser booleano')
    optional=settings.get('optional_assumptions',{})
    if not isinstance(optional,dict) or set(optional)-{'wacc','terminal_growth'}:raise ValueError('Ajuste opcional no válido')
    for key,value in optional.items():_range(key,value,*( (.040001,.299999) if key=='wacc' else (-.009999,.08) ))
    return settings


def _historical_reference(stats,column):
    for window,minimum in [(5,3),(10,5)]:
        rows=stats[stats['Indicador'].eq(column)&stats['Ventana (ejercicios)'].eq(window)]
        if len(rows) and rows.iloc[0]['Observaciones']>=minimum:
            row=rows.iloc[0]
            return [row['P25'],row['Mediana'],row['P75']],f'Histórico propio {window} FY, {int(row["Observaciones"])} observaciones',int(row['Observaciones'])
    return [np.nan]*3,'Histórico propio insuficiente (mínimo 3/5 o 5/10)',0


def _peer_references(selected,as_of,info,ttm_end):
    table=selected.copy();basis=info.get('valuation_accounting_basis');ttm_values=[];forward=[]
    from comparables_ttm import validate_ttm_evidence
    for index,row in table.iterrows():
        ok,value,note=validate_ttm_evidence(row,as_of,ttm_end,basis)
        table.loc[index,'PER TTM verificado']=value if ok else np.nan
        table.loc[index,'Estado PER TTM']=note
        if ok:ttm_values.append((str(row.get('Emisor económico') or row.get('Emisor id') or row['Ticker']).upper(),value))
        valid,pe,errors,_=validate_multiple(row,'PER',as_of,basis)
        table.loc[index,'PER NTM verificado']=pe if valid else np.nan
        table.loc[index,'Estado PER NTM']='Evidencia compatible' if valid else '; '.join(errors)
        if valid:forward.append((str(row.get('Emisor económico') or row.get('Emisor id') or row['Ticker']).upper(),pe))
    def reference(values):
        data=pd.DataFrame(values,columns=['issuer','value']).drop_duplicates('issuer')
        v=data['value']
        # Se rechazan múltiplos extremos y cohorts dispersas; no se fuerza completar tres.
        v=v[(v>=2)&(v<=100)]
        if len(v)<3 or v.max()/v.min()>3.5:return None
        return list(v.quantile([.25,.5,.75]).values),len(v)
    return table,reference(ttm_values),reference(forward)


def evaluate_position(summary,policy=None,position=None):
    """Reglas orientativas: sólo la cotización de hoy interviene en la comparación final."""
    policy={**DEFAULT_POLICY,**(policy or {})}
    for key,value in policy.items():_range(key,value,0.,.8)
    result={'Atractivo':'No evaluable','Decisión':'Sin señal','Margen de seguridad exigido (%)':np.nan,
            'Motivo':'Se necesita una valoración principal válida y evidencia suficiente'}
    fair=number(summary.get('fair_value'));price=number(summary.get('price'))
    ret=number(summary.get('annual_return_3y'));downside=number(summary.get('pessimistic_1y'))
    if summary.get('quote_verified') is False:
        result['Motivo']='Cotización sin fecha admisible; actualizar antes de comparar o decidir'
        return result
    if summary.get('scenario_order_valid') is False:
        result['Motivo']='Escenarios incompletos o no ordenados; revisar supuestos antes de emitir señal'
        return result
    if not (fair>0 and price>0 and np.isfinite(ret)):return result
    penalty=policy['uncertainty_penalty']*(2 if summary.get('confidence')=='Baja' else 1)
    # La dispersión de escenarios aumenta el margen exigido; no cambia los precios calculados.
    width=number(summary.get('scenario_spread'));width=width if np.isfinite(width) else 1.
    margin=min(.8,policy['margin_of_safety']+penalty+min(.2,max(0.,width)*.1))
    safety=1-price/fair
    result.update({'Margen de seguridad exigido (%)':100*margin,'Margen observado (%)':100*safety})
    if summary.get('sector_type') in ('FINANCIERA','REIT'):
        result.update({'Atractivo':'Revisión sectorial','Motivo':'Capital regulatorio o FFO/AFFO/NAV no evaluados; no emitir orden automática'})
        return result
    allowed_downside=max(0.,policy['max_downside']-penalty*.25)
    result['Caída tolerada escenario pesimista (%)']=100*allowed_downside
    if safety>=margin and ret>=policy['required_return'] and np.isfinite(downside) and downside>=price*(1-allowed_downside):
        attraction='Potencialmente atractiva';action='Comprar'
    elif price>fair*(1+policy['sell_premium']+penalty):attraction='Exigente';action='Reducir'
    else:attraction='Zona de vigilancia';action='Mantener'
    result.update({'Atractivo':attraction,'Motivo':'Reglas de valoración y escenarios; no incluye asesoramiento fiscal ni garantiza resultados'})
    if position is not None:
        if set(position)-{'shares','cost_price','portfolio_value'}:raise ValueError('Campo de posición no válido')
        shares=_range('Acciones en posición',position.get('shares',0),0,1e12)
        cost=_range('Precio de coste',position.get('cost_price',0),0,1e12)
        portfolio=_range('Valor de cartera',position.get('portfolio_value',0),0,1e15)
        if shares>0:
            weight=shares*price/portfolio if portfolio>0 else np.nan
            result['Peso posición (%)']=weight*100;result['Plusvalía no realizada']=shares*(price-cost) if cost>0 else np.nan
            if action=='Comprar':action='Ampliar' if np.isfinite(weight) and weight<policy['max_position_weight'] else 'Mantener'
            if np.isfinite(weight) and weight>policy['max_position_weight']:action='Reducir'
            if price>fair*(1+2*(policy['sell_premium']+penalty)):action='Vender'
        elif action!='Comprar':action='No comprar'
        result['Decisión']=action
    return result


def build_stock_analysis(annual,peers,*,price,market_cap,shares_outstanding,financial_currency,quote_currency,
    quarterly=None,as_of=None,fiscal_end_date=None,ticker='',info=None,fx=1.,source='No declarado',history=None,
    settings=None,recent_results_check=None,**unused):
    price=number(price);market_cap=number(market_cap);shares_outstanding=number(shares_outstanding);fx=number(fx)
    settings=validate_settings(settings);info=info or {};today=pd.Timestamp(as_of or pd.Timestamp.now()).tz_localize(None).normalize()
    a=annual.copy().sort_index();controls=[];methods=[]
    def check(scope,name,ok,detail,critical=False):
        controls.append({'Método':scope,'Comprobación':name,'Severidad':'CRITICO' if critical and not ok else 'ADVERTENCIA' if not ok else 'INFO',
            'Estado':'OK' if ok else 'BLOQUEO' if critical else 'REVISAR','Detalle':detail,
            'Estado público':'DISPONIBLE' if ok else 'ADVERTENCIA' if not critical else 'BLOQUEADO' if name in ('Ejercicios fiscales únicos','Precio × acciones = capitalización','Resultados posteriores no incorporados') or (name=='Puente beneficio / acciones diluidas' and 'requiere' in detail and 'nan' not in detail) else 'NO DISPONIBLE'})
    check('Todos','Ejercicios fiscales únicos',not a.index.has_duplicates,'Conservar cierre real y FY de 52/53 semanas; no duplicar años calendario',True)
    if a.index.has_duplicates:a=a[~a.index.duplicated(keep=False)]
    if 'Fecha cierre fiscal' in a:a=a[pd.to_datetime(a['Fecha cierre fiscal'],errors='coerce')<=today]
    raw_annual=a.copy()
    listed=pd.to_datetime(info.get('firstTradeDateMilliseconds'),unit='ms',errors='coerce')
    short_listing=pd.notna(listed) and (today-listed).days<365*5
    perimeter=bool(info.get('valuation_separation_registration')) or any(x in str(info.get('longBusinessSummary','')).lower() for x in ['spin-off','spun off','spun-off'])
    if short_listing:
        check('Histórico','Historia financiera y bursátil',False,f'Primera cotización proveedor {listed.date()}; estados anteriores no crean precios/PER anteriores a cotizar')
    if perimeter and pd.notna(listed):
        check('Normalización','Perímetro anterior a separación',False,'Registro de separación/escisión o descripción del emisor: histórico anterior se conserva pero se excluye de supuestos automáticos hasta acreditar continuidad económica')
        if 'Fecha cierre fiscal' in a:a=a[pd.to_datetime(a['Fecha cierre fiscal'])>=listed]
    ttm,base,q,notes=quarterly_snapshot(quarterly,raw_annual,today,fiscal_end_date)
    for note in notes:check('Por flujo','Integridad trimestral',False,note)
    rev=number(ttm.get('Ingresos'));end=ttm.get('Fecha último trimestre',pd.NaT)
    check('Todos','Ingresos TTM',rev>0,'Cuatro trimestres consecutivos, nunca anualizar un trimestre',True)
    check('Todos','Vigencia TTM',pd.notna(end) and 0<=(today-end).days<=125,'Último trimestre '+str(end)+'; máximo 125 días',True)
    check('Precio EPS','Cotización y FX',number(fx)>0 and bool(financial_currency) and bool(quote_currency),'Divisas '+str(financial_currency)+'→'+str(quote_currency)+'; FX observado o misma moneda',True)
    quote_time=info.get('regularMarketTime')
    quote_date=pd.to_datetime(quote_time,unit='s',utc=True,errors='coerce') if quote_time else pd.to_datetime(info.get('valuation_quote_date'),errors='coerce')
    quote_date=pd.Timestamp(quote_date).tz_localize(None).normalize() if pd.notna(quote_date) else pd.NaT
    quote_ok=pd.notna(quote_date) and 0<=(today-quote_date).days<=7
    check('Cotización','Fecha precio observado',quote_ok,'Fecha '+str(quote_date)+'; sin fecha válida no emitir potencial/retorno ni señal, aunque se puedan proyectar EPS',True)
    market_ok=number(market_cap)>0 and number(shares_outstanding)>0 and number(price)>0 and abs(price*shares_outstanding/market_cap-1)<.10
    implied=number(info.get('impliedSharesOutstanding'))
    implied_ok=implied>0 and number(price)>0 and number(market_cap)>0 and abs(price*implied/market_cap-1)<.10
    # impliedSharesOutstanding acredita sólo el perímetro de mercado del proveedor.
    # Nunca sustituye a la media diluida contable ni se infiere cap/precio como dato.
    check('Capitalización/EV','Precio × acciones = capitalización',market_ok or implied_ok,
          f'Acciones clase={shares_outstanding}; total implícito proveedor={implied}; exige <10% en su perímetro; no usar clase como total emisor',True)
    if not market_ok and implied_ok:check('Capitalización/EV','Perímetro de clases',False,'Yahoo distingue acciones de clase y total implícito del emisor. Para EV se requiere puente consolidado; EPS usa medias diluidas consolidadas')
    freshness=recent_results_check or {}
    check('Todos','Resultados posteriores no incorporados',not freshness.get('newer_filing_confirmed',False) and freshness.get('status')!='BLOQUEO',str(freshness.get('detail','No se ha verificado ausencia de nuevas publicaciones')),True)
    if freshness.get('status')!='VERIFICADO':check('Todos','Actualidad externa',False,'Ausencia de publicaciones posteriores no verificada; no es prueba de desactualización')
    kind=sector_type(info);is_adr=needs_adr_bridge(info,financial_currency,quote_currency);adr_factor=1.
    if is_adr:
        adr=settings.get('adr',{});adr_factor=number(adr.get('ordinary_per_quote_share'))
        adr_date=pd.to_datetime(adr.get('date'),errors='coerce')
        import re
        adr_ok=adr_factor>0 and bool(re.match(r'^https://[^/]+/.+',str(adr.get('source','')))) and pd.notna(adr_date) and adr_date<=today
        check('Precio EPS','Puente ADR/acción',adr_ok,'Requiere acciones ordinarias por ADR, fuente y fecha; no inferir por moneda',True)
    if financial_currency!=quote_currency:check('Histórico','FX histórico',False,'Sin serie FX por cierre no usar múltiplos históricos de distinta moneda')
    diluted=np.nan;diluted_source='N/D'
    if 'Acciones diluidas medias' not in q.attrs.get('invalid_flows',[]) and not q.empty and 'Acciones diluidas medias' in q and number(q.iloc[-1].get('Acciones diluidas medias'))>0:
        diluted=number(q.iloc[-1]['Acciones diluidas medias']);diluted_source='Media diluida del trimestre '+str(end.date())
    elif 'Acciones diluidas medias' not in q.attrs.get('invalid_flows',[]) and len(a) and number(a.iloc[-1].get('Acciones diluidas medias'))>0:
        date=pd.to_datetime(a.iloc[-1].get('Fecha cierre fiscal',fiscal_end_date),errors='coerce')
        if pd.notna(date) and 0<=(today-date).days<=400:
            diluted=number(a.iloc[-1]['Acciones diluidas medias']);diluted_source='Media diluida FY '+str(date.date())
            check('EPS × PER','Acciones diluidas recientes',False,'Sin media diluida del último trimestre; se usa último FY, no acciones básicas')
    check('EPS × PER','Acciones diluidas',diluted>0,diluted_source,True)
    check('EPS × PER','Flujos de resultados',np.isfinite(number(ttm.get('Beneficio neto'))) and (kind=='FINANCIERA' or np.isfinite(number(ttm.get('Beneficio operativo'))) or series(a,'Beneficio antes de impuestos').tail(5).notna().sum()>=3),
          'TTM de neto y EBIT (PBT/margen neto para financieras); sin sustitución por FY',True)
    history_qualified=qualified_history(raw_annual,history if history is not None else pd.DataFrame(),info,kind=='FINANCIERA')
    stats=historical_statistics(raw_annual,history_qualified)
    if changed_regime(raw_annual):check('Histórico','Cambio de régimen económico',False,'Margen de últimos 3 FY cambia ≥2× y ≥5 pp frente a los 3 anteriores; no completar el PER con régimen anterior')
    eligible,_,_,_,universe=score_and_filter(peers,ticker,target_info=info,return_universe=True,max_peers=6,as_of=today)
    selected,peer_ttm,peer_forward=_peer_references(eligible,today,info,end)
    own_pes,own_note,own_count=_historical_reference(stats,'PER histórico')
    per_basis='TTM';confidence='Baja';per_note=own_note;pes=own_pes
    if not own_count and peer_ttm:pes,per_count=peer_ttm;confidence='Media';per_note=f'{per_count} comparables económicos TTM homogéneos'
    if not own_count and not peer_ttm and peer_forward:pes,per_count=peer_forward;confidence='Media';per_note=f'{per_count} comparables económicos NTM verificados';per_basis='NTM'
    exploratory_used=False
    if not all(number(v)>0 for v in pes) and settings.get('exploratory_pe') and len(raw_annual) and not history_qualified.empty:
        good=history_qualified[history_qualified['PER admisible económicamente'].eq(True)]
        for window in [5,10]:
            recent=good[good['Ejercicio']>int(raw_annual.index.max())-window]
            if len(recent)==2:
                v=pd.to_numeric(recent['PER histórico'],errors='coerce');med=number(v.median())
                pes=[min(v.min(),med*.8),med,max(v.max(),med*1.2)]
                per_note=f'Exploratoria: 2 PER limpios en {window} FY; banda de sensibilidad al menos ±20%, no cuartiles precisos'
                per_basis='TTM';confidence='Baja';exploratory_used=True
                break
    if any('pe' in row for row in settings.get('scenarios',{}).values()):
        # Cada PER manual se identifica; no se convierte una etiqueta FY1 en un forecast NTM.
        exploratory_used=False
        per_basis=settings.get('per_basis','TTM');confidence='Baja';per_note='PER manual: '+settings['per_reason']
    check('Precio EPS','Referencia PER',all(number(x)>0 for x in pes) or any('pe' in row for row in settings.get('scenarios',{}).values()),per_note,True)
    if confidence=='Baja':check('EPS × PER','Confianza de múltiplo',False,per_note+'; referencia retrospectiva/manual, no consenso')
    # Mediana del resultado no operativo PBT−EBIT; no afirmar que es interés puro.
    revenues=series(a,'Ingresos');operating=series(a,'Beneficio operativo');pretax=series(a,'Beneficio antes de impuestos')
    net=series(a,'Beneficio neto');eps=series(a,'EPS diluido');shares=series(a,'Acciones diluidas medias')
    common=series(a,'Beneficio neto común').fillna(net)
    attribution=(eps*shares/net.where(net.abs()>0)).tail(5).replace([np.inf,-np.inf],np.nan).dropna()
    common_ratio=number(attribution.median())
    attribution_ok=len(attribution)>=2 and .5<common_ratio<1.1 and (attribution.quantile(.75)-attribution.quantile(.25))<.10
    check('EPS × PER','Puente beneficio / acciones diluidas',attribution_ok,
          f'Mediana EPS × acciones / neto = {common_ratio}; requiere ≥2 FY y dispersión intercuartílica <0.10',True)
    pbt_direct=kind=='FINANCIERA' or operating.tail(5).notna().sum()<3
    if pbt_direct and kind=='OPERATIVA':check('EPS × PER','Margen PBT directo',False,'El emisor no publica una serie EBIT suficiente. Se proyecta PBT normalizado con financiero incluido, sin inventar EBIT ni intereses')
    profit_margin=(pretax/revenues).tail(5).median() if pbt_direct else (operating/revenues).tail(5).median()
    financial,financial_note=recurrent_financial(a,kind=='FINANCIERA')
    if pbt_direct:financial=0.;financial_note='Incluido en PBT directo; no extraer intereses operativos de financieras'
    check('EPS × PER','Recurrencia resultado no operativo',False,financial_note)
    tax_values=(series(a,'Impuestos')/pretax.where(pretax>0)).tail(5)
    # Tasa publicada sólo si es económicamente interpretable; ausencia no equivale a 25% supuesto.
    tax=number(tax_values[(tax_values>=0)&(tax_values<=.6)].median())
    valid_rev=revenues.tail(4)
    growth=np.nan
    if len(valid_rev)>=2 and valid_rev.iloc[0]>0 and valid_rev.iloc[-1]>0:
        span=int(valid_rev.index[-1])-int(valid_rev.index[0])
        if span>0:growth=(valid_rev.iloc[-1]/valid_rev.iloc[0])**(1/span)-1
    yoy=ttm_yoy(q,'Ingresos')
    if np.isfinite(yoy) and np.isfinite(growth):growth=(growth+yoy)/2
    # Cada observación tiene su propia base: los splits no son dilución económica.
    if history is not None and not history.empty and 'Factor split acciones' in history:
        factors=history.drop_duplicates('Ejercicio',keep=False).set_index('Ejercicio')['Factor split acciones'].reindex(a.index)
        shares=shares*pd.to_numeric(factors,errors='coerce')
    intervals=pd.Series(a.index,index=a.index).diff()
    diluted_growth=((shares/shares.shift(1))**(1/intervals.where(intervals>0))-1).tail(3).dropna()
    dilution=number(diluted_growth.median())
    # Se permite proyectar la tendencia de acciones medias, sin afirmar cancelaciones realizadas.
    cyclical=is_cyclical(info)
    exceptional=np.isfinite(growth) and growth>.25
    short_growth=cagr(a,5);normal_growth=cagr(a,10)
    if (cyclical or exceptional) and np.isfinite(short_growth):growth=short_growth
    terminal_growth=min(growth,normal_growth) if (cyclical or exceptional) and np.isfinite(normal_growth) and np.isfinite(growth) else growth
    auto={'growth':growth,'margin':number(profit_margin),'tax':tax,'financial_sales':number(financial),'dilution':dilution,
          'growth_terminal':terminal_growth,'margin_terminal':number(profit_margin)}
    if any('pe' in row for row in settings.get('scenarios',{}).values()) and per_basis=='NTM' and not all('pe' in settings.get('scenarios',{}).get(n,{}) for n in SCENARIOS):
        raise ValueError('Para cambiar la base del PER a NTM se necesitan los tres PER explícitos; no renombrar el histórico TTM')
    variations={'Pesimista':{'growth':-.05,'margin':-.03,'tax':.02,'financial_sales':-.005,'dilution':.01},
                'Base':{},'Optimista':{'growth':.05,'margin':.03,'tax':-.02,'financial_sales':.005,'dilution':-.005}}
    assumptions=[];projected=[];valued=[]
    ttm_eps=number(ttm.get('EPS diluido'))
    turnaround=bool(settings.get('allow_turnaround'))
    check('Precio EPS','EPS TTM positivo',ttm_eps>0 or (not np.isfinite(ttm_eps) and number(ttm.get('Beneficio neto'))>0 and attribution_ok) or turnaround,'EPS TTM '+str(ttm_eps)+'; si falta EPS se comprueba el signo del neto TTM con puente común FY; EPS negativo requiere turnaround explícito',True)
    if kind=='REIT':check('Precio EPS','Modelo sectorial REIT',False,'EPS/PER no representa FFO/AFFO. Se requiere NAV/FFO documentado; no sumar D&A arbitrariamente',True)
    if kind=='FINANCIERA':check('EPS × PER','Modelo sectorial financiera',False,'Proyección por margen PBT (resultado financiero incluido); revisar CET1, provisiones y capital regulatorio. FCFF/EV/FCF no aplicables')
    if cyclical or exceptional:
        check('EPS × PER','Ciclo económico',False,'Ciclo/crecimiento excepcional: CAGR hasta 5 FY → menor de CAGR 5/10 FY al año 3; margen normalizado mediana hasta 5 FY desde año 1. Hipótesis, no consenso')
    for i,name in enumerate(SCENARIOS):
        values={key:(v+variations[name].get(key,0)) for key,v in auto.items()}
        # La banda impositiva no supone reembolsos o tipos negativos.
        if np.isfinite(values['tax']):values['tax']=min(.6,max(0.,values['tax']))
        if pbt_direct:values['financial_sales']=0.
        values['pe']=pes[i]
        custom=settings.get('scenarios',{}).get(name,{})
        if pbt_direct and custom.get('financial_sales',0)!=0:raise ValueError('El margen PBT ya incluye el resultado financiero; no sumarlo de nuevo')
        # No volver a extrapolar el margen TTM de pico sobre ingresos TTM ya elevados.
        values['growth_terminal']=auto['growth_terminal']+variations[name].get('growth',0)
        values['margin_terminal']=auto['margin_terminal']+variations[name].get('margin',0)
        values.update(custom)
        # Un override de nivel sin extremo mantiene la trayectoria constante elegida.
        for start,terminal in [('growth','growth_terminal'),('margin','margin_terminal')]:
            if start in custom and terminal not in custom:values[terminal]=values[start]
        if any(number(v)>0 for v in [values['pe']]) and name=='Base' and (values['growth']>.25 or values['margin']>.5):
            check('EPS × PER','Supuestos exigentes',False,'Crecimiento >25% o margen >50%; no es previsión verificada')
        for key,value in values.items():assumptions.append({'Escenario':name,'Parámetro':key,'Valor':value,
             'Origen':'Usuario' if key in custom else per_note if key=='pe' else 'Incluido en PBT; no sumar financiero dos veces' if key=='financial_sales' and pbt_direct else financial_note if key=='financial_sales' else 'CAGR compuesto de hasta 5/10 FY; menor extremo al año 3' if key in ('growth','growth_terminal') and (cyclical or exceptional) else 'Margen normalizado mediana hasta 5 FY' if key in ('margin','margin_terminal') else 'Calculado del histórico; ajuste escenario '+str(variations[name].get(key,0)),
             'Definición':'Margen PBT; incluye financiero' if key=='margin' and pbt_direct else 'Resultado no operativo recurrente / ventas; ver Origen' if key=='financial_sales' else 'Tasa decimal salvo PER en veces'})
        bounds={'growth':(-.8,1.),'margin':(-.8,.9),'tax':(0,.6),'financial_sales':(-.5,.5),'dilution':(-.15,.5),'pe':(.1,200.),'growth_terminal':(-.8,1.),'margin_terminal':(-.8,.9)}
        valid={key:np.isfinite(number(v)) and bounds[key][0]<=v<=bounds[key][1] for key,v in values.items()}
        check('EPS × PER',name+' supuestos',all(v for k,v in valid.items() if k!='pe'),'Fuera de rango/ausentes: '+', '.join(k for k,v in valid.items() if not v),True)
        blocked=any(c['Estado']=='BLOQUEO' and c['Método'] in ('Todos','EPS × PER') and not any(n+' supuestos'==c['Comprobación'] for n in SCENARIOS) for c in controls)
        paths={}
        if all(v for k,v in valid.items() if k!='pe') and not blocked:
            sales=rev
            for h in [1,2,3,4]:
                weight=min(1.,(h-1)/2)
                g=values['growth']+(values['growth_terminal']-values['growth'])*weight
                margin=values['margin']+(values['margin_terminal']-values['margin'])*weight
                sales*=1+g;op=sales*margin
                pbt=op if pbt_direct else op+sales*values['financial_sales']
                profit=(pbt-max(0.,pbt)*values['tax'])*common_ratio
                diluted_future=diluted*(1+values['dilution'])**h
                eps_future=profit/diluted_future
                paths[h]={'Escenario':name,'Año futuro':h,'Crecimiento aplicado':g,'Margen aplicado':margin,'Ingresos':sales,'EBIT o PBT directo':op,
                    'Resultado no operativo':0. if pbt_direct else sales*values['financial_sales'],
                    'PBT':pbt,'Impuestos':max(0.,pbt)*values['tax'],'Beneficio común normalizado':profit,
                    'Acciones diluidas':diluted_future,'EPS financiero':eps_future,'Moneda':financial_currency}
                projected.append(paths[h])
        for h in [1,3]:
            eps_year=h+1 if per_basis=='NTM' else h
            future=paths.get(eps_year,{})
            price_blocked=any(c['Estado']=='BLOQUEO' and c['Método'] in ('Todos','Precio EPS') for c in controls)
            ef=number(future.get('EPS financiero'));target=ef*values['pe']*fx*adr_factor if ef>0 and valid['pe'] and not price_blocked else np.nan
            valued.append({'Método':'EPS × PER','Escenario':name,'Horizonte (años)':h,'Precio objetivo':target,
                'Moneda':quote_currency,'EPS aplicado':ef,'Moneda EPS':financial_currency,'PER aplicado':values['pe'],
                'Periodo PER':per_basis,'Periodo EPS':f'Año {eps_year}: '+('NTM posterior al horizonte' if per_basis=='NTM' else '12 meses hasta horizonte'),
                'Origen PER':per_note,'Potencial (%)':100*(target/price-1) if number(price)>0 and quote_ok else np.nan,
                'Rentabilidad anualizada (%)':100*((target/price)**(1/h)-1) if target>0 and price>0 and quote_ok else np.nan,
                'Confianza':confidence,'Estado':'ESTIMADO' if target>0 else 'NO DISPONIBLE','Fecha objetivo':str((today+pd.DateOffset(years=h)).date()),
                'Limitación':('Exploratoria con 2 PER; ' if exploratory_used else '')+'Sensibilidad sin probabilidades; sin dividendos, costes ni impuestos personales'})
    valuation=pd.DataFrame(valued)
    eps_ok=int(valuation['Precio objetivo'].notna().sum())>0
    eps_notes='Datos contables suficientes; hipótesis pendientes de validación económica' if eps_ok else '; '.join(c['Comprobación'] for c in controls if c['Estado']=='BLOQUEO' and c['Método'] in ('Todos','EPS × PER','Precio EPS'))
    methods.append({'Método':'EPS × PER','Rol':'Principal','Estado':'ESTIMADO' if eps_ok else 'NO DISPONIBLE','Detalle':eps_notes})
    fcf_pes,fcf_note,_=_historical_reference(stats,'Precio/FCF histórico')
    fcf=number(ttm.get('Flujo de caja libre'));fcf_hist=series(a,'Flujo de caja libre').tail(5)
    fcf_conversion=fcf/number(ttm.get('Beneficio neto')) if number(ttm.get('Beneficio neto'))>0 else np.nan
    fcf_ok=(kind=='OPERATIVA' and fcf>0 and (fcf_hist>0).sum()>=3 and .5<=fcf_conversion<=2 and diluted>0 and all(number(x)>0 for x in fcf_pes)
            and number(fx)>0 and adr_factor>0 and not any(c['Estado']=='BLOQUEO' and c['Método']=='Todos' for c in controls) and 'CAPEX' not in q.attrs.get('invalid_flows',[]))
    methods.append({'Método':'Precio/FCF','Rol':'Contraste','Estado':'CONDICIONAL' if fcf_ok else 'NO_REPRESENTATIVO',
        'Detalle':f'FCF=OCF−CAPEX completo; conversión FCF/neto {fcf_conversion}; mínimo 3 FY positivos; '+fcf_note+'; no confundir P/FCF con EV/FCF'})
    if fcf_ok:
        # Contraste actual, sin vender una extrapolación automática del FCF como previsión.
        valuation.loc[len(valuation)]={'Método':'Precio/FCF','Escenario':'Base','Horizonte (años)':0,
            'Precio objetivo':fcf/diluted*fcf_pes[1]*fx*adr_factor,'Moneda':quote_currency,'Confianza':'Baja','Estado':'CONDICIONAL',
            'Origen PER':fcf_note,'Limitación':'Contraste sobre FCF TTM representativo; no flujo futuro ni equity cash flow distribuible verificado'}
    for method in ['EV/EBITDA','DCF']:
        methods.append({'Método':method,'Rol':'Opcional','Estado':'SOLICITADO' if settings.get('advanced') and kind=='OPERATIVA' else 'NO_EJECUTADO',
            'Detalle':'Controles propios; nunca invalidan EPS × PER' if kind=='OPERATIVA' else 'No aplicar FCFF/EV genérico a financieras o REIT'})
    summary={'ticker':ticker,'as_of':str(today.date()),'price':number(price),'quote_date':str(quote_date.date()) if pd.notna(quote_date) else None,'quote_verified':bool(quote_ok),'currency':quote_currency,'financial_currency':financial_currency,
        'exploratory_pe':exploratory_used,'per_mode':'Manual' if any('pe' in v for v in settings.get('scenarios',{}).values()) else 'Exploratoria' if exploratory_used else 'Automático','per_share_fx':fx*adr_factor,'confidence':confidence,'sector_type':kind,'profit_model':'PBT directo' if pbt_direct else 'EBIT + no operativo','revenue_ttm':rev,'diluted_base':diluted,'diluted_source':diluted_source,
        'fair_value':np.nan,'target_1y':np.nan,'target_3y':np.nan,'upside_1y':np.nan,'annual_return_3y':np.nan,
        'pessimistic_1y':np.nan,'scenario_spread':np.nan,'publicable':False,'source':source,'per_source':per_note}
    base_values=valuation[valuation['Método'].eq('EPS × PER')&valuation['Escenario'].eq('Base')]
    for h,key in [(1,'target_1y'),(3,'target_3y')]:
        row=base_values[base_values['Horizonte (años)'].eq(h)]
        if len(row):summary[key]=number(row.iloc[0]['Precio objetivo'])
    policy={**DEFAULT_POLICY,**settings.get('policy',{})}
    # Valor razonable hoy: precio Base a 1 año descontado al retorno exigido editable.
    summary['fair_value']=summary['target_1y']/(1+policy['required_return'])
    if number(price)>0 and quote_ok:
        summary['upside_1y']=summary['target_1y']/price-1
        summary['annual_return_3y']=(summary['target_3y']/price)**(1/3)-1 if summary['target_3y']>0 else np.nan
    one=valuation[valuation['Método'].eq('EPS × PER')&valuation['Horizonte (años)'].eq(1)]
    if len(one):
        summary['pessimistic_1y']=number(one[one['Escenario'].eq('Pesimista')].iloc[0]['Precio objetivo'])
        summary['scenario_spread']=(one['Precio objetivo'].max()-one['Precio objetivo'].min())/summary['target_1y'] if summary['target_1y']>0 else np.nan
    scenario_prices=one.set_index('Escenario')['Precio objetivo'].reindex(SCENARIOS) if len(one) else pd.Series(dtype=float)
    summary['scenario_order_valid']=bool(all(len(v:=valuation[valuation['Método'].eq('EPS × PER')&valuation['Horizonte (años)'].eq(h)].set_index('Escenario')['Precio objetivo'].reindex(SCENARIOS))==3 and v.notna().all() and v.is_monotonic_increasing for h in [1,3]))
    if not summary['scenario_order_valid']:check('Señales','Coherencia de escenarios',False,'Tres escenarios válidos y ordenados requeridos para clasificar atractivo')
    summary.update(evaluate_position(summary,policy))
    debt=number(ttm.get('Deuda neta reciente'));ebit=number(ttm.get('Beneficio operativo'))
    diagnostics=pd.DataFrame([
        {'Diagnóstico':'Crecimiento','Lectura':'Expansión' if growth>0 else 'Contracción' if np.isfinite(growth) else 'N/D','Valor':growth,'Detalle':'CAGR compuesto hasta 5 FY, con extremo hasta 10 FY; no consenso' if cyclical or exceptional else 'CAGR de últimos hasta 4 FY y TTM interanual si completo; no consenso'},
        {'Diagnóstico':'Rentabilidad','Lectura':'Positiva' if profit_margin>0 else 'Débil' if np.isfinite(profit_margin) else 'N/D','Valor':profit_margin,'Detalle':'Mediana de margen '+('PBT directo' if pbt_direct else 'EBIT')+' de hasta 5 FY'},
        {'Diagnóstico':'Solidez financiera','Lectura':'Revisión sectorial' if kind!='OPERATIVA' else 'Caja neta' if debt<0 else 'Revisar deuda' if debt>3*ebit else 'Deuda moderada' if np.isfinite(debt) and ebit>0 else 'N/D',
         'Valor':debt/ebit if ebit>0 and np.isfinite(debt) else np.nan,'Detalle':'Deuda neta/EBIT orientativo; no sustituye vencimientos/liquidez; bancos requieren capital regulatorio'},
        {'Diagnóstico':'Valoración','Lectura':summary['Atractivo'],'Valor':summary['upside_1y'],'Detalle':'EPS proyectado × PER; incertidumbre reflejada en margen exigido'}])
    diagnostics['Estado']=['DISPONIBLE' if pd.notna(v) else 'NO DISPONIBLE' for v in diagnostics['Valor']]
    diagnostics.loc[diagnostics['Diagnóstico'].eq('Valoración')&diagnostics['Valor'].notna(),'Estado']='ESTIMADO'
    summary['available_targets']=int(valuation['Precio objetivo'].notna().sum());summary['primary_available']=eps_ok
    conflicts={field for field,dates in q.attrs.get('field_conflicts',{}).items() if any(pd.Timestamp(d) in q.tail(4).index for d in dates)}
    metrics=metric_coverage(ttm,raw_annual,summary,set(q.attrs.get('invalid_flows',[]))|conflicts)
    summary['metrics_available_pct']=100*metrics['Valor'].notna().mean()
    return StockAnalysis(public_states(valuation),pd.DataFrame(projected),pd.DataFrame(assumptions),public_states(pd.DataFrame(methods)),pd.DataFrame(controls).assign(Estado=lambda x:x['Estado público']).drop(columns='Estado público'),
                         summary,diagnostics,selected,universe,stats,base,settings,metrics,history_qualified)
