# -*- coding: utf-8 -*-
"""Histórico financiero anual desde SEC EDGAR Company Facts + Inline XBRL.

Devuelve una tabla en unidades originales (USD/EUR/etc.; acciones en unidades;
EPS por acción), hasta los 10 últimos ejercicios fiscales disponibles.
Los datos trimestrales y las métricas de mercado siguen procediendo de Yahoo Finance.
"""
from __future__ import annotations

import re
import warnings
from functools import lru_cache
from typing import Any

import numpy as np
import pandas as pd
import requests
from bs4 import BeautifulSoup

SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
DEFAULT_USER_AGENT = "StockValuationProject/1.0"
ANNUAL_FORMS = {"10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A", "S-1", "S-1/A", "424B4", "10-12B", "10-12B/A"}


def fiscal_year_label(date):
    """Cierres semanales de primeros 7 días de enero pertenecen al FY de diciembre.

    Se conserva siempre la fecha de cierre real. Evita que Jan-01 y Dec-31 del
    mismo año calendario creen un único índice duplicado o un CAGR de cero años.
    """
    day=pd.Timestamp(date)
    return day.year-1 if day.month==1 and day.day<=7 else day.year


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def _num(value: Any) -> float:
    try:
        value = float(value)
        return value if np.isfinite(value) else np.nan
    except (TypeError, ValueError):
        return np.nan


def _date(value: Any) -> pd.Timestamp | pd.NaT:
    try:
        ts = pd.Timestamp(value)
        if ts.tzinfo is not None:
            ts = ts.tz_localize(None)
        return ts.normalize()
    except (TypeError, ValueError):
        return pd.NaT


def _headers(user_agent: str) -> dict[str, str]:
    return {
        "User-Agent": user_agent,
        "Accept-Encoding": "gzip, deflate",
    }


def _get_json(url: str, user_agent: str) -> dict:
    response = requests.get(url, headers=_headers(user_agent), timeout=60)
    response.raise_for_status()
    return response.json()


def cik_from_filing_links(ticker,user_agent,filings=None):
    """Sólo un enlace SEC más ticker exacto en submissions permite el fallback.

    Yahoo descubre el identificador; SEC valida el emisor y sigue aportando las
    cuentas. Ni el nombre parecido ni el ticker base autorizan una identidad.
    """
    if filings is None:
        import yfinance as yf
        filings=yf.Ticker(ticker).sec_filings
    candidates=set()
    for item in filings or []:
        if not isinstance(item,dict):continue
        url=str(item.get('edgarUrl',''))
        match=re.match(r'^https://(?:www\.)?sec\.gov/Archives/edgar/data/(\d+)/',url)
        if match:candidates.add(match.group(1).lstrip('0').zfill(10))
        # Versiones del SDK enlazan a una ficha de filing en Yahoo. Es una pista,
        # nunca prueba de identidad: sigue siendo obligatorio el ticker exacto SEC.
        mirror=re.match(r'^https://finance\.yahoo\.com/sec-filing/'+re.escape(ticker.upper())+r'/\d{10}-\d{2}-\d{6}_(\d+)(?:[?#].*)?$',url)
        if mirror:candidates.add(mirror.group(1).lstrip('0').zfill(10))
    verified=[]
    for cik in sorted(candidates):
        try:
            data=_get_json(SEC_SUBMISSIONS_URL.format(cik=cik),user_agent)
            symbols={str(t).upper().strip() for t in data.get('tickers',[])}
            if str(data.get('cik','')).lstrip('0')==cik.lstrip('0') and ticker.upper().strip() in symbols:
                verified.append((cik,data.get('name')))
        except (requests.RequestException,ValueError,TypeError):continue
    if len(verified)==1:
        warnings.warn('Identidad SEC validada por ticker exacto en submissions; CIK descubierto desde enlace SEC de Yahoo: '+verified[0][0])
        return verified[0]
    return None,None


