"""Verificación offline; ejecutar con el Python del proyecto y el historial Git disponible."""
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import shutil
import numpy as np
import pandas as pd

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]
BASE='25d358ce47e2ecedaed2065c7c0952e57bd88d72'
sys.path.insert(0,str(REPO))
from auditoria_io import read_snapshot
from modelo_fundamental import build_fundamental_model
from dcf_audit import audit_dcf

SCRIPT='''
import sys,json,os
sys.path.insert(0,sys.argv[1])
from auditoria_io import read_snapshot,clean
from modelo_fundamental import build_fundamental_model
annual,peers,kwargs,payload=read_snapshot(sys.argv[2])
for key,value in payload.get('assumption_environment',{}).items():os.environ[key]=value
result=build_fundamental_model(annual,peers,**kwargs)
print(json.dumps(clean({'valuation':result.valuation.to_dict('records'),
 'blockers':result.checks[result.checks['Estado'].eq('BLOQUEO')].to_dict('records')}),allow_nan=False))
'''


def no_constant(value):raise ValueError('JSON no finito: '+value)


def evaluate(code,ticker):
    data=subprocess.check_output([sys.executable,'-c',SCRIPT,str(code),str(HERE/'inputs'/(ticker+'_before.json'))],text=True)
    return json.loads(data)


def main():
    for file in HERE.rglob('*.json'):json.loads(file.read_text(),parse_constant=no_constant)
    expected=pd.read_csv(HERE/'comparacion_entradas_fijas.csv')
    with tempfile.TemporaryDirectory(prefix='audit_stages_') as temporary:
        base=Path(temporary)/'base';base.mkdir()
        files=subprocess.check_output(['git','ls-tree','--name-only',BASE],cwd=REPO,text=True).splitlines()
        for file in files:
            if Path(file).suffix in ('.py','.json'):
                (base/file).write_bytes(subprocess.check_output(['git','show',BASE+':'+file],cwd=REPO))
        stages=[base]
        for stage in [1,2]:
            target=Path(temporary)/str(stage);shutil.copytree(base,target)
            overlays=['filing_review.py','fuentes_fundamentales.json']
            if stage==2:overlays+=['comparables_inteligentes.py','comparables_definiciones.py','multiple_evidence.py']
            for file in overlays:shutil.copy2(REPO/file,target/file)
            stages.append(target)
        stages.append(REPO)
        for ticker in ['MSFT','000660.KS']:
            previous=None
            for stage,code in enumerate(stages):
                data=evaluate(code,ticker)
                if previous is not None:
                    assert data['blockers']==previous['blockers']
                    assert len(data['valuation'])==len(previous['valuation'])
                    for left,right in zip(data['valuation'],previous['valuation']):
                        for key in ['Precio objetivo (divisa cotización)','WACC (%)','G terminal (%)']:
                            if left.get(key) is None:assert right.get(key) is None
                            else:np.testing.assert_allclose(left[key],right[key],rtol=1e-12,atol=1e-12)
                for h in [0,1,3]:
                    match=next((r for r in data['valuation'] if r['Escenario']=='Base' and r['Horizonte (años)']==h and 'DCF' in r['Método']),{})
                    actual=match.get('Precio objetivo (divisa cotización)',float('nan'))
                    target=expected.query('Etapa==@stage and Ticker==@ticker and Horizonte==@h').iloc[0]['Precio DCF Base']
                    np.testing.assert_allclose(float('nan') if actual is None else actual,target,rtol=1e-12,equal_nan=True)
                previous=data
    a,p,k,payload=read_snapshot(HERE/'inputs/MSFT_after.json')
    result=build_fundamental_model(a,p,**k)
    sens,_=audit_dcf(a,p,k,result,references=payload['evidence'].get('risk_references',[]))
    np.testing.assert_allclose(sens['Precio condicional'],pd.read_csv(HERE/'MSFT_sensibilidad.csv')['Precio condicional'],rtol=1e-12)
    rows=pd.read_csv(HERE/'MSFT_formulas_independientes.csv')
    for _,row in rows.iterrows():
        path=result.projected[result.projected['Escenario'].eq(row['Escenario'])].set_index('Año futuro')
        h=int(row['Horizonte'])
        value=result.valuation[result.valuation['Escenario'].eq(row['Escenario'])&result.valuation['Horizonte (años)'].eq(h)&result.valuation['Método'].str.contains('DCF')].iloc[0]
        w=value['WACC (%)']/100;g=value['G terminal (%)']/100
        terminal=path.loc[8,'FCFF (miles MM)']*1e9*(1+g)/(w-g)
        ev=sum(path.loc[y,'FCFF (miles MM)']*1e9/(1+w)**(y-h) for y in range(h+1,9))+terminal/(1+w)**(8-h)
        target=(ev-row['Deuda neta'])/row['Acciones']*k['fx']
        np.testing.assert_allclose([ev,target],[row['EV recalculado'],row['Precio modelo']],rtol=1e-12)
        fcff=path['NOPAT (miles MM)']+path['D&A (miles MM)']-path['CAPEX (miles MM)']-path['Variación capital trabajo (miles MM)']
        np.testing.assert_allclose(fcff,path['FCFF (miles MM)'],rtol=1e-12)
    print('OK: JSON, comparación por etapas, bloqueos, 27 sensibilidades y nueve DCF/FCFF independientes')


if __name__=='__main__':main()
