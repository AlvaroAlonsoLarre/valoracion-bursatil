# -*- coding: utf-8 -*-
"""Motor fundamental multiempresa V3: TTM real, puente del año fiscal, FCFF y comparables.

Entradas monetarias en UNIDADES de la divisa contable, no en miles de millones.
Los múltiplos de mercado se calculan en divisa de cotización tras FX explícito.
La valoración es un análisis de sensibilidad condicional, no consenso/objetivo garantizado.
"""
from __future__ import annotations
from dataclasses import dataclass, field
import os
import math
import numpy as np
import pandas as pd
from comparables_inteligentes import score_and_filter, load_config


def f(x):
    try:
        y=float(x)
        return y if np.isfinite(y) else np.nan
    except (ValueError,TypeError): return np.nan


def ratio(a,b):
    a,b=f(a),f(b)
    return a/b if np.isfinite(a) and np.isfinite(b) and b!=0 else np.nan


def med(series,n=3,positive=False):
    s=pd.to_numeric(pd.Series(series),errors='coerce').dropna().tail(n)
    if positive:s=s[s>0]
    return f(s.median()) if len(s) else np.nan


def bound(x,low,high):
    v=f(x)
    return float(np.clip(v,low,high)) if np.isfinite(v) else np.nan


def env_float(key,default):
    try:
        s=os.environ.get('VALUACION_'+key,'').strip().replace(',','.')
        return float(s) if s else default
    except (TypeError,ValueError):return default


def fx_rate(fin_currency,quote_currency,fetcher=None):
    def unit(value):
        raw=str(value or '').strip()
        if raw=='GBp' or raw.upper() in ('GBX','GBPENCE'):return 'GBP',.01
        return raw.upper(),1.
    a,au=unit(fin_currency);b,bu=unit(quote_currency)
    if a==b and a:return au/bu,'mismas monedas; factor de unidad '+str(au/bu)
    if not a or not b or fetcher is None:return np.nan,'No hay divisas o consulta FX'
    for pair,inv in ((a+b+'=X',False),(b+a+'=X',True)):
        try:
            val=f(fetcher(pair))
            if np.isfinite(val) and val>0:return (1/val if inv else val)*au/bu,pair+(' inverso' if inv else '')+'; factor unidad '+str(au/bu)
        except Exception:pass
    return np.nan,'FX ausente; objetivos bloqueados'


@dataclass
class FundamentalResult:
    assumptions:pd.DataFrame
    projected:pd.DataFrame
    valuation:pd.DataFrame
    dcf_detail:pd.DataFrame
    checks:pd.DataFrame
    peers:pd.DataFrame
    roic:pd.DataFrame
    reverse:pd.DataFrame
    fiscal_bridge:pd.DataFrame
    base_ttm:pd.DataFrame
    peer_reference:pd.DataFrame
    peer_universe:pd.DataFrame = field(default_factory=pd.DataFrame)
    risk_parameters:pd.DataFrame = field(default_factory=pd.DataFrame)
    roic_ttm:pd.DataFrame = field(default_factory=pd.DataFrame)
    peer_definitions:pd.DataFrame = field(default_factory=pd.DataFrame)


def quarterly_snapshot(quarterly,annual,as_of,fiscal_end_date=None):
    """Serie financiera real; TTM únicamente si 4 cierres trimestrales consecutivos.

    Trimestres son estados de TRES MESES (no balances acumulados). Si Yahoo
    publicara importes YTD como trimestres, la comparación FY lo detecta.
    """
    q=quarterly.copy() if quarterly is not None else pd.DataFrame()
    if q.empty:return {},pd.DataFrame(),pd.DataFrame(),['Sin información trimestral']
    if 'Cierre del trimestre' in q.columns:
        q=q.set_index('Cierre del trimestre')
    q.index=pd.to_datetime(q.index,errors='coerce',dayfirst=False).tz_localize(None)
    q=q[~q.index.isna() & (q.index<=as_of)].sort_index()
    notes=[]
    invalid=set(q.attrs.get("invalid_flows",[]))
    for date, group in q.groupby(level=0):
        if len(group)>1:
            for col in group.columns:
                if group[col].nunique(dropna=False)>1:
                    invalid.add(col)
                    notes.append(f'Duplicado conflictivo {date.date()}: {col}')
    q=q[~q.index.duplicated(keep='first')]
    # Metadata explícita YTD: diferenciar únicamente dentro del mismo FY.
    # Sin fechas de inicio no es seguro reconstruir trimestres acumulados.
    if 'Tipo periodo' in q and q['Tipo periodo'].eq('YTD').any():
        if 'Inicio periodo' not in q:
            invalid.update(['Ingresos','Beneficio operativo','Beneficio neto','EPS diluido',
                            'Flujo de caja operativo','CAPEX','D&A','Recompras de acciones','Dividendos'])
            notes.append('YTD sin fecha de inicio: flujos no utilizables')
        else:
            original=q.copy()
            for start, group in original.groupby('Inicio periodo'):
                previous=None
                for date, row in group.sort_index().iterrows():
                    if row.get('Tipo periodo')!='YTD':continue
                    duration=(date-pd.Timestamp(start)).days+1
                    expected=1 if previous is None else previous[2]+1
                    number=round(duration/91.25)
                    for col in ['Ingresos','Beneficio operativo','Beneficio neto',
                                'Flujo de caja operativo','CAPEX','D&A','Recompras de acciones','Dividendos']:
                        if col not in q:continue
                        if number!=expected or not 65<=duration-(number-1)*91.25<=115:
                            q.loc[date,col]=np.nan
                            invalid.add(col)
                        elif previous is not None:
                            q.loc[date,col]=f(row.get(col))-f(previous[1].get(col))
                    # EPS no se diferencia sin acciones diluidas ponderadas.
                    q.loc[date,'EPS diluido']=np.nan
                    previous=(date,row,number)
            notes.append('YTD convertido por diferencias dentro del mismo ejercicio; EPS N/D')
    cols=['Ingresos','Beneficio operativo','Beneficio neto','EPS diluido',
          'Flujo de caja operativo','CAPEX','D&A','Flujo de caja libre','EBITDA aproximado',
          'Deuda neta','Deuda total','Efectivo','Recompras de acciones','Dividendos','Patrimonio neto']
    for c in cols:
        if c not in q:q[c]=np.nan
        q[c]=pd.to_numeric(q[c],errors='coerce')
    for derived,left,right,sign in [('Flujo de caja libre','Flujo de caja operativo','CAPEX',-1),('EBITDA aproximado','Beneficio operativo','D&A',1)]:
        if 'Tipo periodo' in q and q['Tipo periodo'].eq('YTD').any():q[derived]=q[left]+sign*q[right]
    last_date=q.index.max() if len(q) else pd.NaT
    newest=q.tail(4)
    consecutive=(len(newest)==4 and all(65 <= (newest.index[j]-newest.index[j-1]).days <=115 for j in range(1,4)))
    ttm={}
    flow_cols=['Ingresos','Beneficio operativo','Beneficio neto','EPS diluido','Flujo de caja operativo',
               'CAPEX','D&A','Flujo de caja libre','EBITDA aproximado','Recompras de acciones','Dividendos']
    for c in flow_cols:
        if consecutive and newest[c].notna().all():ttm[c]=float(newest[c].sum())
        else:ttm[c]=np.nan
    if not consecutive:notes.append('TTM incompleto: no hay cuatro trimestres consecutivos utilizables')
    ttm['Fecha último trimestre']=last_date
    for c in ['Deuda neta','Deuda total','Efectivo','Patrimonio neto']:
        s=q[c].dropna()
        ttm[c+' reciente']=f(s.iloc[-1]) if len(s) else np.nan
        ttm[c+' fecha']=s.index[-1] if len(s) else pd.NaT
    # Cada flujo se reconcilia por separado con FY, tolerancia estricta <1%.
    if len(annual) and fiscal_end_date is not None and pd.notna(fiscal_end_date):
        fy=int(annual.index.max()); fyclose=pd.Timestamp(fiscal_end_date)
        matching=q[(q.index>fyclose-pd.DateOffset(years=1)) & (q.index<=fyclose)]
        for col in ['Ingresos','Beneficio operativo','Flujo de caja operativo','CAPEX','D&A']:
            if col in annual and len(matching)==4 and matching[col].notna().all():
                total=f(annual.loc[fy,col]); part=float(matching[col].sum())
                if np.isfinite(total) and not np.isclose(part,total,rtol=0.009999,atol=1.):
                    invalid.add(col)
                    notes.append(f'Desajuste anual/trimestral FY{fy}: {col}; suma={part}, FY={total}; tolerancia <1%')
    dependencies={'Flujo de caja libre':{'Flujo de caja operativo','CAPEX'},
                  'EBITDA aproximado':{'Beneficio operativo','D&A'}}
    for derived, inputs in dependencies.items():
        if invalid & inputs:invalid.add(derived)
    for col in invalid:
        if col in flow_cols:
            ttm[col]=np.nan
            q[col]=np.nan
    q.attrs['invalid_flows']=sorted(invalid)
    summary=[]
    for col in flow_cols:
        summary.append({'Campo':col,'Base TTM (unidades)':ttm.get(col,np.nan),
                        'Fuente':'4 trimestres' if consecutive and np.isfinite(ttm.get(col,np.nan)) else 'N/D'})
    for col in ['Deuda neta','Deuda total','Efectivo']:
        summary.append({'Campo':col,'Base TTM (unidades)':ttm.get(col+' reciente',np.nan),
                        'Fuente':'Balance al último trimestre disponible'})
    return ttm,pd.DataFrame(summary),q,notes