def resolve_cik(ticker: str, user_agent: str, company_name: str | None = None,
                override_cik: str | None = None) -> tuple[str | None, str | None]:
    """Resuelve ticker a CIK. Admite override; para tickers con sufijo usa alias base conservador."""
    if override_cik:
        return str(override_cik).strip().lstrip("0").zfill(10), "CIK configurado manualmente"

    try:mapping = _get_json(SEC_TICKERS_URL, user_agent)
    except requests.RequestException as exc:
        warnings.warn('Índice ticker SEC no accesible; se contrasta identidad mediante filings/submissions: '+str(exc)[:130])
        try:return cik_from_filing_links(ticker,user_agent)
        except Exception:return None,None
    if isinstance(mapping, dict) and "data" in mapping and "fields" in mapping:
        fields = mapping["fields"]
        rows = [dict(zip(fields, row)) for row in mapping["data"]]
    elif isinstance(mapping, dict):
        rows = list(mapping.values())
    elif isinstance(mapping, list):
        rows = mapping
    else:
        rows = []

    ticker_u = ticker.strip().upper()
    for row in rows:
        if str(row.get("ticker", "")).strip().upper() == ticker_u:
            cik = row.get("cik_str", row.get("cik"))
            return (str(int(cik)).zfill(10), row.get("title", row.get("name"))) if cik else (None, None)

    # Yahoo usa sufijos de bolsa como .MC/.L/.TO; solo probar el ticker base
    # cuando el nombre proporcionado parece corresponder al mismo emisor SEC.
    if "." in ticker_u and company_name:
        base = ticker_u.split(".")[0]
        name_tokens = {x for x in _norm(company_name).split() if len(x) >= 4}
        candidates = []
        for row in rows:
            if str(row.get("ticker", "")).strip().upper() == base:
                title = str(row.get("title", row.get("name", "")))
                title_norm = _norm(title)
                if any(token in title_norm for token in name_tokens):
                    candidates.append(row)
        if len(candidates) == 1:
            row = candidates[0]
            cik = row.get("cik_str", row.get("cik"))
            if cik:
                return str(int(cik)).zfill(10), row.get("title", row.get("name"))
    return None, None


def _unit_ok(unit: str, mode: str, currency: str) -> bool:
    u = _norm(unit)
    c = _norm(currency or "USD")
    if mode == "money":
        return u == c
    if mode == "shares":
        return u in {"share", "shares"}
    if mode == "eps":
        return u in {c + "shares", c + "share", c + "pershare", c + "pershares"} or (u.startswith(c) and "share" in u)
    return True


def _record_matches(record: dict, end_date: str, annual: bool) -> bool:
    if record.get("end") != end_date:
        return False
    start = record.get("start")
    if annual:
        if not start:
            return False
        days = (pd.Timestamp(end_date) - pd.Timestamp(start)).days + 1
        return 330 <= days <= 400
    return not start


def sec_fact(companyfacts: dict, tags: list[str], end_date: str, *, currency: str,
             mode: str = "money", annual: bool = True) -> dict:
    """Busca un hecho XBRL por lista de tags, fin fiscal, unidad y duración."""
    facts = companyfacts.get("facts", {})
    form_rank = {form:i for i,form in enumerate(["10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A", "S-1/A", "S-1", "424B4", "10-12B/A", "10-12B"])}
    for wanted in tags:
        options = []
        for taxonomy, concepts in facts.items():
            concept = concepts.get(wanted)
            if not concept:
                continue
            for unit, records in concept.get("units", {}).items():
                if not _unit_ok(unit, mode, currency):
                    continue
                for rec in records:
                    form = rec.get("form", "")
                    if form not in form_rank or not _record_matches(rec, end_date, annual):
                        continue
                    options.append({
                        "value": _num(rec.get("val")),
                        "tag": f"{taxonomy}:{wanted}",
                        "unit": unit,
                        "form": form,
                        "filed": rec.get("filed", ""),
                        "accn": rec.get("accn", ""),
                    })
        options = [x for x in options if pd.notna(x["value"])]
        if options:
            options.sort(key=lambda x: (form_rank.get(x["form"], 99), x["filed"]), reverse=False)
            best_form_rank = min(form_rank[x["form"]] for x in options)
            same_form = [x for x in options if form_rank[x["form"]] == best_form_rank]
            return max(same_form, key=lambda x: x["filed"])
    return {"value": np.nan, "tag": "No encontrado en CompanyFacts", "unit": "", "form": "", "filed": "", "accn": ""}


def _local_name(tag: Any) -> str:
    return str(getattr(tag, "name", "") or "").split(":")[-1].lower()


def _child_text(element: Any, local: str) -> str | None:
    found = element.find(lambda t: getattr(t, "name", None) and _local_name(t) == local.lower())
    return found.get_text(strip=True) if found else None


def _parse_inline_number(tag: Any) -> float:
    text = tag.get_text("", strip=True).replace("\xa0", " ").replace("−", "-")
    m = re.search(r"\(?\s*[-+]?\d[\d,]*(?:\.\d+)?\s*\)?", text)
    if not m:
        return np.nan
    token = m.group(0).strip().replace(",", "").replace(" ", "")
    negative = token.startswith("(") and token.endswith(")")
    token = token.strip("()")
    try:
        value = float(token)
    except ValueError:
        return np.nan
    if negative or str(tag.get("sign", "")).strip() == "-":
        value = -abs(value)
    try:
        scale = int(tag.get("scale", "0") or 0)
    except (TypeError, ValueError):
        scale = 0
    return value * (10 ** scale)


