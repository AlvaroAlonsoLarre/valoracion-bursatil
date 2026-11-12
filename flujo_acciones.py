"""Composición común para terminal, replay, Excel y dashboard; sin red al recalcular."""
from types import SimpleNamespace
import numpy as np
import pandas as pd
from analisis_acciones import build_stock_analysis,sector_type
from auditoria_io import clean


def stock_tables(annual,peers,kwargs,history,settings=None,optional_environment=None):
    result=build_stock_analysis(annual,peers,history=history,settings=settings,**kwargs)
    tables={
        'Resumen':pd.DataFrame([{'Concepto':k,'Valor':v} for k,v in result.summary.items()]),
        'Diagnosticos':result.diagnostics,'Valoracion EPS PER':result.valuation,'Proyeccion EPS':result.projected,
        'Supuestos EPS PER':result.assumptions,'Estado metodos':result.methods,'Control por metodo':result.controls,
        'Comparables seleccionados':result.peers.drop(columns=['Evidencia múltiplos','Evidencia TTM'],errors='ignore'),
        'Universo comparables':result.universe.drop(columns=['Evidencia múltiplos','Evidencia TTM'],errors='ignore'),
        'Referencias historicas':history,'Estadisticas 5 y 10':result.history_statistics,'Base TTM y balance':result.base_ttm,
        'Financieros anuales':annual.reset_index(),'Resultados trimestrales':kwargs['quarterly'].reset_index() if kwargs.get('quarterly') is not None else pd.DataFrame()}
    registry=[]
    for _,r in result.valuation.iterrows():
        main=r['Método']=='EPS × PER'
        registry.append({'method_id':'eps_pe_projected' if main else 'price_fcf_contrast','scenario':r['Escenario'],
            'scenario_type':'principal_eps_pe' if main else 'contraste_fcf','horizon_years':r['Horizonte (años)'],
            'valuation_date':result.summary['as_of'],'target_date':r.get('Fecha objetivo'),'currency':r['Moneda'],
            'price':r['Precio objetivo'],'validation_state':r['Estado'],'source':r.get('Origen PER'),
            'limitation':r['Limitación'],'flow_period':r.get('Periodo EPS','TTM')})
    tables['Registro valoraciones']=pd.DataFrame(registry)
    optional=optional_models(annual,peers,kwargs,settings or {},optional_environment)
    if optional is not None:
        tables.update({'Valoracion opcional':optional.valuation,'Control opcionales':optional.checks,
            'DCF detalle':optional.dcf_detail,'Proyeccion opcional':optional.projected,'Parametros riesgo':optional.risk_parameters,
            'Comparables forward requisitos':optional.peer_definitions})
        for label,pattern in [('DCF','DCF'),('EV/EBITDA','EV/EBITDA')]:
            v=optional.valuation
            found=v[v['Método'].str.contains(pattern,regex=False)] if not v.empty else v
            ok=not found.empty and found['Precio objetivo (divisa cotización)'].notna().any()
            tables['Estado metodos'].loc[tables['Estado metodos']['Método'].eq(label),'Estado']='ERROR' if getattr(optional,'error',False) else 'CONDICIONAL' if ok else 'BLOQUEO'
        for _,row in optional.valuation.iterrows():
            h=int(row['Horizonte (años)']);is_dcf='DCF' in row['Método']
            registry.append({'method_id':('dcf_fcff_present' if h==0 else 'dcf_fcff_future') if is_dcf else 'peer_ev_ebitda_ntm',
                'scenario':row['Escenario'],'scenario_type':'opcional_dcf' if is_dcf else 'opcional_ev_ebitda',
                'horizon_years':h,'valuation_date':result.summary['as_of'],'target_date':row.get('Fecha objetivo aprox.'),
                'currency':kwargs['quote_currency'],'price':row['Precio objetivo (divisa cotización)'],
                'validation_state':row.get('Estado validación','CONDICIONAL') if pd.notna(row['Precio objetivo (divisa cotización)']) else 'BLOQUEO',
                'source':kwargs.get('source','Modelo opcional'),'limitation':row.get('Limitación',''),
                'flow_period':'FCFF proyectado' if is_dcf else 'EBITDA NTM proyectado'})
        tables['Registro valoraciones']=pd.DataFrame(registry)
        result.summary['available_targets']=int(tables['Registro valoraciones']['price'].notna().sum())
        result.summary['optional_available']=int(tables['Registro valoraciones'].loc[tables['Registro valoraciones']['scenario_type'].str.startswith('opcional'),'price'].notna().sum())
        tables['Resumen']=pd.DataFrame([{'Concepto':k,'Valor':v} for k,v in result.summary.items()])
    return result,tables


