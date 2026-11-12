"""Contraste económico y paridad Excel/JSON/replay de toda la muestra, sin red."""
import argparse,json,hashlib,sys,re
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from auditoria_io import clean
from flujo_acciones import analysis_from_snapshot
from verificar_generalizacion import verify_formulas


def summary(path):
    data=json.loads(path.read_text())
    return data,{r['Concepto']:r['Valor'] for r in data['Resumen']}


def verify(after,before,previous,output):
    output.mkdir(exist_ok=True,parents=True);rows=[];evidence=[];sensitivity=[];relative=[]
    for path in sorted(after.glob('*/*_resumen.json')):
        data,s=summary(path);ticker=data['ticker'];capture=path.with_name(ticker+'_inputs.json')
        p=json.loads(capture.read_text());r,tables=analysis_from_snapshot(p)
        assert data['input_sha256']==hashlib.sha256(capture.read_bytes()).hexdigest()
        xls=pd.read_excel(path.with_name(data['excel']),sheet_name=None)
        old,old_s=summary(before/ticker/(ticker+'_resumen.json'))
        original,original_s=summary(previous/ticker/(ticker+'_resumen.json'))
        numeric_checks=0
        for table in ['Valoracion EPS PER','Proyeccion EPS','Supuestos EPS PER','Sensibilidad EPS PER','Expectativas implicitas','Puente recurrencia','Recurrencia trimestral']:
            expected=tables[table];export=pd.DataFrame(data[table]);excel=xls[table[:31]]
            assert len(expected)==len(export)==len(excel),(ticker,table,'row count')
            for col in expected:
                if not pd.api.types.is_numeric_dtype(expected[col]):
                    def normalized(value):
                        if pd.isna(value):return None
                        if isinstance(value,pd.Timestamp) or (isinstance(value,str) and re.match(r'^\d{4}-\d{2}-\d{2}(?:T|$)',value)):
                            return pd.Timestamp(value).isoformat()
                        return str(value)
                    if len(expected):
                        left=[normalized(v) for v in expected[col]]
                        assert left==[normalized(v) for v in export[col]],(ticker,table,col,'JSON text')
                        assert left==[normalized(v) for v in excel[col]],(ticker,table,col,'Excel text')
                    continue
                left=pd.to_numeric(expected[col],errors='coerce').to_numpy(dtype=float,na_value=np.nan)
                for candidate in [export,excel]:
                    if len(expected):
                        right=pd.to_numeric(candidate[col],errors='coerce').to_numpy(dtype=float,na_value=np.nan)
                        assert np.allclose(left,right,rtol=1e-11,atol=1e-9,equal_nan=True),(ticker,table,col)
                numeric_checks+=1
        for key in ['price','target_1y','target_3y','fair_value']:
            expected=r.summary[key];actual=s[key]
            assert (pd.isna(expected) and actual is None) or np.isclose(expected,actual,rtol=1e-11),(ticker,key)
        sens=tables['Sensibilidad EPS PER']
        for _,v in sens.iterrows():
            if v['Cambio']==0:
                target=r.summary['target_1y' if v['Horizonte (años)']==1 else 'target_3y']
                assert np.isclose(target,v['Precio sensibilidad'],rtol=1e-11)
        implied=tables['Expectativas implicitas'];pbase=r.projected.query("Escenario=='Base'") if not r.projected.empty else pd.DataFrame()
        if len(implied) and len(pbase):
            pbase=pbase.set_index('Año futuro')
            for _,v in implied.iterrows():
                eps=pbase.loc[v['Año EPS'],'EPS financiero']
                if eps>0:assert np.isclose(v['PER implícito']*eps*s['per_share_fx'],s['price'],rtol=1e-11)
        a=r.assumptions.query("Escenario=='Base'").set_index('Parámetro')['Valor'].to_dict()
        if len(pbase) and 'Año futuro' not in pbase:
            base3=pbase.loc[3];attribution=base3['Beneficio común normalizado']/(base3['PBT']-base3['Impuestos'])
            for parameter,delta in [('growth',.05),('margin',.03)]:
                for shift in [-delta,0,delta]:
                    sales=r.summary['revenue_ttm']
                    for step in [1,2,3]:
                        w=(step-1)/2
                        sales*=1+a['growth']+(a['growth_terminal']-a['growth'])*w+(shift if parameter=='growth' else 0)
                    margin=a['margin_terminal']+(shift if parameter=='margin' else 0)
                    pretax=sales*(margin+a['financial_sales'])
                    eps=(pretax-max(0,pretax)*a['tax'])*attribution/base3['Acciones diluidas']
                    relative.append({'Ticker':ticker,'Parámetro':parameter,'Cambio':shift,'EPS Base año 3':base3['EPS financiero'],
                        'EPS sensibilidad año 3':eps,'Cambio relativo EPS (%)':100*(eps/base3['EPS financiero']-1),
                        'Nota':'Variación de EPS; misma variación porcentual de precio sólo si se mantiene fijo un PER positivo. No produce un precio objetivo'})

        row={'Ticker':ticker,'Moneda':s['currency'],'Cotizacion':s['price'],'Base 1a anterior':original_s['target_1y'],
            'Base 3a anterior':original_s['target_3y'],'Base 1a motor anterior mismos datos':old_s['target_1y'],
            'Base 3a motor anterior mismos datos':old_s['target_3y'],'Base 1a final':s['target_1y'],'Base 3a final':s['target_3y'],
            'Objetivos EPS anteriores':old['auditoria']['objetivos_principales_disponibles'],'Objetivos EPS finales':data['auditoria']['objetivos_principales_disponibles'],
            'Crecimiento 1':a['growth'],'Crecimiento 3':a['growth_terminal'],'Margen 1':a['margin'],'Margen 3':a['margin_terminal'],'PER':a['pe'],
            'PER limpio n':int(r.qualified_history['PER admisible económicamente'].eq(True).sum()),
            'Razon no disponible':data['Estado metodos'][0]['Detalle'] if not s['primary_available'] else ''}
        rows.append(row)
        evidence.append({'ticker':ticker,'sha':data['provenance']['sha'],'input_sha256':data['input_sha256'],'paridad_numerica':True,
                         'columnas_comprobadas':numeric_checks,'trayectorias':len(r.projected),'sensibilidades':len(sens),
                         'referencias':clean(r.qualified_history.to_dict('records'))})
        for rec in sens.to_dict('records'):sensitivity.append({'Ticker':ticker,**rec})
    assert len(rows)==13,'Muestra incompleta'
    pd.DataFrame(rows).to_csv(output/'comparacion.csv',index=False)
    pd.DataFrame(sensitivity).to_csv(output/'sensibilidad.csv',index=False)
    pd.DataFrame(relative).to_csv(output/'sensibilidad_relativa.csv',index=False)
    formulas=verify_formulas(after)
    (output/'validacion.json').write_text(json.dumps(clean({'tickers':evidence,'formula_checks':formulas}),ensure_ascii=False,indent=2,allow_nan=False))
    print(pd.DataFrame(rows)[['Ticker','Base 1a motor anterior mismos datos','Base 1a final','Base 3a motor anterior mismos datos','Base 3a final','Objetivos EPS finales']].to_string(index=False))
    print('Paridad 13/13; trayectorias:',len(formulas),'sensibilidades:',len(sensitivity))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--after',type=Path,required=True);parser.add_argument('--before',type=Path,required=True);parser.add_argument('--previous',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    a=parser.parse_args();verify(a.after,a.before,a.previous,a.output)