def parse_inline_xbrl(html: str, filing: dict) -> list[dict]:
    """Extrae hechos Inline XBRL con sus contextos, unidades y metadata de filing."""
    soup = BeautifulSoup(html, "html.parser")
    contexts = {}
    for ctx in soup.find_all(lambda t: getattr(t, "name", None) and _local_name(t) == "context"):
        ctx_id = ctx.get("id")
        if not ctx_id:
            continue
        instant = _child_text(ctx, "instant")
        start = _child_text(ctx, "startdate")
        end = _child_text(ctx, "enddate") or instant
        dimensions = any(_local_name(t) in {"explicitmember", "typedmember"} for t in ctx.find_all(True))
        members=[t.get_text(strip=True) for t in ctx.find_all(True) if _local_name(t) in {"explicitmember", "typedmember"}]
        contexts[ctx_id] = {"instant": instant, "start": start, "end": end, "dimensions": dimensions,"members":members}

    result = []
    for fact in soup.find_all(lambda t: getattr(t, "name", None) and _local_name(t) == "nonfraction"):
        name = fact.get("name")
        ref = fact.get("contextref") or fact.get("contextRef")
        if not name or ref not in contexts:
            continue
        value = _parse_inline_number(fact)
        if pd.isna(value):
            continue
        ctx = contexts[ref]
        days = None
        if ctx.get("start") and ctx.get("end"):
            try:
                days = (pd.Timestamp(ctx["end"]) - pd.Timestamp(ctx["start"])).days + 1
            except Exception:
                pass
        result.append({
            "name": str(name), "local": _norm(str(name).split(":")[-1]),
            "value": value, "unitref": str(fact.get("unitref") or fact.get("unitRef") or ""),
            "start": ctx.get("start"), "end": ctx.get("end"), "instant": ctx.get("instant"),
            "days": days, "dimensions": ctx.get("dimensions", False),"members":ctx.get("members",[]),"scale":fact.get("scale","0"),
            "form": filing.get("form", ""), "filed": filing.get("filing_date", ""),
            "report_date": filing.get("report_date", ""), "accession": filing.get("accession", ""),
            "url": filing.get("url", ""),
        })
    return result


def _filings_for_sec(submissions: dict, cik: str) -> list[dict]:
    recent = submissions.get("filings", {}).get("recent", {})
    result = []
    total = len(recent.get("form", []))
    cik_numeric = str(int(cik))
    for i in range(total):
        form = (recent.get("form", [""] * total)[i] or "")
        if form not in ANNUAL_FORMS:
            continue
        filed = (recent.get("filingDate", [""] * total)[i] or "")
        report_date = (recent.get("reportDate", [""] * total)[i] or "")
        accession = (recent.get("accessionNumber", [""] * total)[i] or "")
        primary = (recent.get("primaryDocument", [""] * total)[i] or "")
        if not (filed and report_date and accession and primary):
            continue
        url = f"https://www.sec.gov/Archives/edgar/data/{cik_numeric}/{accession.replace('-', '')}/{primary}"
        result.append({"form": form, "filing_date": filed, "report_date": report_date,
                       "accession": accession, "primary_document": primary, "url": url})
    result.sort(key=lambda f: (f["report_date"], f["filing_date"]), reverse=True)
    return result


def _annual_periods(companyfacts: dict, submissions: dict, max_years: int) -> list[str]:
    """Identify fiscal year ends, including older periods outside submissions.recent.

    SEC submissions.recent is NOT a 10-year archive. Never use it as the sole
    source of fiscal years. Extract annual revenue fact periods from CompanyFacts
    (including those contained as comparatives in recent 10-K filings).
    """
    dates: set[str] = set()
    fiscal_filing_dates: set[str] = set()
    recent = submissions.get("filings", {}).get("recent", {})
    for form, date in zip(recent.get("form", []), recent.get("reportDate", [])):
        if form in ANNUAL_FORMS and date:
            fiscal_filing_dates.add(str(date))

    facts = companyfacts.get("facts", {})
    revenue_tags = (
        "RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues",
        "SalesRevenueNet", "RevenueFromContractWithCustomerIncludingAssessedTax", "Revenue"
    )
    for concepts in facts.values():
        for tag in revenue_tags:
            concept = concepts.get(tag)
            if not concept:
                continue
            for records in concept.get("units", {}).values():
                for rec in records:
                    if rec.get("form") not in ANNUAL_FORMS:
                        continue
                    if not rec.get("start") or not rec.get("end"):
                        continue
                    try:
                        days = (pd.Timestamp(rec["end"]) - pd.Timestamp(rec["start"])).days + 1
                        if 330 <= days <= 400:
                            dates.add(str(rec["end"]))
                    except (ValueError, TypeError, OverflowError):
                        continue
    # Add the latest filed fiscal year even when the revenue tag is customized;
    # do not infer ten-year coverage from the filings API by itself.
    dates.update(fiscal_filing_dates)
    return sorted(dates)[-max_years:]


