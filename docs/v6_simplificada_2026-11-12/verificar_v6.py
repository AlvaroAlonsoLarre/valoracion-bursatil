"""Verifica sin red los snapshots, las fórmulas y la comparación con el motor previo.

Necesita el historial Git de 0faccd1… o --baseline-dir con ese checkout.
"""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import numpy as np
import pandas as pd

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT))
from auditoria_io import clean,read_snapshot,assess
from flujo_acciones import analysis_from_snapshot

BASELINE='0faccd1d832d985b7817b999a3ee821d9b24d0b6'
OLD_SCRIPT='''
import sys,json,os
sys.path.insert(0,sys.argv[1])
from auditoria_io import read_snapshot,clean
from modelo_fundamental import build_fundamental_model
annual,peers,kwargs,payload=read_snapshot(sys.argv[2])
# Estas capturas no contienen overrides de riesgo: se comparan los defaults de ambos motores.
result=build_fundamental_model(annual,peers,**kwargs)
print(json.dumps(clean({'valuation':result.valuation.to_dict('records'),'controls':result.checks.to_dict('records')}),ensure_ascii=False,allow_nan=False))
'''


def old_result(directory,snapshot):
    output=subprocess.check_output([sys.executable,'-c',OLD_SCRIPT,str(directory),str(snapshot)],text=True)
    return json.loads(output)


def baseline_copy(folder):
    files=subprocess.check_output(['git','ls-tree','--name-only',BASELINE],cwd=ROOT,text=True).splitlines()
    for name in files:
        if Path(name).suffix in ('.py','.json'):
            (folder/name).write_bytes(subprocess.check_output(['git','show',BASELINE+':'+name],cwd=ROOT))


