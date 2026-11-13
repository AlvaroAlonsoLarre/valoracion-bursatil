from pathlib import Path
import json
import os
import subprocess
import sys
import pandas as pd
import pytest
from auditoria_io import write_snapshot,read_snapshot,valuation_registry,assess
from ejecutar_analisis import save_summary,run
from cobertura import build_manifest
from referencias_oficiales import comprobar_ir


def test_snapshot_roundtrip_and_cli_integration(tmp_path,model_inputs):
    args=dict(model_inputs);annual=args.pop('annual');peers=args.pop('peers')
    target=tmp_path/'inputs.json'
    digest=write_snapshot(target,annual,peers,args)
    a,p,k,payload=read_snapshot(target)
    pd.testing.assert_frame_equal(a,annual,check_dtype=False)
    pd.testing.assert_frame_equal(k['quarterly'],args['quarterly'],check_dtype=False)
    result=subprocess.run([sys.executable,'ejecutar_analisis.py','--snapshot',str(target),'--outdir',str(tmp_path/'replay')],capture_output=True,text=True)
    assert result.returncode==0,result.stdout+result.stderr
    summary=json.loads((tmp_path/'replay/OTHER_resumen.json').read_text())
    tables=pd.read_excel(tmp_path/'replay/valoracion_OTHER_replay.xlsx',sheet_name=None)
    registry=summary['Registro valoraciones']
    assert len(registry)==len(tables['Registro valoraciones'])==21
    assert summary['input_sha256']==digest
    assert {r['method_id'] for r in registry}==set(tables['Registro valoraciones']['method_id'])
    pd.testing.assert_series_equal(pd.Series([r['price'] for r in registry],dtype=float),tables['Registro valoraciones']['price'],check_names=False)


def test_registry_preserves_historical_and_fundamental_separately(build):
    r=build();history=pd.DataFrame([{'Escenario':'Medio','Horizonte (años)':1,'Precio objetivo':731.11},
                                 {'Escenario':'Medio','Horizonte (años)':3,'Precio objetivo':1185.34}])
    registry=valuation_registry(r.valuation,history,pd.DataFrame(),as_of='2026-01-15',fy_date='2025-12-31',
        ttm_date='2025-12-31',currency='USD',source='fixture',freshness='NO_VERIFICADO')
    assert len(registry)==23
    rows=registry.query("method_id=='historical_eps_pe'")
    assert list(rows['price'])==[731.11,1185.34]
    assert set(rows['flow_period'])=={'FY'}
    assert set(rows['validation_state'])=={'SENSIBILIDAD_HISTORICA'}


def test_runner_preserves_blocked_artifacts_and_returns_nonzero(tmp_path,build):
    r=build(fx=float('nan'))
    sheets={'Control modelo':r.checks,'Registro valoraciones':pd.DataFrame()}
    excel=tmp_path/'fixture.xlsx';pd.DataFrame({'x':[1]}).to_excel(excel,index=False)
    assert save_summary('OTHER',tmp_path,excel,sheets,pd.Timestamp('2026-01-01'))==2
    data=json.loads((tmp_path/'OTHER_resumen.json').read_text())
    assert data['auditoria']['estado_financiero']=='BLOQUEO' and excel.exists()


def test_full_runner_subprocess_workbook_integration(tmp_path,build,monkeypatch):
    # Exercise the real runner's subprocess/export path without a remote provider.
    r=build()
    registry=valuation_registry(r.valuation,pd.DataFrame(),pd.DataFrame(),as_of='2026-01-15',fy_date='2025-12-31',
        ttm_date='2025-12-31',currency='USD',source='fixture',freshness='NO_VERIFICADO')
    def fake_engine(cmd,cwd,**kw):
        assert kw['env']['VALUACION_TICKER']=='OTHER'
        with pd.ExcelWriter(Path(cwd)/'valoracion_completa_OTHER.xlsx') as writer:
            r.checks.to_excel(writer,sheet_name='Control modelo',index=False)
            registry.to_excel(writer,sheet_name='Registro valoraciones',index=False)
        return subprocess.CompletedProcess(cmd,0,'log retained','')
    monkeypatch.setattr('ejecutar_analisis.subprocess.run',fake_engine)
    monkeypatch.setattr('auditoria_io.provenance',lambda:{'sha':'test'})
    assert run('OTHER',tmp_path,12,'')==0
    assert (tmp_path/'OTHER_ejecucion.log').exists()
    data=json.loads((tmp_path/'OTHER_resumen.json').read_text())
    assert data['auditoria']['estado_financiero']=='PARCIAL'
    assert not data['auditoria']['publicable']


