"""Capturas y ajustes del único dashboard. No contiene fórmulas financieras."""
from copy import deepcopy
import json
from pathlib import Path
import zipfile
import pandas as pd
from auditoria_io import frame_payload,restore_frame
from analisis_acciones import validate_settings,SCENARIOS,needs_adr_bridge
from historico_acciones import historical_multiples


def prepare_capture(raw):
    p=json.loads(raw)
    if p.get('schema')!='audit-inputs-v1':
        raise ValueError('Se necesita la captura reproducible *_inputs.json, no el JSON de resultados ni un esquema desconocido')
    if not {'annual','peers'}<=set(p.get('frames',{})) or not isinstance(p.get('kwargs'),dict):
        raise ValueError('Captura incompleta: faltan estados financieros o parámetros de moneda/fecha')
    for frame in p['frames'].values():restore_frame(frame)
    historical=p.setdefault('historical',{});evidence=p.setdefault('evidence',{});notes=[]
    model=evidence.setdefault('stock_model',{'version':'stock-dashboard-v1','settings':{}})
    if model.get('version','stock-dashboard-v1')!='stock-dashboard-v1':raise ValueError('Versión del motor de la captura no compatible')
    validate_settings(model.get('settings',{}))
    if 'Referencia histórica auditada' not in historical:
        if 'Precios y splits' in historical:
            a=restore_frame(p['frames']['annual']);prices=restore_frame(historical['Precios y splits']);k=p['kwargs']
            h=historical_multiples(a,prices,k['financial_currency'],k['quote_currency'],k['as_of'],
                is_adr=needs_adr_bridge(k.get('info') or {},k['financial_currency'],k['quote_currency']))
            historical['Referencia histórica auditada']=frame_payload(h)
            notes.append('Referencias reconstruidas desde precios/splits y estados archivados con sus controles originales')
        else:
            historical['Referencia histórica auditada']=frame_payload(pd.DataFrame())
            notes.append('Sin referencias PER ni precios/splits auditables. Se conservan las cuentas; PER automático no disponible, posible PER manual justificado')
    if notes:evidence['compatibilidad_captura']={'notas':notes,'sin_datos_inventados':True}
    return json.dumps(p,ensure_ascii=False,allow_nan=False,indent=2),notes


def default_capture(root,path=None):
    if path:return Path(path).read_text(encoding='utf-8')
    archive=Path(root)/'docs/economia_final_2026-11-12/ejecuciones_1.zip'
    if archive.exists():
        with zipfile.ZipFile(archive) as z:return z.read('final/MSFT/MSFT_inputs.json').decode('utf-8')
    return (Path(root)/'docs/v6_simplificada_2026-11-12/inputs/MSFT_after.json').read_text(encoding='utf-8')


def per_settings(saved,mode,base=20.,down=.2,up=.2,reason='',basis='TTM',exploratory=False):
    result=deepcopy(saved);result.setdefault('scenarios',{})
    if mode not in ('Automático','Manual'):raise ValueError('Modo PER no válido')
    if not 0<=down<1 or not 0<=up<=1:raise ValueError('Distancias PER fuera de rango')
    for name,factor in [('Pesimista',1-down),('Base',1.),('Optimista',1+up)]:
        row=result['scenarios'].setdefault(name,{})
        if mode=='Manual':row['pe']=base*factor
        else:row.pop('pe',None)
        if not row:result['scenarios'].pop(name,None)
    if mode=='Manual':result.update(per_reason=reason.strip(),per_basis=basis)
    else:
        result.pop('per_reason',None);result.pop('per_basis',None)
    result['exploratory_pe']=bool(exploratory)
    return validate_settings(result)


def edited_settings(saved,edited,baseline,labels,pbt_direct=False):
    """Una edición modifica sólo las celdas modificadas; no borra ajustes anteriores."""
    result=deepcopy(saved);result.setdefault('scenarios',{})
    for _,row in edited.iterrows():
        name=row['Escenario'];values=result['scenarios'].setdefault(name,{})
        for key,label in labels.items():
            if key=='pe' or (key=='financial_sales' and pbt_direct):continue
            value=row[label]/100;old=baseline.loc[name,key]
            same=(pd.isna(value) and pd.isna(old)) or (pd.notna(value) and pd.notna(old) and abs(value-old)<1e-12)
            if not same:
                if pd.isna(value):values.pop(key,None)
                else:values[key]=float(value)
        if not values:result['scenarios'].pop(name,None)
    return result


def model_fingerprint(root):
    """Evita reutilizar un cálculo de otra revisión del motor en Streamlit."""
    import hashlib
    digest=hashlib.sha256()
    for name in ['analisis_acciones.py','flujo_acciones.py','historico_acciones.py','revision_economica.py']:
        digest.update(name.encode());digest.update((Path(root)/name).read_bytes())
    return digest.hexdigest()
