"""Referencias retrospectivas por ejercicio, con base de acción y cobertura explícitas."""
import numpy as np
import pandas as pd


def number(value):
    try:
        result=float(value)
        return result if np.isfinite(result) else np.nan
    except (TypeError,ValueError):return np.nan


def historical_multiples(annual,prices,financial_currency,quote_currency,as_of,*,is_adr=False):
    """Close de Yahoo está ajustado por splits, no por dividendos.

    EPS/acciones SEC se llevan a la misma base mediante eventos posteriores a la
    fecha del filing que reportó cada dato. Sin evidencia de la base, se omite
    la observación afectada; no se aplica el FX de hoy al precio de hace años.
    """
    rows=[];today=pd.Timestamp(as_of).tz_localize(None).normalize()
    market=prices.copy()
    if not market.empty:
        market.index=pd.to_datetime(market.index).tz_localize(None)
        market=market[market.index<=today].sort_index()
    splits=market.get('Stock Splits',pd.Series(dtype=float));splits=splits[splits.notna()&(splits>0)&(splits!=1)]
    def factor(date,reported):
        if 'Stock Splits' not in market:return np.nan,'Serie de acciones corporativas no disponible'
        filed=pd.to_datetime(reported,errors='coerce')
        if pd.notna(filed):
            if filed>today:return np.nan,'Filing posterior a valoración'
            events=splits[splits.index>filed]
            return float(events.prod()),'Base ajustada por splits posteriores al filing'
        if (splits.index>date).any():return np.nan,'Split posterior sin fecha/base del EPS acreditada'
        return 1.,'Sin splits posteriores al cierre en la serie de acciones corporativas'
    for year,row in annual.sort_index().iterrows():
        date=pd.to_datetime(row.get('Fecha cierre fiscal'),errors='coerce')
        record={'Ejercicio':year,'Fecha cierre fiscal':date,'PER histórico':np.nan,'Precio/FCF histórico':np.nan,
            'EPS base cotización':np.nan,'Precio cierre fiscal':np.nan,'Estado base acción':'N/D','Base acción conciliada':False}
        if pd.isna(date) or date>today:
            rows.append(record);continue
        available=market[(market.index<=date)&(market.index>=date-pd.Timedelta(days=7))]
        if available.empty or 'Close' not in available:
            record['Estado base acción']='Sin cierre observado dentro de 7 días';rows.append(record);continue
        px=number(available['Close'].iloc[-1]);record['Precio cierre fiscal']=px
        unit_fx=1. if financial_currency==quote_currency else 100. if financial_currency=='GBP' and quote_currency in ('GBp','GBX','GBPENCE') else .01 if financial_currency in ('GBp','GBX','GBPENCE') and quote_currency=='GBP' else np.nan
        if not np.isfinite(unit_fx) or is_adr:
            record['Estado base acción']='FX histórico o base ADR histórica sin reconciliar';rows.append(record);continue
        eps=number(row.get('EPS continuado diluido'))
        continuing=np.isfinite(eps)
        if not continuing:eps=number(row.get('EPS diluido'))
        record['Definición EPS histórico']='Continuado diluido' if continuing else 'Total diluido'
        shares=number(row.get('Acciones diluidas medias'))
        ef,note=factor(date,row.get('EPS continuado fuente presentado') if continuing else row.get('EPS fuente presentado'));sf,snote=factor(date,row.get('Acciones fuente presentado'))
        current_eps=eps/ef;current_shares=shares*sf
        net=number(row.get('Beneficio neto continuado')) if continuing else number(row.get('Beneficio neto común'))
        if not np.isfinite(net) and not continuing:net=number(row.get('Beneficio neto'))
        # No corregir una divergencia entre EPS/acciones y beneficio común mediante un split supuesto.
        reconciled=np.isfinite(net) and np.isfinite(current_eps*current_shares) and abs(net)>0 and abs(current_eps*current_shares/net-1)<.05
        if not reconciled:
            note+='; EPS × acciones no concilia con beneficio común (<5%)'
        record.update({'EPS base cotización':current_eps*unit_fx,'Factor split EPS':ef,'Factor split acciones':sf,
                       'Estado base acción':note,'Base acción conciliada':bool(reconciled)})
        if reconciled and current_eps>0 and px>0:record['PER histórico']=px/(current_eps*unit_fx)
        ocf=number(row.get('Flujo de caja operativo'));capex=number(row.get('CAPEX'));fcf=ocf-capex
        if reconciled and fcf>0 and current_shares>0 and px>0:record['Precio/FCF histórico']=px*current_shares/(fcf*unit_fx)
        rows.append(record)
    return pd.DataFrame(rows)


def historical_statistics(annual,history):
    rows=[]
    latest=int(annual.index.max()) if len(annual) else 0
    for window in [5,10]:
        a=annual[(annual.index>latest-window)&(annual.index<=latest)]
        h=history[history['Ejercicio'].between(latest-window+1,latest)] if not history.empty else pd.DataFrame()
        if not h.empty:
            h=h[~h['Ejercicio'].duplicated(keep=False)]
            h=h[h.get('Base acción conciliada',pd.Series(False,index=h.index)).eq(True)]
        data={c:pd.to_numeric(a[c],errors='coerce') for c in ['Ingresos','Flujo de caja libre','Beneficio operativo','Beneficio neto','Deuda neta','Deuda total','Margen operativo','Margen neto','ROIC'] if c in a}
        eps_aligned=h.set_index('Ejercicio')['EPS base cotización'].reindex(a.index) if not h.empty and 'EPS base cotización' in h else pd.Series(index=a.index,dtype=float)
        data['EPS diluido']=eps_aligned
        for c in ['PER histórico','Precio/FCF histórico']:
            selected=h[h['PER admisible económicamente'].eq(True)] if c=='PER histórico' and 'PER admisible económicamente' in h else h
            data[c]=pd.to_numeric(selected[c],errors='coerce') if c in selected else pd.Series(dtype=float)
        for metric,series in data.items():
            valid=series.replace([np.inf,-np.inf],np.nan).dropna()
            if metric in ('PER histórico','Precio/FCF histórico'):valid=valid[valid>0]
            # CAGR sólo con ambos extremos de la ventana disponible, no saltando negativos/NAs.
            cagr=np.nan
            if metric in a and len(a)>=2:
                span=int(a.index[-1])-int(a.index[0]);first=number(eps_aligned.iloc[0]) if metric=='EPS diluido' else number(a[metric].iloc[0]);last=number(eps_aligned.iloc[-1]) if metric=='EPS diluido' else number(a[metric].iloc[-1])
                if span>0 and first>0 and last>0:cagr=(last/first)**(1/span)-1
            rows.append({'Indicador':metric,'Ventana (ejercicios)':window,'Observaciones':len(valid),
                'Ejercicios disponibles':len(a),'Cobertura completa':len(a)==window and len(valid)==window,
                'Media':valid.mean(),'Mediana':valid.median(),'P25':valid.quantile(.25),'P75':valid.quantile(.75),
                'CAGR (%)':100*cagr,'Nota':'Retrospectivo, no backtest point-in-time; sólo múltiplos positivos; no rellenar ejercicios'})
    return pd.DataFrame(rows)