def _download_inline_facts(filing: dict, user_agent: str, cache: dict) -> list[dict]:
    accession = filing.get("accession", "")
    if accession in cache:
        return cache[accession]
    response = requests.get(filing["url"], headers=_headers(user_agent), timeout=90)
    response.raise_for_status()
    records = parse_inline_xbrl(response.text, filing)
    cache[accession] = records
    return records


def _inline_fact(filings: list[dict], target_date: str, tags: list[str], currency: str,
                 user_agent: str, cache: dict, *, annual: bool = True) -> dict | None:
    end = pd.Timestamp(target_date)
    candidates = []
    for filing in filings:
        try:
            report = pd.Timestamp(filing["report_date"])
        except Exception:
            continue
        # Buscar el filing más reciente que razonablemente contiene comparativos
        # del ejercicio: mismo ejercicio o hasta tres ejercicios fiscales después.
        if report < end or report > end + pd.Timedelta(days=3 * 366):
            continue
        candidates.append(filing)
    candidates.sort(key=lambda f: (f["report_date"], f["filing_date"]), reverse=True)
    wanted = {_norm(t.split(":")[-1]) for t in tags}
    currency_norm = _norm(currency or "USD")
    for filing in candidates:
        try:
            facts = _download_inline_facts(filing, user_agent, cache)
        except Exception as exc:
            warnings.warn(f"No se pudo leer Inline XBRL de {filing.get('url')}: {exc}")
            continue
        valid = []
        for f in facts:
            if f["local"] not in wanted or f.get("end") != target_date:
                continue
            if annual:
                if not f.get("start") or f.get("days") is None or not 330 <= f["days"] <= 400:
                    continue
            elif f.get("start") or f.get("instant") != target_date:
                continue
            unitref_norm = _norm(f.get("unitref", ""))
            if currency_norm not in unitref_norm:
                continue
            valid.append(f)
        if valid:
            valid.sort(key=lambda f: (bool(f.get("dimensions")), abs((f.get("days") or 365) - 365)))
            best = valid[0]
            return best
    return None


def _fact_value(companyfacts: dict, source_rows: list[dict], key: str, tags: list[str],
                date: str, *, currency: str, mode: str = "money", annual: bool = True) -> float:
    result = sec_fact(companyfacts, tags, date, currency=currency, mode=mode, annual=annual)
    source_rows.append({"Ejercicio": fiscal_year_label(date), "Fecha cierre fiscal": date, "Campo": key,
                        "Valor original": result["value"], "Unidad": result["unit"],
                        "Concepto SEC": result["tag"], "Formulario": result["form"],
                        "Presentado": result["filed"], "Fuente": "CompanyFacts"})
    return result["value"]


