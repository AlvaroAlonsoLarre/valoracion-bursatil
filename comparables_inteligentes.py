# -*- coding: utf-8 -*-
"""Descubrimiento y selección automatizados de comparables de acciones.

Fuentes: Yahoo Finance (yfinance Industry/Sector, Search y, de modo optativo,
EquityQuery). El texto de la actividad es una señal heurística, NO un dictamen
sobre competencia directa ni exposición por segmentos.

La selección automática no necesita presets. Un ticker manual es una opción
separada y NO supera los controles de datos ni los filtros de múltiplos.
"""
from __future__ import annotations

from collections import Counter
import json
import math
import os
from pathlib import Path
import re
import unicodedata

import numpy as np
import pandas as pd

CONFIG_PATH = Path(__file__).with_name('comparables_config.json')

STOP = set('''a an and are as at be been being by can company companies corporation corp business
businesses co com develops developed develop designing design designs distribution distributes
for from has have having in including includes into is it its of on or our provides
provide providing their the these those this through to under using via was were which
with worldwide also primarily operations operates offer offers offering services products
product solutions solution technology technologies market markets customers customer
international global inc ltd limited plc holdings group headquartered operates engaged
focused various across among other related well based includes sells sell available
north south united states america approximately segments segment operates develops
manufactures manufacturing manufacture manufacturer enterprise enterprises industry
industries year years management operates commercial operates operates provides
'''.split())

# Normalización de términos técnicos, sin depender de un ticker concreto.
TERM_MAP = {
 'memories':'memory', 'semiconductors':'semiconductor', 'chips':'chip',
 'microprocessors':'processor','processors':'processor',
 'applications':'application','platforms':'platform',
 'datacenters':'datacenter','data-centers':'datacenter',
 'cloud-based':'cloud','subscriptions':'subscription',
 'software-as-a-service':'saas', 'solid-state':'ssd',
 'dynamic-random-access':'dram', 'artificial-intelligence':'ai',
 'graphics-processing':'gpu', 'servers':'server',
 'storage-devices':'storage', 'databases':'database',
}


def load_config():
    try:
        with CONFIG_PATH.open(encoding='utf-8') as f:
            d = json.load(f)
            return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def selected_candidates(ticker):
    """Solo ajustes del usuario. Por defecto NO usa presets MSFT/SK.

    VALUACION_COMPARABLES='ORCL,SAP,...' permite anular/ampliar el catálogo.
    VALUACION_MODO_COMPARABLES=catalogo admite listas antiguas bajo petición.
    """
    ticker = str(ticker).upper()
    user = os.environ.get('VALUACION_COMPARABLES', '').strip()
    mode = os.environ.get('VALUACION_MODO_COMPARABLES','automatico').lower().strip()
    if user:
        selected = [{'ticker': t.strip().upper(), 'grupo':'Manual',
                     'justificacion':'Incorporación manual opcional'}
                    for t in re.split(r'[,;\s]+',user) if t.strip()]
    elif mode in ('catalogo','catalog','legacy'):
        selected = load_config().get(ticker,{}).get('candidatos', [])
    else:
        selected = []
    result = {}
    for item in selected:
        t=str(item.get('ticker','')).upper().strip()
        if t != ticker and re.fullmatch(r'[A-Z0-9][A-Z0-9.\-^=]{0,24}', t):
            result[t] = {
                'Grupo económico': item.get('grupo','Manual'),
                'Justificación económica':item.get('justificacion',''),
                'Origen curado':'Manual' if user else 'Catálogo opcional',
            }
    return result


def economic_seeds(ticker):
    """Ruta complementaria de descubrimiento; no otorga elegibilidad."""
    return [x['ticker'] for x in load_config().get(str(ticker).upper(),{}).get('candidatos',[])]


def normalize_ticker(t):
    t = str(t or '').upper().strip()
    return t if re.fullmatch(r'[A-Z0-9][A-Z0-9.\-^=]{0,24}',t) else None


def _tokens(text):
    if not isinstance(text,str):return []
    text=unicodedata.normalize('NFKD',text).encode('ascii','ignore').decode('ascii').lower()
    text=re.sub(r'[^a-z0-9]+',' ',text)
    toks=[]
    for w in text.split():
        if len(w)<3 or w in STOP or w.isdecimal():continue
        toks.append(TERM_MAP.get(w,w))
    return toks


