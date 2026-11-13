"""Proceso aislado para el motor opcional heredado (sus overrides usan entorno)."""
import json,sys
from entorno_ejecucion import configure_runtime
from auditoria_io import restore_frame,frame_payload
from modelo_fundamental import build_fundamental_model

if __name__=='__main__':
    configure_runtime()
    p=json.load(sys.stdin);kwargs=p['kwargs'];kwargs['quarterly']=restore_frame(p['quarterly']) if p['quarterly'] is not None else None
    if kwargs.get('share_schedule'):kwargs['share_schedule']={int(k):v for k,v in kwargs['share_schedule'].items()}
    result=build_fundamental_model(restore_frame(p['annual']),restore_frame(p['peers']),**kwargs)
    print(json.dumps({k:frame_payload(getattr(result,k)) for k in ['valuation','checks','dcf_detail','projected','risk_parameters','peer_definitions']},ensure_ascii=False,allow_nan=False))