def optional_models(annual,peers,kwargs,settings,environment=None):
    if not settings.get('advanced') or sector_type(kwargs.get('info') or {})!='OPERATIVA':return None
    import os,subprocess,sys,json
    from pathlib import Path
    from auditoria_io import frame_payload,restore_frame
    scalars={k:v for k,v in kwargs.items() if k!='quarterly'}
    payload={'annual':frame_payload(annual),'peers':frame_payload(peers),'kwargs':clean(scalars),
        'quarterly':frame_payload(kwargs['quarterly']) if kwargs.get('quarterly') is not None else None}
    env=os.environ.copy()
    names={'WACC','TIPO_LIBRE_RIESGO','PRIMA_RIESGO_MERCADO','BETA','COSTE_DEUDA','RIESGO_PAIS',
        'PARAMETROS_MONEDA','ERP_INCLUYE_PAIS','CRECIMIENTO_TERMINAL','CRECIMIENTO_VENTAS','TASA_IMPOSITIVA',
        'VAR_CAPITAL_TRABAJO_PCT','CRECIMIENTO_ACCIONES','PAGOS_ACCIONISTAS_SOBRE_VENTAS','EMPRESA_CICLICA','MARGEN_NORMALIZADO'}
    keys={'VALUACION_'+key for key in names}
    for name in ['TIPO_LIBRE_RIESGO','PRIMA_RIESGO_MERCADO','BETA','COSTE_DEUDA']:
        keys.update('VALUACION_'+name+s for s in ['_FECHA','_FUENTE','_CADUCIDAD'])
    if environment is not None:
        for key in keys:
            if key in environment:env[key]=str(environment[key])
            else:env.pop(key,None)
    for key,name in [('wacc','VALUACION_WACC'),('terminal_growth','VALUACION_CRECIMIENTO_TERMINAL')]:
        if key in settings.get('optional_assumptions',{}):env[name]=str(settings['optional_assumptions'][key])
    try:
        process=subprocess.run([sys.executable,str(Path(__file__).with_name('opcionales_worker.py'))],
            input=json.dumps(payload,ensure_ascii=False,allow_nan=False),env=env,capture_output=True,text=True,timeout=90)
        if process.returncode:raise ValueError(process.stderr[-500:])
        result=SimpleNamespace(**{k:restore_frame(v) for k,v in json.loads(process.stdout).items()})
        if not result.valuation.empty:result.valuation=result.valuation[~result.valuation['Método'].str.contains('PER forward',regex=False)].copy()
        return result
    except (subprocess.SubprocessError,ValueError,OSError) as exc:
        return SimpleNamespace(error=True,valuation=pd.DataFrame(),checks=pd.DataFrame([{'Estado':'ERROR','Detalle':str(exc)[:500]}]),
            dcf_detail=pd.DataFrame(),projected=pd.DataFrame(),risk_parameters=pd.DataFrame(),peer_definitions=pd.DataFrame())


def tables_summary(ticker,tables,provenance=None):
    from auditoria_io import assess
    result={'schema_version':'stock-dashboard-v1','ticker':ticker,'provenance':provenance or {},'estado_tecnico':'COMPLETADO',
            'auditoria':assess(tables)}
    for key,table in tables.items():result[key]=clean(table.to_dict('records'))
    return result


def analysis_from_snapshot(payload,settings=None):
    from auditoria_io import restore_frame
    from filing_review import components_reconciliation
    from fuentes_fundamentales import ttm_reconciliation
    frames={k:restore_frame(v) for k,v in payload['frames'].items()}
    historical={k:restore_frame(v) for k,v in payload.get('historical',{}).items()}
    kwargs={**payload['kwargs'],'quarterly':frames.get('quarterly')}
    model=payload.get('evidence',{}).get('stock_model',{})
    chosen=model.get('settings',{}) if settings is None else settings
    result,tables=stock_tables(frames['annual'],frames['peers'],kwargs,
        historical.get('Referencia histórica auditada',pd.DataFrame()),chosen,optional_environment=payload.get('assumption_environment',{}))
    evidence=payload.get('evidence',{});official=evidence.get('official_fundamentals',{});ir=evidence.get('ir',{})
    discovered=pd.DataFrame(evidence.get('peer_discovery',[]))
    if not discovered.empty:
        full=tables['Universo comparables']
        missing=discovered[~discovered['Ticker'].isin(full['Ticker'])] if 'Ticker' in full else discovered
        tables['Universo comparables']=pd.concat([full,missing.assign(Elegible=False,Observación='Sin descarga/cobertura')],ignore_index=True)
    for key in ['Fuentes SEC']:
        if key in historical:tables[key]=historical[key]
    tables.update({'Fuentes fundamentales':pd.DataFrame(official.get('changes',[])).drop(columns=['Componentes'],errors='ignore'),
        'Pendientes fundamentales':pd.DataFrame({'Incidencia':official.get('issues',[])}),
        'Actualidad resultados':pd.DataFrame([kwargs.get('recent_results_check') or {}]),
        'Conciliacion TTM':ttm_reconciliation(kwargs['quarterly'],frames['annual'],kwargs['as_of'],kwargs['fiscal_end_date']),
        'Componentes CAPEX DA':components_reconciliation(kwargs['quarterly']),
        'Revision filings':pd.DataFrame(evidence.get('filing_review',[])),
        'Fuentes comparables':pd.DataFrame(evidence.get('peer_sources',[])),
        'Fuentes comparables TTM':pd.DataFrame(evidence.get('peer_ttm_sources',[])),
        'Contraste IR':pd.DataFrame(ir.get('comparisons',[])),'Extraordinarios IR':pd.DataFrame(ir.get('extraordinary',[]))})
    return result,tables


def excel_bytes(tables):
    import io
    stream=io.BytesIO()
    with pd.ExcelWriter(stream,engine='openpyxl') as writer:
        for key,table in tables.items():table.to_excel(writer,sheet_name=key[:31],index=False)
    return stream.getvalue()