def verify(baseline):
    comparison=[];formulas=[]
    for ticker in ['MSFT','000660.KS','JNJ','JPM']:
        snapshot=HERE/'inputs'/(ticker+'_after.json');payload=json.loads(snapshot.read_text())
        annual,peers,kwargs,_=read_snapshot(snapshot)
        modern,tables=analysis_from_snapshot(payload)
        stored=json.loads((HERE/'resultados'/(ticker+'_after.json')).read_text())
        assert hashlib.sha256(snapshot.read_bytes()).hexdigest()==stored['input_sha256']
        np.testing.assert_allclose(modern.valuation['Precio objetivo'],pd.DataFrame(stored['Valoracion EPS PER'])['Precio objetivo'],rtol=1e-12,equal_nan=True)
        assert len(tables['Universo comparables'])==stored['auditoria']['total_candidatos']
        previous=old_result(baseline,snapshot)
        previous['code_ref']=BASELINE
        (HERE/'resultados'/(ticker+'_before_fixed.json')).write_text(json.dumps(previous,ensure_ascii=False,indent=2,allow_nan=False))
        optional_settings={**payload['evidence']['stock_model'].get('settings',{}),'advanced':True}
        advanced,advanced_tables=analysis_from_snapshot(payload,optional_settings)
        np.testing.assert_allclose(advanced.valuation['Precio objetivo'],modern.valuation['Precio objetivo'],rtol=1e-12,equal_nan=True)
        keys=['Estado metodos','Valoracion opcional','Control opcionales','Registro valoraciones']
        (HERE/'resultados'/(ticker+'_opcionales.json')).write_text(json.dumps(clean({k:advanced_tables[k].to_dict('records') for k in keys if k in advanced_tables}),ensure_ascii=False,indent=2,allow_nan=False))
        oldvals=pd.DataFrame(previous['valuation']);oldcontrols=pd.DataFrame(previous['controls'])
        old_dcf=oldvals[oldvals['Método'].str.contains('DCF')] if len(oldvals) else oldvals
        old_pe=oldvals[oldvals['Método'].str.contains('PER')] if len(oldvals) else oldvals
        dcf_prices=int(old_dcf['Precio objetivo (divisa cotización)'].notna().sum()) if len(old_dcf) else 0
        pe_prices=int(old_pe['Precio objetivo (divisa cotización)'].notna().sum()) if len(old_pe) else 0
        base_values=modern.valuation[modern.valuation['Método'].eq('EPS × PER')&modern.valuation['Escenario'].eq('Base')].set_index('Horizonte (años)')
        optional_values=advanced_tables.get('Valoracion opcional',pd.DataFrame())
        optional_controls=advanced_tables.get('Control opcionales',pd.DataFrame())
        for h in [1,3]:
            oldbase=old_dcf[old_dcf['Escenario'].eq('Base')&old_dcf['Horizonte (años)'].eq(h)] if len(old_dcf) else pd.DataFrame()
            comparison.append({'Ticker':ticker,'Horizonte':h,'Anterior DCF Base':oldbase.iloc[0]['Precio objetivo (divisa cotización)'] if len(oldbase) else np.nan,
                'Anterior precios DCF':dcf_prices,'Anterior precios PER forward':pe_prices,'Anterior bloqueos globales':int(oldcontrols['Estado'].eq('BLOQUEO').sum()),
                'V6 EPS PER Base':base_values.loc[h,'Precio objetivo'],'V6 precios principales':stored['auditoria']['objetivos_principales_disponibles'],
                'V6 bloqueos compartidos':stored['auditoria']['errores_bloqueantes'],
                'V6 bloqueos opcionales':int(optional_controls['Estado'].eq('BLOQUEO').sum()) if 'Estado' in optional_controls else 0,
                'Comparables económicos seleccionados':len(modern.peers),'Fuente PER':modern.summary['per_source'],
                'Nota':'DCF y EPS/PER son métodos diferentes: no interpretar su diferencia como corrección aritmética'})
        # Contraste de nueve DCF anteriores con el mismo método opcional, sólo donde se aplica.
        if modern.summary['sector_type']=='OPERATIVA' and len(old_dcf) and not optional_values.empty:
            new_dcf=optional_values[optional_values['Método'].str.contains('DCF')]
            np.testing.assert_allclose(pd.to_numeric(old_dcf['Precio objetivo (divisa cotización)'],errors='coerce').to_numpy(dtype=float),pd.to_numeric(new_dcf['Precio objetivo (divisa cotización)'],errors='coerce').to_numpy(dtype=float),rtol=1e-12,equal_nan=True)
        ratio=(pd.to_numeric(annual['EPS diluido'])*pd.to_numeric(annual['Acciones diluidas medias'])/pd.to_numeric(annual['Beneficio neto'])).tail(5).median()
        revenue=modern.summary['revenue_ttm'];shares=modern.summary['diluted_base']
        assumptions=modern.assumptions.pivot(index='Escenario',columns='Parámetro',values='Valor')
        per_basis=modern.valuation[modern.valuation['Método'].eq('EPS × PER')].iloc[0]['Periodo PER']
        for _,row in modern.valuation[modern.valuation['Método'].eq('EPS × PER')].iterrows():
            values=assumptions.loc[row['Escenario']];h=int(row['Horizonte (años)']);year=h+1 if per_basis=='NTM' else h
            future_revenue=revenue*(1+values['growth'])**year
            pbt=future_revenue*values['margin']
            if modern.summary['profit_model']!='PBT directo':pbt+=future_revenue*values['financial_sales']
            common=(pbt-max(0,pbt)*values['tax'])*ratio
            diluted=shares*(1+values['dilution'])**year
            eps=common/diluted
            adr=(payload['evidence']['stock_model'].get('settings',{}).get('adr') or {}).get('ordinary_per_quote_share',1.)
            target=eps*values['pe']*kwargs['fx']*adr if eps>0 else np.nan
            np.testing.assert_allclose(target,row['Precio objetivo'],rtol=1e-12,equal_nan=True)
            formulas.append({'Ticker':ticker,'Escenario':row['Escenario'],'Horizonte':h,'Año EPS aplicado':year,'Modelo beneficio':modern.summary['profit_model'],
                'Ingresos TTM fuente':revenue,'Ingresos futuros':future_revenue,'PBT recalculado':pbt,'Beneficio común recalculado':common,
                'Acciones diluidas proyectadas':diluted,'EPS recalculado':eps,'PER':values['pe'],'Precio recalculado':target,
                'Precio motor':row['Precio objetivo'],'Residual':target-row['Precio objetivo'],'Moneda':kwargs['quote_currency']})
        assert modern.summary['fair_value']==base_values.loc[1,'Precio objetivo']/1.1
        print(ticker,'OK: seis escenarios; opcionales separados; fórmula y replay comprobados')
    pd.DataFrame(comparison).to_csv(HERE/'comparacion_antes_despues.csv',index=False)
    pd.DataFrame(formulas).to_csv(HERE/'formulas_eps_independientes.csv',index=False)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--baseline-dir',type=Path);args=parser.parse_args()
    if args.baseline_dir:verify(args.baseline_dir)
    else:
        with tempfile.TemporaryDirectory(prefix='v6_before_') as path:
            directory=Path(path);baseline_copy(directory);verify(directory)


if __name__=='__main__':main()