def test_manifest_requires_both_tickers_same_sha(tmp_path):
    for ticker in ['MSFT','000660.KS']:
        (tmp_path/f'{ticker}_resumen.json').write_text(json.dumps({'ticker':ticker,'provenance':{'sha':'abc'}}))
    assert build_manifest(tmp_path,['MSFT','000660.KS'],'abc')['complete']
    assert not build_manifest(tmp_path,['MSFT','000660.KS'],'different')['complete']
    (tmp_path/'000660.KS_resumen.json').unlink()
    assert not build_manifest(tmp_path,['MSFT','000660.KS'],'abc')['complete']


def test_official_ir_blocks_stale_sk_and_checks_units():
    refs=json.loads(Path('referencias_oficiales.json').read_text())
    class Response:
        text=' '.join(refs['000660.KS']['evidence_tokens']);content=text.encode()
        def raise_for_status(self):pass
    get=lambda *a,**kw:Response()
    q=pd.DataFrame({'Ingresos':[1.]},index=pd.to_datetime(['2026-06-30']))
    result=comprobar_ir('000660.KS',q,'KRW','2026-11-11',requests_get=get)
    assert result['status']=='BLOQUEO' and result['newer_filing_confirmed']
    assert result['comparisons'][0]['IR (unidades)']==104.6155e12
    assert result['comparisons'][0]['Estado']=='N/D'
    assert comprobar_ir('OTHER',q,'KRW','2026-11-11',requests_get=get)['status']=='NO_VERIFICADO'
    assert comprobar_ir('000660.KS',q,'USD','2026-11-11',requests_get=get)['status']=='NO_VERIFICADO'


def test_workflow_yaml_is_valid_and_has_no_publication_writes():
    import yaml
    workflows=list(Path('.github/workflows').glob('*.yml'))
    assert len(workflows)==1
    data=yaml.load(workflows[0].read_text(encoding='utf-8'),Loader=yaml.BaseLoader)
    assert {'pruebas','pruebas_windows','valorar','cobertura'}==set(data['jobs'])
    assert data['jobs']['pruebas_windows']['runs-on']=='windows-latest'
    assert data['permissions']=={'contents':'read'}
    assert 'pull_request' in data['on']


def test_failed_engine_retains_log_and_failure_summary(tmp_path,monkeypatch):
    monkeypatch.setattr('ejecutar_analisis.subprocess.run',lambda *a,**kw:subprocess.CompletedProcess([],1,'','provider failed'))
    monkeypatch.setattr('auditoria_io.provenance',lambda:{'sha':'test'})
    assert run('OTHER',tmp_path,12,'')==1
    assert 'provider failed' in (tmp_path/'OTHER_ejecucion.log').read_text()
    assert json.loads((tmp_path/'OTHER_resumen.json').read_text())['estado_tecnico']=='ERROR'


@pytest.mark.parametrize('ticker',['MSFT','000660.KS'])
def test_frozen_real_inputs_keep_unsupported_targets_unavailable(ticker):
    from modelo_fundamental import build_fundamental_model
    path=Path('docs/auditoria_2026-11-11/inputs')/(ticker+'_after.json')
    annual,peers,kwargs,payload=read_snapshot(path)
    result=build_fundamental_model(annual,peers,**kwargs)
    if ticker=='MSFT':
        assert result.valuation['Precio objetivo (divisa cotización)'].isna().all()
        assert 'Agregado D&A y otros' in result.checks.to_string()
    else:
        assert result.valuation.empty
        assert kwargs['recent_results_check']['status']=='BLOQUEO'
    assert kwargs['financial_currency']==kwargs['quote_currency']==('USD' if ticker=='MSFT' else 'KRW')
