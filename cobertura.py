"""Manifiesto de cobertura por ticker/SHA, independiente de suficiencia financiera."""
import argparse
import json
from pathlib import Path


def build_manifest(directory,tickers,sha=None):
    found={}
    for path in Path(directory).rglob('*_resumen.json'):
        data=json.loads(path.read_text())
        ticker=data.get('ticker')
        if ticker not in tickers:continue
        if ticker in found:raise ValueError('Resumen duplicado para '+ticker)
        found[ticker]=data
    rows=[]
    for ticker in tickers:
        data=found.get(ticker)
        seen_sha=(data or {}).get('provenance',{}).get('sha')
        complete=data is not None and (sha is None or seen_sha==sha)
        rows.append({'ticker':ticker,'covered':complete,'sha':seen_sha,
                     'financial_status':data.get('auditoria',{}).get('estado_financiero','ERROR') if data else 'AUSENTE',
                     'input_sha256':data.get('input_sha256') if data else None})
    return {'schema':'coverage-v1','expected_sha':sha,'complete':all(r['covered'] for r in rows),'tickers':rows}


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--directory',required=True)
    ap.add_argument('--tickers',nargs='+',default=['MSFT','000660.KS']);ap.add_argument('--sha');ap.add_argument('--output',required=True)
    args=ap.parse_args();manifest=build_manifest(args.directory,args.tickers,args.sha)
    Path(args.output).write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    print(json.dumps(manifest,ensure_ascii=False));return 0 if manifest['complete'] else 2

if __name__=='__main__':raise SystemExit(main())
