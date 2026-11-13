"""Tabla de aceptación de capturas reales, sin red ni precios esperados fijos.

Uso: python verificar_generalizacion.py --before carpeta --after carpeta --output informe
Cada carpeta contiene TICKER/TICKER_inputs.json y TICKER_resumen.json.
"""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from auditoria_io import restore_frame,clean
from modelo_fundamental import quarterly_snapshot
from estados_datos import metric_coverage


def inspect(directory):
    results={}
    for path in Path(directory).rglob('*_resumen.json'):
        s=json.loads(path.read_text(encoding='utf-8'));ticker=s['ticker'];capture=path.with_name(ticker+'_inputs.json')
        if not capture.exists():raise ValueError('Falta captura: '+ticker)
        payload=json.loads(capture.read_text(encoding='utf-8'));kwargs=payload['kwargs'];annual=restore_frame(payload['frames']['annual'])
        quarterly=restore_frame(payload['frames'].get('quarterly',{'columns':[],'index':[],'data':[],'datetime_index':False,'index_name':None}))
        ttm,base,q,notes=quarterly_snapshot(quarterly,annual,pd.Timestamp(kwargs['as_of']),kwargs.get('fiscal_end_date'))
        fields=restore_frame(payload['historical']['Fuentes SEC']) if 'Fuentes SEC' in payload['historical'] else pd.DataFrame()
        found=[];validated=[]
        for year,group in fields.groupby('Ejercicio') if 'Ejercicio' in fields else []:
            available=group[pd.to_numeric(group['Valor original'],errors='coerce').notna()]
            if len(available):found.append(int(year))
            if set(['Ingresos','Beneficio neto','EPS diluido','Acciones diluidas medias'])<=set(available['Campo']):validated.append(int(year))
        h=restore_frame(payload['historical']['Referencia histórica auditada'])
        summary={r['Concepto']:r['Valor'] for r in s.get('Resumen',[])}
        metrics=pd.DataFrame(s.get('Disponibilidad metricas',[]))
        if metrics.empty:
            proxy={**summary,'per_share_fx':kwargs.get('fx',np.nan),'quote_verified':bool(summary.get('quote_verified')),
                   'diluted_source':summary.get('diluted_source','N/D'),'diluted_base':summary.get('diluted_base',np.nan),'price':kwargs.get('price',np.nan)}
            metrics=metric_coverage(ttm,annual,proxy,q.attrs.get('invalid_flows',[]))
        consecutive=1 if len(q) else 0
        for a,b in zip(q.index[::-1],q.index[::-1][1:]):
            if 65<=(a-b).days<=115:consecutive+=1
            else:break
        controls=s.get('Control por metodo',[]);critical=[r['Comprobación'] for r in controls if r.get('Estado') in ('BLOQUEO','BLOQUEADO','NO DISPONIBLE') and r.get('Severidad')=='CRITICO']
        warnings=[r['Comprobación'] for r in controls if r.get('Estado') in ('ADVERTENCIA','REVISAR')]
        prices=[r for r in s.get('Registro valoraciones',[]) if r.get('method_id')=='eps_pe_projected' and r.get('price') is not None]
        required=['Ingresos','Beneficio operativo','Beneficio neto','EPS diluido','Flujo de caja operativo','CAPEX','Flujo de caja libre']
        results[ticker]={'ticker':ticker,'sha':s['provenance']['sha'],'SEC FY disponibles':found,'SEC FY validados':validated,
            'Último trimestre':str(q.index.max().date()) if len(q) else None,'Trimestres consecutivos':consecutive,
            'Cobertura TTM flujos (de 7)':sum(np.isfinite(float(ttm.get(k,np.nan))) for k in required),
            'Métricas disponibles (%)':round(100*pd.to_numeric(metrics['Valor'],errors='coerce').notna().mean(),1),
            'PER histórico observaciones':int(pd.to_numeric(h.get('PER histórico',pd.Series(dtype=float)),errors='coerce').notna().sum()),
            'Comparables económicos':s['auditoria'].get('comparables_elegibles',0),'Comparables PER TTM':s['auditoria'].get('comparables_per_ttm',0),
            'Comparables PER NTM':s['auditoria'].get('comparables_per_ntm',0),'Precios objetivo EPS':len(prices),
            'Base 1 año':summary.get('target_1y'),'Base 3 años':summary.get('target_3y'),'Críticas / ausencias':critical,'Advertencias':warnings,
            'Métricas':clean(metrics.to_dict('records'))}
    return results