def _profile(info):
    info=info if isinstance(info,dict) else {}
    return ' '.join(str(info.get(k) or '') for k in
                    ('longBusinessSummary','industry','industryKey','sector'))


def _cosine_tfidf(texts):
    """TF-IDF simple entre empresa objetivo y candidatos; no requiere sklearn."""
    docs=[_tokens(t)[:1000] for t in texts]
    freq=Counter()
    for tokens in docs:freq.update(set(tokens))
    n=len(docs)
    vectors=[]
    for toks in docs:
        counts=Counter(toks)
        total=sum(counts.values()) or 1
        vec={word:(1+math.log(count))*(1+math.log((n+1)/(freq[word]+1)))
             for word,count in counts.items()}
        norm=math.sqrt(sum(v*v for v in vec.values())) or 1
        vectors.append({key:v/norm for key,v in vec.items()})
    base=vectors[0]
    sims=[]
    for v in vectors[1:]:
        keys=base.keys() & v.keys()
        sims.append(sum(base[k]*v[k] for k in keys))
    return sims


def _num(x):
    try:
        n=float(x)
        return n if np.isfinite(n) else np.nan
    except (ValueError,TypeError):return np.nan


def _match_target(peer,target, fields):
    return any(str(peer.get(k,'')).lower().strip()==str(target.get(k,'')).lower().strip()
               and str(target.get(k,'')).strip() for k in fields)