def download_sec_annual_history(ticker: str, company_name: str | None = None,
                                financial_currency: str = "USD", years: int = 10,
                                user_agent: str = DEFAULT_USER_AGENT,
                                override_cik: str | None = None, as_of=None) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Descarga los últimos ejercicios fiscales SEC y calcula ratios.

    Si no se localiza un CIK o SEC no aporta datos suficientes, devuelve tabla vacía
    para que el programa llamante decida una alternativa (por ejemplo Yahoo).
    """
    cik, sec_name = resolve_cik(ticker, user_agent, company_name, override_cik)
    if not cik:
        return pd.DataFrame(), pd.DataFrame(), {"CIK": None, "Empresa SEC": None, "Estado": "Ticker no encontrado en SEC"}

    facts = _get_json(SEC_FACTS_URL.format(cik=cik), user_agent)
    submissions = _get_json(SEC_SUBMISSIONS_URL.format(cik=cik), user_agent)
    cutoff=pd.Timestamp(as_of or pd.Timestamp.now()).tz_localize(None).normalize()
    # CompanyFacts es una respuesta actual: excluir hechos presentados o cerrados después del corte.
    for concepts in facts.get('facts',{}).values():
        for concept in concepts.values():
            for unit,records in concept.get('units',{}).items():
                concept['units'][unit]=[r for r in records if r.get('filed') and r.get('end')
                    and pd.Timestamp(r['filed'])<=cutoff and pd.Timestamp(r['end'])<=cutoff]
    currency = (financial_currency or "USD").upper().strip()
    if currency in {"N/A", "NONE", "NO DISPONIBLE", ""}:
        currency = "USD"
    recent=submissions.get('filings',{}).get('recent',{})
    filing_dates=recent.get('filingDate',[])
    indices=[i for i,d in enumerate(filing_dates) if d and pd.Timestamp(d)<=cutoff]
    for key,values in list(recent.items()):
        if isinstance(values,list) and len(values)==len(filing_dates):recent[key]=[values[i] for i in indices]
    filings = [f for f in _filings_for_sec(submissions, cik) if pd.Timestamp(f["filing_date"])<=cutoff]
    dates = _annual_periods(facts, submissions, years)
    if not dates:
        from registration_history import download_registration_history
        return download_registration_history(submissions,cik,user_agent,currency,cutoff)

    inline_cache: dict[str, list[dict]] = {}
    source_rows: list[dict] = []
    output_rows: list[dict] = []

    tags = {
        "Ingresos": ("money", True, ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet", "RevenueFromContractWithCustomerIncludingAssessedTax", "Revenue", "RevenuesNetOfInterestExpense"]),
        "Beneficio bruto": ("money", True, ["GrossProfit"]),
        "Beneficio operativo": ("money", True, ["OperatingIncomeLoss", "OperatingProfitLoss"]),
        "Beneficio neto": ("money", True, ["NetIncomeLoss", "ProfitLoss", "NetIncomeLossAttributableToParent"]),
        "Beneficio neto común": ("money", True, ["NetIncomeLossAvailableToCommonStockholdersBasic"]),
        "Beneficio neto continuado": ("money", True, ["IncomeLossFromContinuingOperations", "ProfitLossFromContinuingOperations"]),
        "EPS continuado diluido": ("eps", True, ["IncomeLossFromContinuingOperationsPerDilutedShare", "IncomeLossFromContinuingOperationsDilutedEarningsPerShare"]),
        "EPS básico": ("eps", True, ["EarningsPerShareBasic", "BasicEarningsLossPerShare"]),
        "EPS diluido": ("eps", True, ["EarningsPerShareDiluted", "DilutedEarningsLossPerShare"]),
        "Acciones diluidas medias": ("shares", True, ["WeightedAverageNumberOfDilutedSharesOutstanding"]),
        "Efectivo": ("money", False, ["CashAndCashEquivalentsAtCarryingValue", "CashAndCashEquivalents", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"]),
        "Inversiones a corto plazo": ("money", False, ["ShortTermInvestments", "AvailableForSaleSecuritiesCurrent", "MarketableSecuritiesCurrent", "ShortTermInvestmentsAvailableForSale"]),
        "Efectivo e inversiones combinado directo": ("money", False, ["CashCashEquivalentsAndShortTermInvestments", "CashCashEquivalentsAndMarketableSecurities"]),
        "Deuda a largo plazo": ("money", False, ["LongTermDebtNoncurrent", "LongTermDebt"]),
        "Activos totales": ("money", False, ["Assets"]),
        "Patrimonio neto": ("money", False, ["StockholdersEquity", "Equity"]),
        "Flujo de caja operativo": ("money", True, ["NetCashProvidedByUsedInOperatingActivities", "CashFlowsFromUsedInOperatingActivities", "NetCashFlowsFromUsedInOperatingActivities"]),
        "CAPEX": ("money", True, ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets", "PaymentsToAcquirePropertyPlantAndEquipmentNetOfProceedsFromSale"]),
        "D&A": ("money", True, ["DepreciationDepletionAndAmortization", "DepreciationAndAmortization"]),
        "Impuestos": ("money", True, ["IncomeTaxExpenseBenefit", "IncomeTaxExpenseContinuingOperations"]),
        "Beneficio antes de impuestos": ("money", True, ["IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest", "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments", "IncomeLossFromContinuingOperationsBeforeIncomeTaxes", "ProfitLossBeforeTax"]),
        "Gastos por intereses": ("money", True, ["InterestExpenseNonOperating", "InterestAndDebtExpense", "InterestExpenseNonOperatingNetOfInterestIncomeExpense", "InterestExpense"]),
        "Recompras de acciones": ("money", True, ["PaymentsForRepurchaseOfCommonStock", "PaymentsForRepurchaseOfEquity", "PaymentsForRepurchaseOfCommonStockIncludingSharesWithheldForTaxes"]),
        "Dividendos": ("money", True, ["PaymentsOfDividendsCommonStock", "PaymentsOfDividends", "PaymentsOfDividendsCommonStockIncludingExtraordinaryDividends"]),
    }

    from revision_economica import INVESTMENT_TAGS
    tags.update({field:('money',True,candidates) for field,candidates in INVESTMENT_TAGS.items()})
    for date in dates:
        row: dict[str, Any] = {"Fecha cierre fiscal": pd.Timestamp(date), "Ejercicio": fiscal_year_label(date)}
        for field, (mode, annual, candidates) in tags.items():
            fact = sec_fact(facts, candidates, date, currency=currency, mode=mode, annual=annual)
            row[field] = fact["value"]
            if field=='EPS diluido':row['EPS fuente presentado']=fact['filed']
            if field=='EPS continuado diluido':row['EPS continuado fuente presentado']=fact['filed']
            if field=='Acciones diluidas medias':row['Acciones fuente presentado']=fact['filed']
            if field=='Gastos por intereses':row['Concepto gasto intereses']=fact['tag']
            source_rows.append({"Ejercicio": fiscal_year_label(date), "Fecha cierre fiscal": date, "Campo": field,
                                "Valor original": fact["value"], "Unidad": fact["unit"], "Concepto SEC": fact["tag"],
                                "Formulario": fact["form"], "Presentado": fact["filed"], "Accession": fact["accn"], "Fuente": "CompanyFacts"})

        # El D&A consolidado de flujo de caja, si está en el filing comparativo, es
        # preferible a sumar conceptos de otras notas. Esto replica la validación MSFT v4.
        inline_da = _inline_fact(filings, date, ["DepreciationAmortizationAndOther"], currency,
                                 user_agent, inline_cache, annual=True)
        row['D&A y otros']=inline_da['value'] if inline_da else np.nan
        row['Definición D&A']='D&A consolidada' if pd.notna(row.get('D&A')) else 'N/D'
        if inline_da and pd.isna(row.get('D&A')):
            row['Definición D&A']='Agregado D&A y otros; no D&A pura'
            row["D&A"] = inline_da["value"]
            source = f"Inline XBRL: {inline_da['name']} (filing {inline_da['report_date']})"
            source_rows = [x for x in source_rows if not (x.get("Campo") == "D&A" and x.get("Ejercicio") == fiscal_year_label(date))]
            source_rows.append({"Ejercicio": fiscal_year_label(date), "Fecha cierre fiscal": date, "Campo": "D&A",
                                "Valor original": inline_da["value"], "Unidad": inline_da["unitref"],
                                "Concepto SEC": inline_da["name"], "Formulario": inline_da["form"],
                                "Presentado": inline_da["filed"], "Fuente": source})
        else:
            source = "CompanyFacts / concepto estándar (definición puede variar)"
        row["Origen D&A"] = source

        # Intereses: si el concepto estandarizado falta, buscar el hecho de las notas Inline XBRL.
        if pd.isna(row.get("Gastos por intereses", np.nan)):
            inline_interest = _inline_fact(filings, date,
                ["InterestExpense", "InterestExpenseNonOperating", "InterestExpenseNonOperatingNetOfInterestIncomeExpense"],
                currency, user_agent, inline_cache, annual=True)
            if inline_interest:
                row["Gastos por intereses"] = abs(inline_interest["value"])
                row['Concepto gasto intereses']=inline_interest['name']
                source_rows = [x for x in source_rows if not (x.get("Campo") == "Gastos por intereses" and x.get("Ejercicio") == fiscal_year_label(date))]
                source_rows.append({"Ejercicio": fiscal_year_label(date), "Fecha cierre fiscal": date,
                                    "Campo": "Gastos por intereses", "Valor original": row["Gastos por intereses"],
                                    "Unidad": inline_interest["unitref"], "Concepto SEC": inline_interest["name"],
                                    "Formulario": inline_interest["form"], "Presentado": inline_interest["filed"],
                                    "Fuente": "Inline XBRL"})

        # Deuda a corto plazo: nunca seleccionar tasas. Usar deuda combinada; si no,
        # sumar papel comercial/préstamos a corto plazo + porción corriente de deuda LP.
        date_nonannual_tags = ["ShortTermBorrowingsAndCurrentPortionOfLongTermDebt",
                               "ShortTermDebtAndCurrentPortionOfLongTermDebt"]
        combined = sec_fact(facts, date_nonannual_tags, date, currency=currency, mode="money", annual=False)
        current_long = sec_fact(facts, ["LongTermDebtCurrent"], date, currency=currency, mode="money", annual=False)
        commercial_paper = sec_fact(facts, ["CommercialPaper", "CommercialPaperOutstanding"], date,
                                    currency=currency, mode="money", annual=False)
        short_borrowings = sec_fact(facts, ["ShortTermBorrowings"], date, currency=currency, mode="money", annual=False)
        source_cp = ""
        if pd.notna(combined["value"]):
            debt_current = combined["value"]
            source_cp = combined["tag"]
        else:
            extra = commercial_paper if pd.notna(commercial_paper["value"]) else short_borrowings
            if pd.notna(extra["value"]) and pd.notna(current_long["value"]):
                debt_current = extra["value"] + current_long["value"]
                source_cp = f"Calculado: {extra['tag']} + {current_long['tag']}"
            elif pd.notna(extra["value"]):
                debt_current = extra["value"]
                source_cp = f"Parcial: {extra['tag']} (sin porción corriente identificada)"
            elif pd.notna(current_long["value"]):
                # Si el CompanyFacts no tiene el papel comercial, usar Inline XBRL para completar.
                inline_extra = _inline_fact(filings, date, ["CommercialPaper", "CommercialPaperOutstanding", "ShortTermBorrowings"],
                                            currency, user_agent, inline_cache, annual=False)
                if inline_extra:
                    debt_current = inline_extra["value"] + current_long["value"]
                    source_cp = f"Calculado: Inline {inline_extra['name']} + {current_long['tag']}"
                else:
                    debt_current = current_long["value"]
                    source_cp = f"Solo {current_long['tag']} (posible saldo parcial)"
            else:
                inline_combined = _inline_fact(filings, date, date_nonannual_tags, currency, user_agent, inline_cache, annual=False)
                if inline_combined:
                    debt_current = inline_combined["value"]
                    source_cp = f"Inline XBRL: {inline_combined['name']}"
                else:
                    debt_current = np.nan
                    source_cp = "No encontrada"
        row["Deuda a corto plazo"] = debt_current
        row["Origen deuda"] = source_cp
        row["Deuda incluye arrendamientos"] = False
        source_rows.append({"Ejercicio": fiscal_year_label(date), "Fecha cierre fiscal": date, "Campo": "Deuda a corto plazo",
                            "Valor original": debt_current, "Unidad": currency, "Concepto SEC": source_cp,
                            "Formulario": "SEC XBRL", "Presentado": "", "Fuente": source_cp})

        # Estandarizar salidas de caja, intereses y recompras como valores positivos.
        for col in ["CAPEX", "Gastos por intereses", "Recompras de acciones", "Dividendos"]:
            if pd.notna(row.get(col, np.nan)):
                row[col] = abs(row[col])

        # Efectivo total: respetar partida conjunta si existe; nunca sumar dos veces.
        if pd.notna(row.get("Efectivo e inversiones combinado directo", np.nan)):
            row["Efectivo e inversiones"] = row["Efectivo e inversiones combinado directo"]
            cash_source = "Etiqueta conjunta SEC"
        elif pd.notna(row.get("Efectivo", np.nan)) and pd.notna(row.get("Inversiones a corto plazo", np.nan)):
            row["Efectivo e inversiones"] = row["Efectivo"] + row["Inversiones a corto plazo"]
            cash_source = "Efectivo + inversiones a corto plazo"
        elif pd.notna(row.get("Efectivo", np.nan)):
            row["Efectivo e inversiones"] = row["Efectivo"]
            cash_source = "Solo efectivo: inversiones no disponibles"
        else:
            row["Efectivo e inversiones"] = np.nan
            cash_source = "No disponible"
        row["Origen efectivo/inversiones"] = cash_source

        # Pasivos de arrendamiento en balance: preferir total, o sumar corriente y no corriente.
        leases = []
        for lease_type, tag_sets in [
            ("operativo", (["OperatingLeaseLiability"], ["OperatingLeaseLiabilityCurrent"], ["OperatingLeaseLiabilityNoncurrent", "OperatingLeaseLiabilityNonCurrent"])),
            ("financiero", (["FinanceLeaseLiability"], ["FinanceLeaseLiabilityCurrent"], ["FinanceLeaseLiabilityNoncurrent", "FinanceLeaseLiabilityNonCurrent"])),
        ]:
            total_tags, cur_tags, noncur_tags = tag_sets
            direct = sec_fact(facts, total_tags, date, currency=currency, mode="money", annual=False)
            cur = sec_fact(facts, cur_tags, date, currency=currency, mode="money", annual=False)
            noncur = sec_fact(facts, noncur_tags, date, currency=currency, mode="money", annual=False)
            if pd.notna(direct["value"]):
                leases.append(direct["value"])
            elif pd.notna(cur["value"]) and pd.notna(noncur["value"]):
                leases.append(cur["value"] + noncur["value"])
        row["Pasivos por arrendamientos"] = sum(leases) if leases else np.nan

        # Métricas derivadas.
        dcp, dlp = row.get("Deuda a corto plazo", np.nan), row.get("Deuda a largo plazo", np.nan)
        row["Deuda total"] = dcp + dlp if pd.notna(dcp) and pd.notna(dlp) else np.nan
        cash_total = row.get("Efectivo e inversiones", np.nan)
        row["Deuda neta"] = row["Deuda total"] - cash_total if pd.notna(row["Deuda total"]) and pd.notna(cash_total) else np.nan
        leases_total = row.get("Pasivos por arrendamientos", np.nan)
        row["Deuda total incl. arrendamientos"] = row["Deuda total"] + leases_total if pd.notna(row["Deuda total"]) and pd.notna(leases_total) else np.nan
        row["Deuda neta incl. arrendamientos"] = row["Deuda total incl. arrendamientos"] - cash_total if pd.notna(row["Deuda total incl. arrendamientos"]) and pd.notna(cash_total) else np.nan
        op, rev = row.get("Beneficio operativo", np.nan), row.get("Ingresos", np.nan)
        net, gross = row.get("Beneficio neto", np.nan), row.get("Beneficio bruto", np.nan)
        fcf = row.get("Flujo de caja operativo", np.nan) - row.get("CAPEX", np.nan) if pd.notna(row.get("Flujo de caja operativo", np.nan)) and pd.notna(row.get("CAPEX", np.nan)) else np.nan
        row["Flujo de caja libre"] = fcf
        row["EBITDA aproximado"] = op + row["D&A"] if pd.notna(op) and pd.notna(row.get("D&A", np.nan)) else np.nan
        row["Tasa fiscal"] = row["Impuestos"] / row["Beneficio antes de impuestos"] if pd.notna(row.get("Impuestos", np.nan)) and pd.notna(row.get("Beneficio antes de impuestos", np.nan)) and row["Beneficio antes de impuestos"] != 0 else np.nan
        row["Margen bruto"] = gross / rev if pd.notna(gross) and pd.notna(rev) and rev != 0 else np.nan
        row["Margen operativo"] = op / rev if pd.notna(op) and pd.notna(rev) and rev != 0 else np.nan
        row["Margen neto"] = net / rev if pd.notna(net) and pd.notna(rev) and rev != 0 else np.nan
        row["Margen FCF"] = fcf / rev if pd.notna(fcf) and pd.notna(rev) and rev != 0 else np.nan
        row["Deuda neta / EBITDA"] = row["Deuda neta"] / row["EBITDA aproximado"] if pd.notna(row["Deuda neta"]) and pd.notna(row["EBITDA aproximado"]) and row["EBITDA aproximado"] != 0 else np.nan
        row["Cobertura de intereses"] = op / row["Gastos por intereses"] if pd.notna(op) and pd.notna(row.get("Gastos por intereses", np.nan)) and row["Gastos por intereses"] != 0 else np.nan
        row["NOPAT aproximado"] = op * (1 - row["Tasa fiscal"]) if pd.notna(op) and pd.notna(row["Tasa fiscal"]) else np.nan
        row["Capital invertido aproximado"] = row["Deuda total"] + row["Patrimonio neto"] - cash_total if pd.notna(row["Deuda total"]) and pd.notna(row.get("Patrimonio neto", np.nan)) and pd.notna(cash_total) else np.nan
        row["ROIC"] = row["NOPAT aproximado"] / row["Capital invertido aproximado"] if pd.notna(row["NOPAT aproximado"]) and pd.notna(row["Capital invertido aproximado"]) and row["Capital invertido aproximado"] != 0 else np.nan
        row["Origen financiero anual"] = "SEC EDGAR CompanyFacts + Inline XBRL"
        row["CIK SEC"] = cik
        output_rows.append(row)

    df = pd.DataFrame(output_rows).sort_values("Fecha cierre fiscal").set_index("Ejercicio")
    audit = pd.DataFrame(source_rows)
    annual_revenue_count = int(pd.to_numeric(df.get("Ingresos"), errors="coerce").notna().sum()) if not df.empty else 0
    latest = df.iloc[-1] if not df.empty else pd.Series(dtype=object)
    if (
        df.empty
        or annual_revenue_count < max(2, int(np.ceil(len(df) * 0.40)))
        or pd.isna(_num(latest.get("Ingresos", np.nan)))
        or pd.isna(_num(latest.get("Beneficio neto", np.nan)))
    ):
        meta = {
            "CIK": cik,
            "Empresa SEC": facts.get("entityName", sec_name),
            "Estado": "Cobertura SEC insuficiente; se recomienda fallback",
            "Años recuperados": len(df),
            "Años con ingresos": annual_revenue_count,
            "Divisa reportada esperada": currency,
        }
        return pd.DataFrame(), audit, meta

    meta = {"CIK": cik,
        "Registro separación": any(f in {"10-12B", "10-12B/A"} for f in recent.get("form", [])), "Empresa SEC": facts.get("entityName", sec_name), "Estado": "OK",
            "Años recuperados": len(df), "Años con ingresos": annual_revenue_count,
            "Primera fecha fiscal": df["Fecha cierre fiscal"].min(),
            "Última fecha fiscal": df["Fecha cierre fiscal"].max(), "Divisa reportada esperada": currency}
    accounting=set(str(x['Concepto SEC']).split(':')[0] for x in source_rows
        if x.get('Campo') in ('Ingresos','Beneficio neto','EPS diluido') and pd.notna(x.get('Valor original')) and ':' in str(x['Concepto SEC']))
    meta['Base contable']='US_GAAP' if accounting=={'us-gaap'} else 'IFRS' if accounting=={'ifrs-full'} else 'UNKNOWN'
    meta['Fecha corte']=str(cutoff.date())
    for i,form in enumerate(recent.get('form',[])):
        if form not in ('10-Q','10-K') or not recent.get('primaryDocument',[])[i]:continue
        accn=recent['accessionNumber'][i]
        meta['Último filing financiero']={'form':form,'filing_date':recent['filingDate'][i],
            'report_date':recent['reportDate'][i],'accession':accn,
            'url':f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accn.replace('-','')}/{recent['primaryDocument'][i]}"}
        break
    return df, audit, meta