def compare(before,after):
    if set(before)!=set(after):raise ValueError('Muestra distinta antes/después')
    rows=[]
    for ticker,new in after.items():
        old=before[ticker]
        row={'Ticker':ticker,'SEC FY disponibles':','.join(map(str,new['SEC FY disponibles'])),'SEC FY validados':','.join(map(str,new['SEC FY validados'])),
            'Último trimestre':new['Último trimestre'],'Trimestres consecutivos':new['Trimestres consecutivos'],
            'TTM flujos antes→después':f"{old['Cobertura TTM flujos (de 7)']}→{new['Cobertura TTM flujos (de 7)']}/7",
            'Métricas % antes→después':f"{old['Métricas disponibles (%)']}→{new['Métricas disponibles (%)']}",
            'PER historia (n)':new['PER histórico observaciones'],'Pares económicos / PER TTM / NTM':f"{new['Comparables económicos']}/{new['Comparables PER TTM']}/{new['Comparables PER NTM']}",
            'Objetivos EPS antes→después':f"{old['Precios objetivo EPS']}→{new['Precios objetivo EPS']}",
            'Base 1a antes':old['Base 1 año'],'Base 1a después':new['Base 1 año'],'Base 3a antes':old['Base 3 años'],'Base 3a después':new['Base 3 años'],
            'Críticas / ausencias':'; '.join(new['Críticas / ausencias']),'Advertencias':'; '.join(new['Advertencias'])}
        rows.append(row)
    return pd.DataFrame(rows)


def verify_formulas(directory):
    rows=[]
    for path in Path(directory).rglob('*_resumen.json'):
        s=json.loads(path.read_text(encoding='utf-8'));ticker=s['ticker'];projections=s.get('Proyeccion EPS',[])
        assumptions={(r['Escenario'],r['Parámetro']):r['Valor'] for r in s['Supuestos EPS PER']}
        summary={r['Concepto']:r['Valor'] for r in s['Resumen']};sales={}
        for r in projections:
            name=r['Escenario'];h=r['Año futuro'];weight=min(1.,(h-1)/2)
            expected_growth=assumptions[name,'growth']+(assumptions[name,'growth_terminal']-assumptions[name,'growth'])*weight
            expected_margin=assumptions[name,'margin']+(assumptions[name,'margin_terminal']-assumptions[name,'margin'])*weight
            expected_sales=sales.get(name,summary['revenue_ttm'])*(1+expected_growth);sales[name]=expected_sales
            tax=assumptions[name,'tax'];pbt=r['EBIT o PBT directo']+r['Resultado no operativo']
            checks=[np.isclose(r['Ingresos'],expected_sales),np.isclose(r['EBIT o PBT directo'],expected_sales*expected_margin),np.isclose(r['PBT'],pbt),
                    np.isclose(r['Impuestos'],max(0,pbt)*tax),np.isclose(r['EPS financiero'],r['Beneficio común normalizado']/r['Acciones diluidas'])]
            if not all(checks):raise AssertionError((ticker,name,h,checks))
            rows.append({'ticker':ticker,'escenario':name,'año':h,'identidades_correctas':True})
        for r in s.get('Valoracion EPS PER',[]):
            if r['Método']=='EPS × PER' and r['Precio objetivo'] is not None:
                assert np.isclose(r['Precio objetivo'],r['EPS aplicado']*r['PER aplicado']*summary['per_share_fx'])
        capture=path.with_name(ticker+'_inputs.json');p=json.loads(capture.read_text(encoding='utf-8'));q=restore_frame(p['frames']['quarterly'])
        if set(['Flujo de caja operativo','CAPEX','Flujo de caja libre'])<=set(q):
            expected=pd.to_numeric(q['Flujo de caja operativo'],errors='coerce')-pd.to_numeric(q['CAPEX'],errors='coerce');actual=pd.to_numeric(q['Flujo de caja libre'],errors='coerce')
            assert np.allclose(expected,actual,equal_nan=True),ticker+' FCF no concilia'
    return rows


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--before',required=True);parser.add_argument('--after',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    before=inspect(args.before);after=inspect(args.after);table=compare(before,after)
    table.to_csv(out/'comparacion.csv',index=False)
    (out/'aceptacion.json').write_text(json.dumps(clean({'before':before,'after':after,'formula_checks':verify_formulas(args.after)}),ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    print(table.drop(columns=['Críticas / ausencias','Advertencias']).to_string(index=False))

if __name__=='__main__':main()