def discover_candidates(yf,ticker,target_info, *, region=None, max_candidates=95,
                        soft_timeout=True):
    """Descubre emisores sin ticker preseleccionado.

    Orden: Industry local + US + mercados globales -> Search por actividad ->
    screener de industria (solo si Yahoo acepta valor) -> Sector local/US.
    Falla parcialmente sin detener la valoración. Devuelve {ticker: metadata}.
    """
    target_info=target_info or {}
    exclude=str(ticker).upper()
    industry_key=target_info.get('industryKey')
    industry_name=target_info.get('industry')
    sector_key=target_info.get('sectorKey')
    area=(region or '').upper() or 'US'
    regions=[]
    for r in (area,'US','KR','TW','JP','DE','GB'):
        if r not in regions:regions.append(r)
    override=os.environ.get('VALUACION_REGIONES_PEERS','').strip()
    if override:
        regions=[r.strip().upper() for r in override.split(',') if len(r.strip())==2]
    # Lista internacional más amplia para semiconductores y otras empresas globales.
    # Se limita a 4 regiones adicionales para evitar consultas excesivas.
    industry_regions=regions[:6]
    candidates={}
    def add(symbol,origin,priority=2):
        symbol=normalize_ticker(symbol)
        # Reservar ~35% de universo para Search y Sector, incluso si Industry
        # devuelve decenas de símbolos de un mismo sector en el primer mercado.
        industry_cap=max(20,int(max_candidates*.63))
        if priority<=1 and origin.startswith(('Industria Yahoo','Crecimiento industria','Screener industria')) and len(candidates)>=industry_cap:
            return
        if symbol and symbol!=exclude and len(candidates)<max_candidates:
            if symbol not in candidates or priority<candidates[symbol]['Prioridad origen']:
                candidates[symbol]={'Ticker':symbol,'Origen candidatos':origin,
                                    'Prioridad origen':priority,
                                    'Capitalización de screener':np.nan}
    def data_frame(df,origin,priority):
        if not isinstance(df,pd.DataFrame) or df.empty:return
        col=next((c for c in df.columns if str(c).lower() in ('symbol','ticker','tickersymbol')),None)
        if col:
            for s in df[col].head(max_candidates).tolist():add(s,origin,priority)
        else:
            for s in df.index[:max_candidates]:
                if isinstance(s,str) and re.search('[a-zA-Z]',s):add(s,origin,priority)
    errors=[]
    if industry_key and hasattr(yf,'Industry'):
        for reg in industry_regions:
            if len(candidates)>=max_candidates:break
            try:
                obj=yf.Industry(industry_key,region=reg)
                # Limitar por mercado, en vez de dejar que el primero monopolice
                # el presupuesto (p.ej., todo Corea y ningún competidor US/TW).
                before=len(candidates)
                top=obj.top_companies
                data_frame(top.head(13) if isinstance(top,pd.DataFrame) else None,'Industria Yahoo '+reg,0)
                if len(candidates)-before<9 and len(candidates)<max_candidates:
                    try:
                        growth=obj.top_growth_companies
                        data_frame(growth.head(6) if isinstance(growth,pd.DataFrame) else None,'Crecimiento industria '+reg,1)
                    except Exception:pass
            except Exception as e:errors.append('Industry '+reg+': '+str(e)[:85])
    # Yahoo Search identifica emisores relacionados con producto y tecnología,
    # más allá de las etiquetas genéricas sector/industria.
    token_counts=Counter(_tokens(target_info.get('longBusinessSummary',''))[:260])
    ignored={'revenue','billion','million','unit','manufacturing','production','sales',
             'electronic','systems','information','services','devices','consumer'}
    kw=[t for t,c in token_counts.most_common(25) if t not in ignored and (c>=2 or len(t)>=5)]
    phrases=[]
    if industry_name:phrases.append(industry_name)
    if kw:phrases.append(' '.join(kw[:3]))
    if len(kw)>=5:phrases.append(' '.join(kw[2:5]))
    if hasattr(yf,'Search'):
        for query in dict.fromkeys(phrases[:3]):
            if len(candidates)>=max_candidates:break
            try:
                search=yf.Search(query,max_results=15,news_count=0,lists_count=0,
                                 include_cb=False,raise_errors=False)
                for x in getattr(search,'quotes',[]) or []:
                    if isinstance(x,dict) and x.get('quoteType','EQUITY') in ('EQUITY','ETF'):
                        # ETF no es un comparable operativo.
                        if x.get('quoteType','EQUITY')=='EQUITY':
                            add(x.get('symbol'),'Búsqueda actividad: '+query[:38],2)
            except Exception as e:errors.append('Search '+query+': '+str(e)[:85])
    if len(candidates)<max_candidates and industry_name and hasattr(yf,'screen') and hasattr(yf,'EquityQuery'):
        # El nombre tiene que coincidir con los códigos de Yahoo; nunca suponemos
        # que un nombre de perfil es un valor de screener válido.
        try:
            vals=getattr(yf.EquityQuery,'valid_values',{})
            allowed=vals.get('industry',[]) if isinstance(vals,dict) else []
            if industry_name in allowed:
                q=yf.EquityQuery('eq',['industry',industry_name])
                resp=yf.screen(q,size=45)
                for r in resp.get('quotes',[]) if isinstance(resp,dict) else []:
                    add(r.get('symbol'),'Screener industria Yahoo',1)
        except Exception as e:errors.append('Screener: '+str(e)[:85])
    if len(candidates)<max_candidates and sector_key and hasattr(yf,'Sector'):
        for reg in regions[:2]:
            try:
                df=yf.Sector(sector_key,region=reg).top_companies
                data_frame(df,'Sector Yahoo '+reg,4)
            except Exception as e:errors.append('Sector '+reg+': '+str(e)[:85])
    return candidates,errors


# Categorías económicas GENERALES, no listas de tickers. No equivalen a
# segmentos contables auditados; sirven para descartar candidatos incompatibles.
ACTIVITY_PATTERNS = {
    'memoria': r'\b(dram|hbm|nand|flash memory|memory chip|memory semiconductor|dynamic random access|ddr[345]|lpddr)\b',
    'fundicion': r'\b(foundr(?:y|ies)|wafer fabrication|contract chip manufactur|semiconductor fabrication|pure.play foundry)\b',
    'diseno_chips': r'\b(chip design|fabless|gpu|microprocessor|cpu|processor designs|graphics processing)\b',
    'equipos_semis': r'\b(lithography|wafer equipment|semiconductor equipment|etching|deposition equipment)\b',
    'software_empresa': r'\b(enterprise software|enterprise application|business software|crm|erp|productivity software|office software|database software|saas)\b',
    'infra_cloud': r'\b(cloud computing|cloud infrastructure|data center infrastructure|hyperscale|azure|aws|cloud platform)\b',
    'ciberseguridad': r'\b(cybersecurity|cyber security|network security|endpoint security|firewall|threat intelligence)\b',
    'dispositivos': r'\b(smartphone|iphone|consumer electronic|mobile device|personal computer|consumer device|wearable)\b',
    'consultoria_it': r'\b(it consulting|consulting services|outsourcing|system integration|professional services)\b',
    'banca': r'\b(retail banking|commercial bank|lending|deposit account|consumer bank)\b',
    'seguros': r'\b(insurance underwrit|life insurance|property and casualty insurance|insurance polic)\b',
    'petroleo_gas': r'\b(oil and gas|crude oil|natural gas|upstream petroleum|hydrocarbon)\b',
    'automovil': r'\b(automotive manufactur|passenger vehicle|automaker|electric vehicle|motor vehicle)\b',
    'farmaceutica': r'\b(pharmaceutical|drug discovery|therapeutic drug|prescription medicine|biopharmaceutical)\b',
    'retail': r'\b(retail stores|supermarket|grocery stores|online retail|e.commerce marketplace)\b',
}