def ttm_yoy(q,metric):
    """Cambio entre dos ventanas anuales completas, con mismos cierres fiscales."""
    if q is None or metric not in q or len(q)<8:return np.nan
    values=q.sort_index().tail(8)
    if values[metric].isna().any() or values.index.has_duplicates:return np.nan
    if any(not 65<=(b-a).days<=115 for a,b in zip(values.index,values.index[1:])):return np.nan
    if any(not 350<=(values.index[i+4]-values.index[i]).days<=380 for i in range(4)):return np.nan
    previous=values[metric].iloc[:4].sum()
    return values[metric].iloc[4:].sum()/previous-1 if previous>0 else np.nan


def fiscal_year_bridge(df,q,fy_end,as_of):
    """FY actual = trimestres publicados + estimación restante basada en homólogos.

    No interpreta el puente como un consenso; muestra datos publicados y no
    permite que el estimado de FY quede por debajo del YTD para flujos positivos.
    """
    if q.empty or fy_end is None or pd.isna(fy_end):return pd.DataFrame()
    fy_end=pd.Timestamp(fy_end).normalize()
    current=q[(q.index>fy_end) & (q.index<=as_of)].sort_index()
    if current.empty:return pd.DataFrame()
    max_quarters=min(int(len(current)),4)
    if max_quarters>=4:return pd.DataFrame()
    # Una empresa con FY que termina en junio puede tener Q del año calendario anterior.
    rows=[]
    for name in ('Ingresos','Beneficio operativo','Beneficio neto','CAPEX','Flujo de caja operativo','D&A'):
        ytd=f(current[name].tail(max_quarters).sum()) if current[name].tail(max_quarters).notna().all() else np.nan
        former=[]
        base=f(df[name].iloc[-1]) if len(df) and name in df else np.nan
        # En Yahoo suele faltar el Q1 comparativo aunque Q2,Q3,Q4 estén.
        # Si el total anual y otros 3 trimestres existen, reconstruir el Q1
        # por diferencia, sin asignar estimaciones arbitrarias.
        fy_start=fy_end-pd.DateOffset(years=1)
        prior_fy=q[(q.index>fy_start) & (q.index<=fy_end)].sort_index()
        prior_good=prior_fy[name].dropna() if name in prior_fy else pd.Series(dtype=float)
        reconstructed=(base-float(prior_good.sum())) if np.isfinite(base) and len(prior_good)==3 else np.nan
        recovered=False
        for date in current.index[-max_quarters:]:
            prev=q[(q.index>=date-pd.Timedelta(days=380)) & (q.index<=date-pd.Timedelta(days=350))]
            matched=f(prev.iloc[-1][name]) if len(prev) else np.nan
            if not np.isfinite(matched) and np.isfinite(reconstructed):
                matched=reconstructed; recovered=True
            former.append(matched)
        prior_ytd=float(np.sum(former)) if len(former)==max_quarters and np.isfinite(former).all() else np.nan
        prior_remainder=base-prior_ytd if np.isfinite(base) and np.isfinite(prior_ytd) else np.nan
        if name in ('Ingresos','CAPEX','Flujo de caja operativo','D&A') and np.isfinite(prior_ytd) and prior_ytd>0 and np.isfinite(ytd):
            trend=bound(ytd/prior_ytd,.5,2.0)
        else:trend=np.nan
        # Para net income excepcional, NO extrapolarlo ni usarlo como base de EPS normalizado.
        remainder=prior_remainder*trend if np.isfinite(prior_remainder) and np.isfinite(trend) else np.nan
        full=ytd+remainder if np.isfinite(ytd) and np.isfinite(remainder) else np.nan
        if name in ('Ingresos','CAPEX') and np.isfinite(full) and np.isfinite(ytd):full=max(ytd,full)
        status='Estimación mecánica (homólogos previos)' if np.isfinite(full) else 'Sin homólogos: no se estima cierre anual'
        if recovered:status+='; Q previo reconstruido por diferencia con FY publicado'
        if name=='Beneficio neto' and np.isfinite(ytd) and np.isfinite(base) and ytd>base*1.5:
            status+='; fuerte extraordinario posible, no extrapolar EPS'
        rows.append({'Ejercicio fiscal estimado':str(fy_end.year+1),
                     'Métrica':name,'Trimestres reales':max_quarters,
                     'Real YTD (unidades)':ytd,'Mismo periodo FY anterior':prior_ytd,
                     'Resto FY anterior':prior_remainder,'Estimación resto FY':remainder,
                     'FY actual estimado':full,'Advertencia':status})
    return pd.DataFrame(rows)


