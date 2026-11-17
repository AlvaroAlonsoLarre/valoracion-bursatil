"""Reproduce las dos consultas guardadas y compara tabla, captura y Excel/JSON, sin red.

Desde la raíz: python docs/seguimiento_completo_2026-11-16/validar_capturas.py
"""
from pathlib import Path
import io,json,sys,tempfile,zipfile
from openpyxl import load_workbook
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'docs/v7_integrada_2026-11-13'))
from validar_evidencias import equal_cell
from flujo_acciones import analysis_from_snapshot,excel_bytes,tables_summary
from seguimiento_metricas import summarize
from seguimiento_servicio import Service
from seguimiento_store import Store
from grafico_cotizacion import chart_data
from auditoria_io import clean


def main():
    folder=Path(__file__).resolve().parent
    expected=json.loads((folder/'consultas_reales.json').read_text(encoding='utf-8'));result={}
    with zipfile.ZipFile(folder/'capturas_msft_nvda.zip') as z,tempfile.TemporaryDirectory() as tmp:
        store=Store(Path(tmp)/'Álvaro 日本');target=Store(Path(tmp)/'Importado')
        for ticker in ['MSFT','NVDA']:
            p=json.loads(z.read(ticker+'_inputs.json'));r,tables=analysis_from_snapshot(p);m=summarize(p,r)
            assert r.summary==expected[ticker]['summary']
            assert m['ev_fy']==expected[ticker]['ev_fy']
            assert m['informative_peers']==expected[ticker]['informative_peers']
            assert m['row']['Cobertura QoQ']==expected[ticker]['qoq_coverage']=='20/20'
            Service(store).save_capture(p)
            tables['Grafico cotizacion']=chart_data(p,r.summary,r.valuation,'1 año','3 años')
            exported=tables_summary(ticker,tables);wb=load_workbook(io.BytesIO(excel_bytes(tables)))
            count=0
            for key,rows in exported.items():
                if not isinstance(rows,list) or not rows or not isinstance(rows[0],dict):continue
                ws=wb[key[:31]];headers=[c.value for c in ws[1]]
                assert headers==list(rows[0]) and ws.max_row==len(rows)+1
                for i,row in enumerate(rows,2):
                    for j,column in enumerate(headers,1):
                        assert equal_cell(ws.cell(i,j).value,row[column]),(ticker,key,i,column)
                        count+=1
            eps=r.valuation[r.valuation['Método'].eq('EPS × PER')]
            assert eps['Precio objetivo'].notna().sum()==6
            for _,row in eps.iterrows():
                endpoints=tables['Grafico cotizacion']
                found=endpoints[endpoints['Serie'].eq(row['Escenario'])&endpoints['Fecha'].eq(row['Fecha objetivo'])]
                assert len(found)==1 and equal_cell(found.iloc[0]['Precio'],row['Precio objetivo'])
            result[ticker]={'celdas_excel_json':count,'objetivos_eps_per':6,'base_1y':r.summary['target_1y'],'base_3y':r.summary['target_3y'],'qoq':'20/20','ev_fy_reproducible':True}
        target.import_list(json.dumps(store.export()))
        for ticker in result:
            m=target.entry(ticker)['metrics']
            assert m['summary']==expected[ticker]['summary'] and m['ev_fy']==expected[ticker]['ev_fy']
            assert m['row']['Cobertura QoQ']=='20/20'
            result[ticker]['importacion_sin_red']=True
    (folder/'consistencia_actual.json').write_text(json.dumps(clean(result),ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