def activity_tags(description):
    txt = str(description or '').lower().replace('–', '-').replace('—','-')
    return {name for name,rx in ACTIVITY_PATTERNS.items() if re.search(rx,txt)}


def activity_conflict(target, peer):
    """Impedimentos sectoriales explícitos. Se penalizan sin afirmar negocios iguales."""
    blockers = (
        ('memoria', ('fundicion','equipos_semis','diseno_chips')),
        ('fundicion', ('memoria','equipos_semis','diseno_chips')),
        ('software_empresa', ('ciberseguridad','dispositivos','consultoria_it')),
        ('ciberseguridad', ('software_empresa','dispositivos','consultoria_it')),
    )
    for focus, opponents in blockers:
        if focus in target and focus not in peer and peer.intersection(opponents):
            if not target.intersection(peer):
                return f'Actividad distinta: {focus} frente a {", ".join(sorted(peer.intersection(opponents)))}'
    return ''


def score_and_filter(peers, ticker, *, target_margin=np.nan, target_growth=np.nan,
                     target_cap=np.nan, curated=None, target_info=None,
                     max_peers=10, min_peers=3, return_universe=False, as_of=None):
    """Una sola clasificación para TODO el universo y para las referencias.

    - Confianza Baja NUNCA es elegible.
    - No se fuerza a alcanzar un número de comparables.
    - Se exige coincidencia económica y evidencia textual; el sector por sí solo no basta.
    - Las medianas PER/EV/EBITDA se calculan por separado con datos válidos.
    - `return_universe` expone trazabilidad completa sin volver a clasificar.
    """
    from multiple_evidence import validate_multiple
    import json
    evidence_date=pd.Timestamp(as_of or pd.Timestamp.now()).normalize()
    curated=curated if curated is not None else selected_candidates(ticker)
    info=target_info if isinstance(target_info,dict) else {}
    empty=pd.DataFrame()
    if peers is None or peers.empty:
        result=(empty,np.nan,np.nan,empty)
        return (*result,empty) if return_universe else result
    df=peers.drop_duplicates('Ticker').copy().reset_index(drop=True)
    base_desc=str(info.get('longBusinessSummary') or '')
    target_full=_profile(info)
    target_tags=activity_tags(base_desc)
    target_industry=str(info.get('industryKey') or '').strip().lower()
    target_sector=str(info.get('sectorKey') or '').strip().lower()
    texts=[target_full]+[str(r.get('Descripción actividad') or '')+' '+str(r.get('Industria') or '') for _,r in df.iterrows()]
    sims=_cosine_tfidf(texts)
    result=[]
    for i,(_,r) in enumerate(df.iterrows()):
        sym=str(r.get('Ticker') or '').upper()
        if not sym or sym==ticker.upper(): continue
        peer_desc=str(r.get('Descripción actividad') or '')
        tags=activity_tags(peer_desc)
        overlap=target_tags & tags
        union=target_tags | tags
        overlap_score=len(overlap)/len(union) if union else 0.0
        same_ind=bool(target_industry and target_industry==str(r.get('Industria clave') or '').lower())
        same_sec=bool(target_sector and target_sector==str(r.get('Sector clave') or '').lower())
        sem=max(0.,float(sims[i]))
        mismatch=activity_conflict(target_tags,tags)
        has_evidence=bool(_tokens(base_desc)) and bool(_tokens(peer_desc))
        # Señales sin similitud semántica ni actividad nunca se convierten en pares
        # por la simple coincidencia de la etiqueta sectorial.
        sufficient=(
            (same_ind and sem>=.23) or
            (same_ind and sem>=.145 and overlap_score>=.25) or
            (same_sec and sem>=.29) or
            (same_sec and sem>=.17 and overlap_score>=.38) or
            (sem>=.37 and overlap_score>=.25)
        )
        eligible=bool(has_evidence and sufficient and not mismatch and (same_sec or same_ind or sem>=.42))
        confidence=('Alta' if eligible and sem>=.32 and (same_ind or overlap_score>=.38) else
                    'Media' if eligible else 'Baja')
        peer_margin=_num(r.get('Margen operativo (%)'))
        peer_growth=_num(r.get('Crecimiento ventas (%)'))
        score=50*sem+25*overlap_score+(12 if same_ind else 5 if same_sec else 0)
        if np.isfinite(peer_margin) and np.isfinite(_num(target_margin)):
            score+=8*math.exp(-abs(peer_margin-target_margin)/25)
        if np.isfinite(peer_growth) and np.isfinite(_num(target_growth)):
            score+=5*math.exp(-abs(peer_growth-target_growth)/30)
        peer_ccy=str(r.get('Divisa cotización') or '').upper()
        target_ccy=str(info.get('currency') or '').upper()
        cap=_num(r.get('Capitalización (miles de millones)'))
        if peer_ccy and peer_ccy==target_ccy and np.isfinite(cap) and cap>0 and np.isfinite(_num(target_cap)) and target_cap>0:
            score+=4*math.exp(-abs(math.log(cap/target_cap))/3)
        p_definition,pe,p_errors,p_meta=validate_multiple(r,'PER',evidence_date,info.get('valuation_accounting_basis'))
        ev_definition,ev,ev_errors,ev_meta=validate_multiple(r,'EV/EBITDA',evidence_date,info.get('valuation_accounting_basis'))
        p_ok=bool(p_definition and eligible and np.isfinite(pe) and 2<=pe<=65 and peer_margin>0)
        ev_ok=bool(ev_definition and eligible and np.isfinite(ev) and 3<=ev<=38 and peer_margin>0)
        notes=p_errors+ev_errors
        if not p_definition:notes.append('PER sin definición GAAP/NTM comprobada')
        if not ev_definition:notes.append('EV/EBITDA sin NTM y perímetro de deuda comprobados')
        if not has_evidence:notes.append('Descripción del negocio insuficiente')
        if mismatch:notes.append(mismatch)
        if not sufficient:notes.append('Similitud insuficiente; no usar solo sector/industria')
        if not eligible:notes.append('Confianza baja: NO utilizar para valorar')
        if not p_ok:notes.append('PER no utilizable (beneficio/múltiplo/calidad)')
        if not ev_ok:notes.append('EV/EBITDA no utilizable (beneficio/múltiplo/calidad)')
        row=r.to_dict()
        row.update({
            'Grupo económico':'Automático · actividad corroborada' if eligible else 'Candidato no comparable',
            'Justificación económica':', '.join(sorted(overlap)) or 'Sin actividad específica común identificada',
            'Puntuación económica (0-100)':round(min(100,score),1),
            'Similitud de actividad (0-100)':round(100*sem,1),
            'Solapamiento actividades (0-100)':round(100*overlap_score,1),
            'Actividades objetivo':', '.join(sorted(target_tags)),
            'Actividades candidato':', '.join(sorted(tags)),
            'Confianza en comparabilidad':confidence,
            'Misma industria':same_ind, 'Mismo sector':same_sec,
            'Elegible':eligible,'PER admisible':p_ok,'EV/EBITDA admisible':ev_ok,
            'PER forward (x)':pe,'EV/EBITDA (x)':ev,
            'PER cohorte':json.dumps([p_meta.get(k) for k in ('basis','start','end','debt_perimeter')]),
            'EV cohorte':json.dumps([ev_meta.get(k) for k in ('basis','start','end','debt_perimeter')]),
            'Observación':'; '.join(notes) or 'Actividad similar; validar segmentos económicos',
        })
        result.append(row)
    if not result:
        values=(empty,np.nan,np.nan,empty)
        return (*values,empty) if return_universe else values
    full=pd.DataFrame(result).sort_values(
        ['Elegible','Puntuación económica (0-100)'],ascending=[False,False]
    ).reset_index(drop=True)
    selected=full.loc[full['Elegible']].head(max_peers).copy().reset_index(drop=True)
    def issuer_key(row):
        ev=row.get('Evidencia TTM')
        cik=ev.get('payload',{}).get('cik') if isinstance(ev,dict) else None
        return 'CIK:'+str(cik).lstrip('0') if cik else str(row.get('Empresa') or row.get('Emisor id') or row['Ticker']).strip().upper()
    # Una clase adicional no crea otro comparable económico.
    full['Emisor económico']=full.apply(issuer_key,axis=1)
    target_name=str(info.get('longName') or '').strip().upper()
    target_cik='CIK:'+str(info.get('valuation_cik')).lstrip('0') if info.get('valuation_cik') else ''
    seen=set()
    for index,row in full.iterrows():
        key=row['Emisor económico']
        if key in seen or key in (target_name,target_cik):
            full.loc[index,['Elegible','PER admisible','EV/EBITDA admisible']]=False
            full.loc[index,'Observación']+='; clase duplicada o mismo emisor objetivo'
        elif row['Elegible']:seen.add(key)
    selected=full.loc[full['Elegible']].head(max_peers).copy().reset_index(drop=True)
    refs=[]
    def metric_reference(label,allowed):
        values=pd.to_numeric(selected.loc[selected[allowed],label],errors='coerce').replace([np.inf,-np.inf],np.nan).dropna()
        ids=selected.loc[selected[allowed]].copy()
        ids['issuer_key']=ids.apply(lambda r:str(r.get('Emisor id') or r.get('Empresa') or r['Ticker']).strip().upper(),axis=1)
        ids=ids.drop_duplicates('issuer_key')
        cohort='PER cohorte' if allowed=='PER admisible' else 'EV cohorte'
        if len(ids) and ids[cohort].nunique()>1:
            refs.append({'Método':label,'Mediana':np.nan,'Observaciones':len(ids),
                         'Estado':'BLOQUEADO: cohortes contables/horizontes/perímetros heterogéneos',
                         'Dispersión max/min':np.nan})
            return np.nan
        values=pd.to_numeric(ids[label],errors='coerce').dropna()
        n=len(values)
        if n<min_peers:
            refs.append({'Método':label,'Mediana':np.nan,'Observaciones':n,
                         'Estado':f'BLOQUEADO: {n}/{min_peers} comparables válidos con confianza media/alta',
                         'Dispersión max/min':np.nan})
            return np.nan
        center=float(values.median()); mad=float((values-center).abs().median())
        if mad>0 and n>=5:
            filtered=values[(values-center).abs()<=3.5*1.4826*mad]
            if len(filtered)>=min_peers:values=filtered
        spread=float(values.max()/values.min()) if values.min()>0 else np.nan
        too_dispersed=np.isfinite(spread) and spread>3.5
        conf_ok=bool((selected.loc[selected[allowed],'Confianza en comparabilidad']=='Alta').any())
        # No forzar una valoración cuando todos son apenas medianos y la distribución
        # está muy dispersa: cuantificar incertidumbre en vez de inventar precisión.
        blocked=too_dispersed and not conf_ok
        status=('BLOQUEADO: gran dispersión y sin comparables de confianza alta' if blocked else
                'REVISAR: múltiplos muy dispersos' if too_dispersed else
                'Mediana de comparables de confianza media/alta')
        value=np.nan if blocked else float(values.median())
        refs.append({'Método':label,'Mediana':value,'Observaciones':len(values),
                     'Estado':status,'Dispersión max/min':spread})
        return value
    per=metric_reference('PER forward (x)','PER admisible')
    ev=metric_reference('EV/EBITDA (x)','EV/EBITDA admisible')
    reference=pd.DataFrame(refs)
    values=(selected,per,ev,reference)
    return (*values,full) if return_universe else values