def wacc_model(fin_currency,market_cap_quote,fx,current_total_debt_fin,annual,info,tax):
    """WACC CAPM aproximado con parámetros verificables y editables.

    Usa prima de mercado editable, beta Yahoo y coste de deuda histórico.
    Sin beta o renta fija comprobable: WACC calculado se etiqueta ilustrativo.
    """
    currency=str(fin_currency).upper()
    rf_defaults={'USD':.041,'EUR':.030,'KRW':.031,'JPY':.018,'GBP':.040,'CHF':.015,'TWD':.020}
    rf=env_float('TIPO_LIBRE_RIESGO',rf_defaults.get(currency,.04))
    erp=env_float('PRIMA_RIESGO_MERCADO',.055)
    beta=env_float('BETA',f(info.get('beta')))
    if not np.isfinite(beta) or beta<=0 or beta>5:
        beta=1.0; beta_note='beta no disponible: beta 1 SUPUESTO'
    else:beta_note='beta de Yahoo (puede estar desactualizada)'
    spread=env_float('RIESGO_PAIS',0.0)
    ke=rf+beta*erp+spread
    debt=f(current_total_debt_fin)
    interest=abs(f(annual['Gastos por intereses'].iloc[-1])) if 'Gastos por intereses' in annual else np.nan
    annual_debt=pd.to_numeric(annual.get('Deuda total',pd.Series(dtype=float)),errors='coerce').tail(2)
    consecutive=len(annual)>=2 and int(annual.index[-1])-int(annual.index[-2])==1
    average_debt=f(annual_debt.mean()) if len(annual_debt)==2 and annual_debt.notna().all() and consecutive else np.nan
    if np.isfinite(average_debt) and average_debt>0 and np.isfinite(interest) and interest>=0:
        kd=interest/average_debt
        kd_note='intereses último FY / deuda media inicial-final del mismo FY; proxy histórico, no coste prospectivo'
    else:
        kd=rf+.025
        kd_note='sin coste de deuda utilizable: prima 2.5 pp SUPUESTA'
    override_kd=env_float('COSTE_DEUDA',np.nan)
    if np.isfinite(override_kd):kd=override_kd; kd_note='Override coste deuda; requiere fuente y vigencia'
    equity_fin=ratio(market_cap_quote,fx)
    denom=equity_fin+(debt if np.isfinite(debt) and debt>=0 else 0)
    if not np.isfinite(denom) or denom<=0: return np.nan,rf,beta,ke,kd,beta_note+'; capitalización ausente'
    we=equity_fin/denom
    wd=1-we
    calc=we*ke+wd*kd*(1-tax)
    override_currency=os.environ.get('VALUACION_PARAMETROS_MONEDA',currency).upper()
    if override_currency!=currency:return np.nan,rf,beta,ke,kd,'BLOQUEO: parámetros de riesgo en otra moneda'
    if os.environ.get('VALUACION_ERP_INCLUYE_PAIS','').lower() in ('1','true') and spread!=0:
        return np.nan,rf,beta,ke,kd,'BLOQUEO: riesgo país ya incluido en ERP'
    manual=env_float('WACC',np.nan)
    wacc=manual if np.isfinite(manual) else calc
    note=('WACC MANUAL' if np.isfinite(manual) else 'WACC aproximado CAPM; '+beta_note+'; '+kd_note)
    return wacc,rf,beta,ke,kd,note


def build_fundamental_model(annual,peers,*,price,market_cap,shares_outstanding,
                            financial_currency,quote_currency,fx=1.,fx_source='mismas divisas',
                            source='No declarado',stock_comp=None,is_demo=False,
                            quarterly=None,fiscal_end_date=None,as_of=None,ticker='',info=None,
                            recent_results_check=None,share_schedule=None,sensitivity_shocks=None):
    shocks=dict(sensitivity_shocks or {})
    allowed_shocks={'capex_sales','da_sales','wacc','terminal_growth'}
    if set(shocks)-allowed_shocks or any(not np.isfinite(f(v)) or abs(float(v))>.20 for v in shocks.values()):
        raise ValueError('Shocks de sensibilidad no válidos')
    info=info or {}
    share_schedule=share_schedule or {}
    now=pd.Timestamp(as_of or pd.Timestamp.now()).normalize()
    df=annual.copy().sort_index()
    necessary=['Ingresos','Beneficio operativo','Beneficio neto','EPS diluido','D&A','CAPEX',
               'Flujo de caja libre','EBITDA aproximado','Deuda neta','Deuda total',
               'Tasa fiscal','Beneficio antes de impuestos','Capital invertido aproximado',
               'NOPAT aproximado','Acciones diluidas medias','Flujo de caja operativo',
               'Gastos por intereses','Recompras de acciones','Dividendos']
    for c in necessary:
        if c not in df:df[c]=np.nan
        df[c]=pd.to_numeric(df[c],errors='coerce')
    checks=[]
    def check(name,ok,note,blocking=False):
        checks.append({'Comprobación':name,'Estado':'OK' if ok else ('BLOQUEO' if blocking else 'REVISAR'),
                       'Detalle':note})
    px=f(price); fx=f(fx); mcap=f(market_cap); shares=f(shares_outstanding)
    if (not np.isfinite(shares) or shares<=0) and np.isfinite(px) and px>0:
        shares=ratio(mcap,px)
    if (not np.isfinite(mcap) or mcap<=0) and np.isfinite(shares) and shares>0:
        mcap=shares*px
    check('Divisas y FX',np.isfinite(fx) and fx>0,f'{financial_currency}→{quote_currency}; fuente: {fx_source}',True)
    check('Precio y número acciones',np.isfinite(px) and px>0 and np.isfinite(shares) and shares>0,
          'acciones al cierre, no acciones medias del ejercicio; se valida capitalización',True)
    market_consistent=True
    if np.isfinite(shares) and np.isfinite(px) and np.isfinite(mcap) and mcap>0:
        discrepancy=abs(shares*px/mcap-1)
        market_consistent=(discrepancy<.10)
        check('Capitalización = precio × acciones',market_consistent,
              f'Diferencia {discrepancy:.1%}; split/ADR y acciones a reconciliar',blocking=True)
    check('Cobertura histórica',len(df)>=10,f'{len(df)} ejercicios fuente {source}; sin SEC se usa Yahoo cuando exista')
    ttm,ttm_table,q,qn=quarterly_snapshot(quarterly,df,now,fiscal_end_date)
    for note in qn:check('Integridad trimestral',False,note)
    published_newer=False
    recent_details='Verificación externa no disponible'
    if isinstance(recent_results_check,dict):
        published_newer=bool(recent_results_check.get('newer_filing_confirmed'))
        recent_details=str(recent_results_check.get('detail') or recent_details)
    freshness=(recent_results_check or {}).get('status','NO_VERIFICADO')
    if published_newer:freshness='BLOQUEO'
    checks.append({'Comprobación':'Publicación posterior a datos trimestrales',
                   'Estado':freshness if freshness in ('VERIFICADO','NO_VERIFICADO','REVISAR','BLOQUEO') else 'NO_VERIFICADO',
                   'Detalle':recent_details})
    last_annual=int(df.index.max()) if len(df) else None
    bridge=fiscal_year_bridge(df,q,fiscal_end_date,now)
    latest_q=ttm.get('Fecha último trimestre',pd.NaT)
    annual_date=pd.Timestamp(fiscal_end_date) if fiscal_end_date is not None and pd.notna(fiscal_end_date) else pd.NaT
    if pd.notna(latest_q):
        check('Actualidad trimestral',(now-latest_q).days<=125,
              f'Último trimestre {latest_q.date()}, {int((now-latest_q).days)} días hasta fecha valoración; si supera 125 días comprobar nueva publicación')
    if not bridge.empty:
        tr=bridge[bridge['Métrica']=='Ingresos'].iloc[0]
        check('Puente año fiscal actual',np.isfinite(f(tr['FY actual estimado'])),
              f"{int(tr['Trimestres reales'])} trimestres publicados, ingresos YTD {tr['Real YTD (unidades)']/1e9:,.2f} miles MM",False)
    r_annual=f(df['Ingresos'].iloc[-1]) if len(df) else np.nan
    op_annual=f(df['Beneficio operativo'].iloc[-1]) if len(df) else np.nan
    net_annual=f(df['Beneficio neto'].iloc[-1]) if len(df) else np.nan
    ttm_revenue=f(ttm.get('Ingresos'))
    ttm_op=f(ttm.get('Beneficio operativo'))
    # Base: resultados TTM (cuatro trimestres consecutivos); nunca año anterior si TTM utilizable.
    use_ttm=np.isfinite(ttm_revenue) and ttm_revenue>0 and np.isfinite(ttm_op)
    r=ttm_revenue if use_ttm else r_annual
    op=ttm_op if use_ttm else op_annual
    base_origin='TTM' if use_ttm else 'Anual'
    partial_without_base=(not use_ttm and pd.notna(latest_q) and pd.notna(annual_date) and latest_q>annual_date)
    bridge_ok=False
    if partial_without_base:
        def projected_fy(metric):
            if bridge.empty or 'Métrica' not in bridge:return np.nan
            serie=bridge.loc[bridge['Métrica'].eq(metric),'FY actual estimado']
            return f(serie.iloc[0]) if len(serie) else np.nan
        br=projected_fy('Ingresos'); bo=projected_fy('Beneficio operativo')
        if np.isfinite(br) and br>0 and np.isfinite(bo):
            r,op=br,bo
            base_origin='Puente FY parcial'
            bridge_ok=True
        check('Base parcial sin TTM',bridge_ok,
              'No extrapolar el último FY antiguo: si puente FY insuficiente bloquear precios',blocking=True)
    check('Base de proyección',use_ttm or bridge_ok,
          ('TTM real hasta '+str(latest_q.date())) if use_ttm else (
            'Puente del ejercicio parcial' if bridge_ok else 'Último ejercicio anual: datos trimestrales insuficientes'))
    net_ttm=f(ttm.get('Beneficio neto'))
    # Beneficios extraordinarios pueden superar ingresos; se proyecta EBIT menos fiscalidad y otros NORMALIZADOS.
    raw_net_margin=ratio(net_ttm,ttm_revenue)
    unusual=np.isfinite(raw_net_margin) and (raw_net_margin>.75 or raw_net_margin<-.6)
    check('Beneficio neto TTM extraordinario',not unusual,
          f'Margen neto TTM={raw_net_margin:.1%}; no extrapolar de forma automática el EPS' if np.isfinite(raw_net_margin) else 'Sin beneficio neto TTM comparable')
    latest_balance_q=f(ttm.get('Deuda neta reciente'))
    nd_annual=f(df['Deuda neta'].iloc[-1]) if len(df) else np.nan
    balance_is_newer=pd.notna(latest_q) and (pd.isna(annual_date) or latest_q>annual_date)
    nd=latest_balance_q if balance_is_newer and np.isfinite(latest_balance_q) else nd_annual
    if not np.isfinite(nd) and np.isfinite(latest_balance_q):nd=latest_balance_q
    nd_date=ttm.get('Deuda neta fecha') if np.isfinite(latest_balance_q) and nd==latest_balance_q else annual_date
    check('Deuda neta más reciente',np.isfinite(nd),
          f'Fuente: {"trimestre" if nd==latest_balance_q and np.isfinite(latest_balance_q) else "anual"}; {nd_date}; divisa contable',True)
    balance_recent=pd.notna(nd_date) and ((now-pd.Timestamp(nd_date)).days <=400)
    check('Vigencia balance',balance_recent,
          f'Fecha {nd_date}; límite conservador 400 días, valores antiguos pueden estar obsoletos',blocking=True)
    debt=f(ttm.get('Deuda total reciente')) if balance_is_newer else np.nan
    if not np.isfinite(debt):debt=f(df['Deuda total'].iloc[-1]) if len(df) else np.nan
    # Impuestos: normalizados para evitar tasas extraordinarias negativas o >100%.
    tax_vals=df['Tasa fiscal'].dropna()
    if len(tax_vals) and tax_vals.abs().median()>1:tax_vals=tax_vals/100
    tax=bound(med(tax_vals,3),.08,.38)
    if not np.isfinite(tax):tax=env_float('TASA_IMPOSITIVA',.25)
    revenues=df['Ingresos']; op_margin=df['Beneficio operativo']/revenues.replace(0,np.nan)
    margin_hist=med(op_margin,3)
    margin_latest=ratio(op,r)
    margin=bound(.7*margin_latest+.3*margin_hist,-.40,.80) if np.isfinite(margin_hist) and np.isfinite(margin_latest) else bound(margin_latest,-.4,.8)
    # Margen neto efectivo extraordinario NO determina la proyección.
    normal_other_hist=(df['Beneficio neto']-df['Beneficio operativo']*(1-tax))/df['Ingresos'].replace(0,np.nan)
    normal_other=bound(med(normal_other_hist,3),-.08,.08)
    if not np.isfinite(normal_other):normal_other=0.
    if unusual:normal_other=bound(normal_other,-.03,.03)
    da_hist=med(df['D&A']/revenues.replace(0,np.nan),3,positive=True)
    cap_hist=med(df['CAPEX']/revenues.replace(0,np.nan),3,positive=True)
    da_latest=ratio(ttm.get('D&A'),ttm_revenue) if use_ttm else np.nan
    cap_latest=ratio(ttm.get('CAPEX'),ttm_revenue) if use_ttm else np.nan
    # No usar únicamente mediana histórica en presencia de una aceleración de CAPEX.
    da_ratio=bound(.75*da_latest+.25*da_hist,0,.7) if np.isfinite(da_latest) and np.isfinite(da_hist) else bound(da_latest if np.isfinite(da_latest) else da_hist,0,.7)
    cap_ratio=bound(.8*cap_latest+.2*cap_hist,0,.9) if np.isfinite(cap_latest) and np.isfinite(cap_hist) else bound(cap_latest if np.isfinite(cap_latest) else cap_hist,0,.9)
    cap_ratio=cap_ratio+shocks.get('capex_sales',0.)
    da_ratio=da_ratio+shocks.get('da_sales',0.)
    if np.isfinite(cap_ratio) and not 0<=cap_ratio<=.9:raise ValueError('CAPEX/ventas fuera de límites')
    if np.isfinite(da_ratio) and not 0<=da_ratio<=.7:raise ValueError('D&A/ventas fuera de límites')
    if 'CAPEX' in q.attrs.get('invalid_flows',[]):cap_ratio=np.nan
    if 'D&A' in q.attrs.get('invalid_flows',[]):da_ratio=np.nan
    check('Capex de periodos recientes',np.isfinite(cap_ratio),f'CAPEX TTM / ventas {cap_latest:.1%} si disponible; referencia anual {cap_hist:.1%}' if np.isfinite(cap_hist) else 'Sin CAPEX',True)
    check('Depreciación de periodos recientes',np.isfinite(da_ratio),'D&A puede incluir «and other» en SEC; verificar en cuentas',True)
    growth_hist=df['Ingresos'].pct_change(fill_method=None).replace([np.inf,-np.inf],np.nan).dropna().tail(4)
    gh=bound(med(growth_hist,4),-.20,.40)
    last_year_growth=ttm_yoy(q,'Ingresos')
    g=bound(last_year_growth,-.30,.55) if np.isfinite(last_year_growth) else gh
    growth_origin='TTM interanual (8 trimestres)' if np.isfinite(last_year_growth) else 'Mediana crecimiento FY (sin TTM interanual)'
    check('Crecimiento comparable',np.isfinite(g),growth_origin+'; nunca TTM / FY')
    env_g=env_float('CRECIMIENTO_VENTAS',np.nan)
    if np.isfinite(env_g):g=bound(env_g,-.4,.7); growth_origin='Override explícito VALUACION_CRECIMIENTO_VENTAS'
    vol=f(growth_hist.std(ddof=1)) if len(growth_hist)>=3 else .10
    if not np.isfinite(vol):vol=.10
    band=bound(vol*.45,.04,.15)
    nwc=env_float('VAR_CAPITAL_TRABAJO_PCT',.01)
    shares_growth=env_float('CRECIMIENTO_ACCIONES',0.)
    # Las recompras y dividendos afectan a caja y al stock de acciones; no duplicar
    # como un gasto del FCFF. Por defecto, payout histórico si disponible; cero si ausente.
    dividend_ratio=med(df['Dividendos'].abs()/df['Ingresos'].replace(0,np.nan),3)
    dividend_ratio=dividend_ratio if np.isfinite(dividend_ratio) else 0.
    payout_hist=[]
    for name in ['Dividendos','Recompras de acciones']:
        vals=df[name].abs()/df['Ingresos'].replace(0,np.nan)
        v=med(vals,3)
        if np.isfinite(v):payout_hist.append(v)
    payout_ratio=min(sum(payout_hist),.3) if payout_hist else 0.
    manual_payout=env_float('PAGOS_ACCIONISTAS_SOBRE_VENTAS',np.nan)
    if np.isfinite(manual_payout):payout_ratio=bound(manual_payout,0,.4)
    check('Remuneración accionistas',bool(payout_hist) or np.isfinite(manual_payout),
          f'Pagos cash / ventas {payout_ratio:.1%}; recompras no se asumen cambio de acciones, crecimiento de acciones editable')
    stockcomp=f(stock_comp)
    check('Compensación en acciones',np.isfinite(stockcomp),
          'SBC requiere reconcilación: dilución futura configurada, no hay gasto doble contabilizado')
    if np.isfinite(margin) and margin>.6:
        check('Margen operativo elevado',False,f'Margen EBIT base {margin:.1%}: evaluar sostenibilidad/ciclo')
    check('Extraordinarios y beneficios',np.isfinite(normal_other),
          f'Ingresos no operativos normalizados {normal_other:.1%} de ventas; eventos excepcionales no extrapolados')
    # Capital reciente para comparar con métricas prospectivas.
    wacc,rf,beta,ke,kd,wacc_note=wacc_model(financial_currency,mcap,fx,debt,df,info,tax)
    wacc=wacc+shocks.get('wacc',0.)
    tg=env_float('CRECIMIENTO_TERMINAL',.025 if str(financial_currency).upper()=='USD' else .02)+shocks.get('terminal_growth',0.)
    check('WACC específico',np.isfinite(wacc) and .04<wacc<.30,
          f'{wacc*100:.2f}%; rf {rf*100:.2f}%; beta {beta:.2f}; Ke {ke*100:.2f}%; Kd {kd*100:.2f}%; {wacc_note}')
    check('Terminal descontable',np.isfinite(wacc) and -.01<tg<wacc-.015,
          f'WACC {wacc*100:.2f}%, g terminal {tg*100:.2f}%; WACC debe superar g por al menos 1.5pp',True)
    catalog=load_config().get(ticker.upper(),{})
    cycle_str=os.environ.get('VALUACION_EMPRESA_CICLICA','').strip()
    cyclical=(cycle_str in ('1','true','True','si','sí')) if cycle_str else bool(catalog.get('ciclica',False))
    peer_table,pe_median,ev_median,peer_refs,peer_universe=score_and_filter(peers,ticker,
          target_margin=margin*100 if np.isfinite(margin) else np.nan,
          target_growth=g*100 if np.isfinite(g) else np.nan,
          target_cap=mcap/1e9 if np.isfinite(mcap) else np.nan,
          target_info=info,return_universe=True,as_of=now)
    # Valores de la misma empresa solo como referencia secundaria, nunca confundidos con peers.
    self_pe=f(info.get('forwardPE'))
    self_ev=f(info.get('enterpriseToEbitda'))
    # El PER/EV de la PROPIA empresa no es un comparable independiente:
    # se muestra como referencia, pero NO se sustituye a un peer inexistente.
    pe_ref=pe_median
    ev_ref=ev_median
    # Agregados contables y perímetros sin conciliar no autorizan FCFF/EBITDA.
    latest_definition=str(df.get('Definición D&A',pd.Series(dtype=str)).iloc[-1]) if 'Definición D&A' in df and len(df) else 'No declarada'
    da_origin=str(df.get('Origen D&A',pd.Series(dtype=str)).iloc[-1]) if 'Origen D&A' in df and len(df) else ''
    da_aggregate='otros' in latest_definition.lower() or 'ppe' in latest_definition.lower() or 'DepreciationAmortizationAndOther' in da_origin
    if len(df) and pd.notna(df.iloc[-1].get('D&A validada')) and bool(df.iloc[-1].get('D&A validada')):
        da_aggregate=da_aggregate or 'D&A validada' not in q or not q.tail(4)['D&A validada'].fillna(False).eq(True).all()
    lease_mismatch=False
    balance_row=None
    for table in [q,df]:
        if not table.empty and 'Deuda incluye arrendamientos' in table:
            balance_row=table.iloc[-1];break
    if balance_row is not None:
        raw=balance_row.get('Deuda incluye arrendamientos')
        lease_mismatch=pd.notna(raw) and str(raw).lower() in ('true','1','sí','si')
    check('Definición D&A para FCFF',not da_aggregate,'D&A: '+latest_definition+'; agregado no permite DCF/EV-EBITDA')
    check('Perímetro leases',not lease_mismatch,'Deuda que incluye leases requiere FCFF conciliado antes de DCF y EV/EBITDA')
    if da_aggregate or lease_mismatch:ev_ref=np.nan
    # Para sectores cíclicos un múltiplo de la propia empresa en pleno boom NO
    # constituye una referencia prospectiva independiente: bloquear si no hay peers.
    if cyclical:
        if not np.isfinite(pe_median):pe_ref=np.nan
        if not np.isfinite(ev_median):ev_ref=np.nan
    check('Comparables económicos',np.isfinite(pe_median) and np.isfinite(ev_median),
          f'Mediana PER peers {pe_median}; EV/EBITDA peers {ev_median}; Yahoo propia {self_pe}/{self_ev} solo referencia NO valorativa')
    check('Fuentes externos',not is_demo,'Yahoo/SEC sujetos a retrasos/cambios; sin consenso de analistas, guidance o ajustes especiales')
    # Si hay segundo escenario de perímetro, horizonte de un año se refiere a doce
    # meses desde FECHA DE VALORACIÓN, con base disponible a último cierre financiero.
    values=[r,op,margin,g,cap_ratio,da_ratio,px,fx,shares,nd,wacc]
    core_ok=np.isfinite(debt) and (freshness!='BLOQUEO') and not bool(set(q.attrs.get('invalid_flows',[])) & {'Ingresos','Beneficio operativo'}) and market_consistent and balance_recent and (not partial_without_base or bridge_ok) and all(np.isfinite(f(v)) for v in values) and r>0 and shares>0 and px>0 and fx>0 and .04<wacc<.30 and tg<wacc-.015
    check('Integridad para precio objetivo',core_ok,'Todos ingresos, EBIT, CAPEX, D&A, FX, deuda neta, acciones y descuento deben existir',True)
    ass_data=[
      ('Fecha valoración',str(now.date()),'Fecha de consulta del motor'),
      ('Shocks de auditoría',str(shocks) if shocks else 'Ninguno','Solo experimentos separados; no recalibra la base ni rellena datos ausentes'),
      ('Último ejercicio disponible',last_annual,'Fecha SEC/Yahoo anual'),
      ('Fecha base TTM',str(latest_q.date()) if pd.notna(latest_q) else 'N/D','Cuatro trimestres, no ×4 de un trimestre'),
      ('Base operativa',base_origin,'TTM; puente FY si es necesario; bloquear si parcial sin base completa'),
      ('Ingresos base (miles MM)',r/1e9,'TTM o FY si no hay cuatro trimestres'),
      ('Crecimiento ventas (%)',100*g,growth_origin),
      ('Crecimiento TTM interanual (%)',100*last_year_growth,'N/D sin ocho trimestres consecutivos; no se sustituye por cero'),
      ('Banda de escenarios (%)',100*band,'Sensibilidad, NO intervalo de confianza'),
      ('Margen EBIT normalizado (%)',100*margin,'70% margen TTM + 30% histórico si datos'),
      ('D&A / ingresos (%)',100*da_ratio,'80/20 reciente/histórico aprox.; definición D&A revisar'),
      ('CAPEX / ingresos (%)',100*cap_ratio,'80% tasa TTM + 20% histórica si existe'),
      ('No operativos normalizados (%)',100*normal_other,'Recorte extraordinarios/ausencia dato'),
      ('Impuestos normalizados (%)',100*tax,'Mediana tasas FY; acotada'),
      ('Capital trabajo / aumento ingresos (%)',100*nwc,'Ajustable; requiere flujos capital trabajo'),
      ('Pagos accionistas / ingresos (%)',100*payout_ratio,'Dividendo + recompras cash; estimación'),
      ('Crecimiento acciones (%)',100*shares_growth,'No relaciona automáticamente recompras con dilución'),
      ('Deuda neta reciente (miles MM)',nd/1e9,'Balance trimestral o anual más reciente'),
      ('Fecha balance',str(nd_date.date()) if pd.notna(nd_date) else 'N/D','La deuda evoluciona en escenarios'),
      ('EPS TTM','Suma EPS trimestrales (aproximación)','No equivale a beneficio TTM / acciones diluidas ponderadas TTM si varían las acciones'),
      ('Acciones al cierre (miles MM)',shares/1e9,'Yahoo acciones en circulación'),
      ('FX contabilidad a cotización',fx,fx_source),
      ('WACC (%)',100*wacc,wacc_note),
      ('Coste equity Ke (%)',100*ke,'rf+beta*ERP+riesgo país'),
      ('Coste deuda Kd (%)',100*kd,'Gastos financieros / deuda o aproximación'),
      ('Beta',beta,'Yahoo o supuesto 1'),
      ('Tasa sin riesgo (%)',100*rf,'Supuesto moneda editable'),
      ('Prima mercado ERP (%)',100*env_float('PRIMA_RIESGO_MERCADO',.055),'Editable'),
      ('Crecimiento terminal (%)',100*tg,'Editable, compatible con WACC'),
      ('Año terminal común',8,'Misma trayectoria y estado estable en horizontes 0, 1 y 3'),
      ('Convención deuda y leases','Deuda financiera sin leases','FCFF con cash CAPEX; no se añade deuda de leases sin conciliación integral; resultado condicional'),
      ('Caja e inversiones','Saldo fuente; disponibilidad no verificada','Sin evidencia no se presume que inversiones estratégicas sean caja distribuible'),
      ('Acciones y recompras','Calendario documentado' if share_schedule else 'Acciones constantes salvo crecimiento explícito','Sin cancelaciones/SBC documentadas no se inventa variación; caja sí paga recompras'),
      ('PER forward propio Yahoo (solo referencia)',self_pe,'No es comparable independiente ni múltiplo para valorar'),
      ('EV/EBITDA Yahoo propio (solo referencia)',self_ev,'No es comparable independiente ni múltiplo para valorar'),
      ('PER de referencia (x)',pe_ref,'Sólo comparables económicos válidos; si faltan no habrá objetivo PER'),
      ('EV/EBITDA referencia (x)',ev_ref,'Sólo comparables económicos válidos; si faltan no habrá objetivo EV/EBITDA'),
      ('PER referencia origen','Comparables independientes' if np.isfinite(pe_median) else 'N/D: comparables insuficientes','No se utiliza el PER propio como sustituto'),
      ('EV/EBITDA referencia origen','Comparables independientes' if np.isfinite(ev_median) else 'N/D: comparables insuficientes','No se utiliza EV/EBITDA propio como sustituto'),
    ]
    assumptions=pd.DataFrame(ass_data,columns=['Supuesto','Valor','Origen y limitación'])
    # ROIC aproximado sobre inversión media. Evita negativos/equity residual absurdo.
    roic=[];prev=np.nan
    for year,row in df.iterrows():
        ci=f(row.get('Capital invertido aproximado'));nop=f(row.get('NOPAT aproximado'))
        avg=(ci+prev)/2 if np.isfinite(ci) and np.isfinite(prev) and roic and int(year)-int(roic[-1]['Ejercicio'])==1 else np.nan
        rr=ratio(nop,avg) if np.isfinite(avg) and avg>0 else np.nan
        roic.append({'Ejercicio':year,'Capital invertido inicial (miles MM)':prev/1e9 if np.isfinite(prev) else np.nan,
                     'Capital invertido final (miles MM)':ci/1e9 if np.isfinite(ci) else np.nan,
                     'Capital invertido medio (miles MM)':avg/1e9 if np.isfinite(avg) else np.nan,
                     'NOPAT (miles MM)':nop/1e9 if np.isfinite(nop) else np.nan,
                     'ROIC capital medio (%)':100*rr if np.isfinite(rr) else np.nan,
                     'ROIC FY - WACC actual (pp)':100*(rr-wacc) if np.isfinite(rr) else np.nan,
                     'Nota':'aproximado, revisar efectivo operativo, goodwill, leases y NOPAT'})
        prev=ci
    initial_ci=final_ci=np.nan
    if not q.empty and 'Capital invertido aproximado' in q:
        latest=q.index.max()
        current=q.loc[latest,'Capital invertido aproximado']
        prior=q[(q.index>=latest-pd.Timedelta(days=380)) & (q.index<=latest-pd.Timedelta(days=350))]
        final_ci=f(current)
        if len(prior)==1:initial_ci=f(prior.iloc[0]['Capital invertido aproximado'])
    mean_ci=(initial_ci+final_ci)/2
    roic_ttm_value=ratio(ttm_op*(1-tax),mean_ci) if np.isfinite(mean_ci) and mean_ci>0 else np.nan
    roic_ttm=pd.DataFrame([{'Periodo':'TTM','Fecha cierre':str(latest_q),'NOPAT TTM':ttm_op*(1-tax),
        'Capital inicial':initial_ci,'Capital final':final_ci,'Capital medio':mean_ci,
        'ROIC TTM capital medio (%)':roic_ttm_value*100,'WACC actual (%)':wacc*100,
        'Estado':'APROXIMADO' if np.isfinite(roic_ttm_value) else 'N/D',
        'Limitación':'Capital fuente resta caja/inversiones; goodwill y leases sin ajuste; tasa fiscal normalizada; WACC actual, no histórico'}])
    typical_margin=bound(med(op_margin,5),-.25,.7)
    custom_cycle_margin=env_float('MARGEN_NORMALIZADO',np.nan)
    if np.isfinite(custom_cycle_margin):typical_margin=bound(custom_cycle_margin,-.25,.7)
    if not np.isfinite(typical_margin):typical_margin=margin
    check('Ciclo y normalización',not cyclical,
          ('Actividad cíclica: crecimiento converge desde año 1; margen EBIT vuelve hacia '+f'{typical_margin:.1%} con el tiempo') if cyclical else 'Sin normalización de ciclo explícita')
    assumptions=pd.concat([assumptions,pd.DataFrame([
      ('Empresa cíclica', 'Sí' if cyclical else 'No','Catálogo económico o VALUACION_EMPRESA_CICLICA'),
      ('Margen EBIT de ciclo normalizado (%)',100*typical_margin,'Mediana de hasta cinco FY o VALUACION_MARGEN_NORMALIZADO')
    ],columns=assumptions.columns)],ignore_index=True)
    specs={
      'Pesimista':{'growth':bound(g-band,-.5,.7),'margin_shift':-.04,'wacc':wacc+.015,'gterm':tg-.005,'multiple':.85,'cap_factor':1.10},
      'Base':{'growth':g,'margin_shift':0.,'wacc':wacc,'gterm':tg,'multiple':1.,'cap_factor':1.},
      'Optimista':{'growth':bound(g+band,-.5,.7),'margin_shift':.04,'wacc':wacc-.01,'gterm':tg+.005,'multiple':1.15,'cap_factor':.95},
    }
    projected=[]; valued=[]; dcf=[]
    if core_ok:
        for scenario,s in specs.items():
            rev=r; nd_future=nd; forecast=[]; cumulative_dividends=0.; future_shares=shares
            for yr in range(1,9):
                if cyclical:
                    # Reversión gradual: no extrapolar un boom de memoria/HBM ocho años.
                    speed={1:.70,2:.35,3:.10}.get(yr,0.)
                    growth=s['growth']*speed + s['gterm']*(1-speed) if yr<=3 else s['gterm']
                    weight_to_cycle=min(yr/5,1.)
                    margin_f=bound((margin+s['margin_shift'])*(1-weight_to_cycle)+typical_margin*weight_to_cycle,-.50,.85)
                else:
                    growth=s['growth'] if yr<=3 else s['growth']+(s['gterm']-s['growth'])*(yr-3)/5
                    margin_f=bound(margin+s['margin_shift']*(1 if yr<=3 else (8-yr)/5),-.50,.85)
                prior_rev=rev;rev=rev*(1+growth)
                EBIT=rev*margin_f
                DA=rev*da_ratio
                CAPEX=rev*cap_ratio*s['cap_factor']
                dNWC=(rev-prior_rev)*nwc
                NOPAT=EBIT*(1-tax)
                FCFF=NOPAT+DA-CAPEX-dNWC
                # Flujos de financiación: gasto interés aproximado (deuda neta puede ser negativa).
                interest_net=max(0,debt)*kd*(1-tax) if np.isfinite(debt) else np.nan
                dividends=max(0,rev*min(dividend_ratio,payout_ratio))
                buyback=max(0,rev*payout_ratio-dividends)
                event=share_schedule.get(yr,{})
                cancelled=f(event.get('cancelled_shares',0.)); issued=f(event.get('issued_shares',0.))
                if cancelled<0 or issued<0 or not np.isfinite(cancelled+issued):
                    raise ValueError('Calendario de acciones inválido')
                if cancelled:
                    buyback_price=f(event.get('buyback_price_fin'))
                    if not np.isfinite(buyback_price) or buyback_price<=0 or not event.get('source'):
                        raise ValueError('Cancelaciones requieren precio de recompra en divisa financiera y fuente')
                    buyback=cancelled*buyback_price
                if issued and not event.get('source'):raise ValueError('Emisiones/SBC requieren fuente')
                payout=dividends+buyback
                nd_future=nd_future-(FCFF-interest_net-payout)
                future_shares=future_shares*(1+shares_growth)+issued-cancelled
                if future_shares<=0:raise ValueError('Acciones futuras no positivas')
                cumulative_dividends+=dividends/future_shares
                net_income=NOPAT+rev*normal_other
                eps_future=ratio(net_income,future_shares)
                EBITDA=EBIT+DA
                record={'Escenario':scenario,'Año futuro':yr,
                   'Fecha objetivo aprox.':str((now+pd.DateOffset(years=yr)).date()),
                   'Ingresos (miles MM)':rev/1e9,'Crecimiento ingresos (%)':100*growth,
                   'Margen EBIT (%)':100*margin_f,'EBIT (miles MM)':EBIT/1e9,
                   'D&A (miles MM)':DA/1e9,'EBITDA (miles MM)':EBITDA/1e9,
                   'CAPEX (miles MM)':CAPEX/1e9,'Impuestos normalizados (%)':tax*100,
                   'NOPAT (miles MM)':NOPAT/1e9,'Variación capital trabajo (miles MM)':dNWC/1e9,
                   'FCFF (miles MM)':FCFF/1e9,'Pagos accionistas (miles MM)':payout/1e9,
                   'Dividendos (miles MM)':dividends/1e9,'Recompras cash (miles MM)':buyback/1e9,
                   'Acciones emitidas':issued,'Acciones canceladas':cancelled,
                   'Dividendos acumulados por acción':cumulative_dividends,
                   'Beneficio normalizado (miles MM)':net_income/1e9,
                   'Acciones (miles MM)':future_shares/1e9,'EPS normalizado (divisa contable)':eps_future,
                   'Deuda neta proyectada (miles MM)':nd_future/1e9}
                projected.append(record)
                forecast.append({'year':yr,'fcff':FCFF,'eps':eps_future,'ebitda':EBITDA,
                                 'nd':nd_future,'shares':future_shares,'dividends':cumulative_dividends,
                                 'nopat':NOPAT,'reinvestment':CAPEX-DA+dNWC})
            for horizon in (0,1,3):
                rec=forecast[horizon-1] if horizon else {'nd':nd,'shares':shares,'dividends':0.,'eps':np.nan,'ebitda':np.nan}
                flows=forecast[horizon:]
                w=s['wacc']; tg_s=s['gterm']
                terminal_reinvestment=ratio(forecast[-1]['reinvestment'],forecast[-1]['nopat'])
                terminal_roic=ratio(tg_s,terminal_reinvestment)
                can_dcf= not da_aggregate and not lease_mismatch and .04<w<.35 and -0.02<tg_s<w-.015 and 0<=terminal_reinvestment<1 and flows[-1]['fcff']>0
                # ROIC terminal se deriva de reinversión observada en la trayectoria.
                # No se impone ROIC ni se reduce CAPEX para aproximar la cotización.
                terminal=np.nan; enterprise=np.nan
                if can_dcf:
                    terminal=flows[-1]['fcff']*(1+tg_s)/(w-tg_s)
                    enterprise=sum(v['fcff']/(1+w)**idx for idx,v in enumerate(flows,1)) + terminal/(1+w)**len(flows)
                for idx,row in enumerate(flows,1):
                    dcf.append({'Escenario':scenario,'Horizonte base (años)':horizon,
                      'Año flujo':row['year'],'Año terminal común':8,
                      'Reinversión terminal (%)':terminal_reinvestment*100,'ROIC terminal implícito (%)':terminal_roic*100,
                      'FCFF (miles MM)':row['fcff']/1e9,
                      'WACC (%)':100*w,'VP FCFF (miles MM)':row['fcff']/(1+w)**idx/1e9,
                      'Valor terminal (miles MM)':terminal/1e9 if idx==len(flows) and np.isfinite(terminal) else np.nan})
                mp=pe_ref*s['multiple'] if np.isfinite(pe_ref) else np.nan
                me=ev_ref*s['multiple'] if np.isfinite(ev_ref) else np.nan
                prices={
                  'PER forward':rec['eps']*mp*fx if np.isfinite(rec['eps']) and rec['eps']>0 and np.isfinite(mp) else np.nan,
                  'EV/EBITDA forward':(rec['ebitda']*me-rec['nd'])/rec['shares']*fx if rec['ebitda']>0 and np.isfinite(me) else np.nan,
                  'DCF FCFF (valor futuro)':(enterprise-rec['nd'])/rec['shares']*fx if np.isfinite(enterprise) else np.nan}
                if horizon==0:prices={'DCF FCFF (valor presente)':prices['DCF FCFF (valor futuro)']}
                for method,target in prices.items():
                    if not np.isfinite(target) or target<=0:target=np.nan
                    reval=(target/px-1)*100 if np.isfinite(target) else np.nan
                    annual_return=((target/px)**(1/horizon)-1)*100 if np.isfinite(target) and horizon else np.nan
                    valued.append({'Escenario':scenario,'Horizonte (años)':horizon,'Método':method,
                        'Fecha objetivo aprox.':str((now+pd.DateOffset(years=horizon)).date()),
                        'Precio objetivo (divisa cotización)':target,
                        'Precio actual (divisa cotización)':px,
                        'Potencial (%)':reval,'Rentabilidad anualizada (%)':annual_return,
                        'Retorno total (%)':((target+rec['dividends']*fx)/px-1)*100 if np.isfinite(target) and horizon else np.nan,
                        'Dividendos acumulados (divisa cotización)':rec['dividends']*fx,
                        'Estado validación':'CONDICIONAL' if np.isfinite(target) else 'N/D',
                        'Reinversión terminal (%)':terminal_reinvestment*100 if 'DCF' in method else np.nan,
                        'ROIC terminal implícito (%)':terminal_roic*100 if 'DCF' in method else np.nan,
                        'Peso terminal EV (%)':terminal/(1+w)**len(flows)/enterprise*100 if 'DCF' in method and np.isfinite(enterprise) else np.nan,
                        'EPS previsto (divisa financiera)':rec['eps'],
                        'PER aplicado (x)':mp if method=='PER forward' else np.nan,
                        'EV/EBITDA aplicado (x)':me if method=='EV/EBITDA forward' else np.nan,
                        'WACC (%)':w*100 if 'DCF' in method else np.nan,
                        'G terminal (%)':tg_s*100 if 'DCF' in method else np.nan,
                        'Deuda neta utilizada (miles MM)':rec['nd']/1e9,
                        'Moneda':quote_currency,
                        'Limitación':'Sin consenso; datos TTM retrasados respecto a cotización; deuda neta aproximada; hipótesis de ciclo y múltiples'})
    reverse=[]
    for horizon in (1,3):
        base=next((r for r in projected if r['Escenario']=='Base' and r['Año futuro']==horizon),None)
        e=base['EPS normalizado (divisa contable)'] if base else np.nan
        reverse.append({'Horizonte (años)':horizon,
          'PER implícito dado EPS normalizado':ratio(px,e*fx),
          'Crecimiento EPS implícito desde EPS último anual (%)':
            ((px/(f(df['EPS diluido'].iloc[-1])*fx*pe_ref))**(1/horizon)-1)*100
             if len(df) and f(df['EPS diluido'].iloc[-1])>0 and np.isfinite(pe_ref) and pe_ref>0 and np.isfinite(fx) and fx>0 and px>0 else np.nan,
          'Advertencia':'PER propio/peer futuro es una hipótesis de mercado, no una probabilidad'})
    risk_rows=[]
    for key,value,default_source in [('TIPO_LIBRE_RIESGO',rf,'SUPUESTO nominal por moneda, plazo no verificado'),
        ('PRIMA_RIESGO_MERCADO',env_float('PRIMA_RIESGO_MERCADO',.055),'SUPUESTO ERP'),
        ('BETA',beta,'Yahoo; ventana no verificada'),('COSTE_DEUDA',kd,wacc_note)]:
        date=os.environ.get('VALUACION_'+key+'_FECHA','')
        expiry=os.environ.get('VALUACION_'+key+'_CADUCIDAD','')
        risk_rows.append({'Parámetro':key,'Valor':value,'Moneda':financial_currency,
            'Fuente':os.environ.get('VALUACION_'+key+'_FUENTE',default_source),
            'Fecha fuente':date or 'N/D','Válido hasta':expiry or 'N/D',
            'Fecha consulta':str(now.date()),'Estado':'NO_VERIFICADO'})
        if expiry and pd.Timestamp(expiry)<now:
            check('Caducidad '+key,False,'Override caducado; bloquea objetivos',True)
    if any(x['Estado']=='BLOQUEO' for x in checks):
        for row in valued:
            row['Precio objetivo (divisa cotización)']=np.nan
            row['Potencial (%)']=np.nan; row['Rentabilidad anualizada (%)']=np.nan
            row['Retorno total (%)']=np.nan; row['Estado validación']='BLOQUEO'
    from comparables_definiciones import verified_coverage
    return FundamentalResult(assumptions,pd.DataFrame(projected),pd.DataFrame(valued),pd.DataFrame(dcf),
                             pd.DataFrame(checks),peer_table,pd.DataFrame(roic),pd.DataFrame(reverse),
                             bridge,ttm_table,peer_refs,peer_universe,pd.DataFrame(risk_rows),roic_ttm,verified_coverage(peers,now,info.get('valuation_accounting_basis')))
