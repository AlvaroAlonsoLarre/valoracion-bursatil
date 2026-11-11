# -*- coding: utf-8 -*-
"""
ANÁLISIS BURSÁTIL COMPLETO: HISTÓRICO SEC EDGAR + MERCADO YAHOO FINANCE

Cambiar únicamente TICKER y, si se desea, NUM_TRIMESTRES.

Incluye:
- Información general, divisa y próxima fecha de resultados disponible.
- Últimos resultados trimestrales disponibles.
- Histórico de estados financieros anuales SEC EDGAR (hasta 10 ejercicios; fallback Yahoo si SEC no está disponible).
- Ratios históricos y valoración al cierre fiscal.
- Valoración actual de mercado.
- CAGR de ventas, EPS y flujo de caja libre (FCF).
- Escenarios pesimista, medio y optimista a 1 y 3 años:
    * EPS proyectado × PER histórico.
    * Valoración complementaria por FCF yield.
- Empresas comparables de Yahoo (máximo 10), métricas de comparación y media/mediana.
- Revisión de datos ausentes y exportación de todas las tablas a un Excel.

Notas metodológicas:
- Los importes de estados financieros se presentan en miles de millones de la
  divisa financiera informada por Yahoo Finance; EPS y precios por acción.
- La deuda utiliza partidas de deuda sin arrendamientos siempre que Yahoo las
  proporcione. Si no están disponibles, se usa una alternativa con arrendamientos
  y se identifica explícitamente.
- La capitalización histórica es aproximada: precio de cierre fiscal × acciones
  diluidas medias del ejercicio. No equivale a la capitalización histórica exacta.
- El FCF propio se calcula como flujo de caja operativo − CAPEX absoluto.
- El EBITDA aproximado propio se calcula como beneficio operativo + D&A.
- Los datos históricos anuales priorizan SEC EDGAR; la cobertura depende de que el ticker corresponda a un emisor SEC. Los estados trimestrales y datos de mercado siguen en Yahoo Finance.
- El modelo de escenarios es ilustrativo, no una predicción ni recomendación.
"""

# ============================================================
# 1. CONFIGURACIÓN: CAMBIAR SOLO ESTOS PARÁMETROS
# ============================================================
import os
TICKER = os.environ.get("VALUACION_TICKER", "MSFT").strip().upper() or "MSFT"
NUM_TRIMESTRES = int(os.environ.get("VALUACION_NUM_TRIMESTRES", "12"))
HORIZONTES = (1, 3)
MAX_COMPARABLES = 10
MAX_CANDIDATOS_INFO = max(15, min(100, int(os.environ.get("VALUACION_MAX_CANDIDATOS", "55"))))
ANIOS_HISTORICO_SEC = 10
# Sustituye el correo de ejemplo por una dirección de contacto real para SEC EDGAR.
SEC_USER_AGENT = os.environ.get(
    "VALUACION_SEC_USER_AGENT",
    "StockValuationProject/1.0 (contact: replace-with-your-email@example.com)"
)
SEC_CIK_OVERRIDE = os.environ.get("VALUACION_SEC_CIK", "").strip() or None

# ============================================================
# 2. IMPORTACIONES Y AJUSTES DE PRESENTACIÓN
# ============================================================
import re
import warnings
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
import yfinance as yf
from sec_historical import download_sec_annual_history
from modelo_fundamental import build_fundamental_model, fx_rate
from comparables_inteligentes import selected_candidates, discover_candidates, score_and_filter, economic_seeds

# Import explícito para que la función de presentación no dependa de una
# variable global llamada `display` que pudiera haberse sobrescrito en Jupyter.
try:
    from IPython.display import display as ipy_display
except ImportError:
    ipy_display = None

pd.set_option("display.max_columns", None)
pd.set_option("display.width", 320)
pd.set_option("display.float_format", lambda x: f"{x:,.2f}")

# En Jupyter se muestra una tabla enriquecida; en otros entornos se imprime.
def mostrar(objeto, filas=100):
    if ipy_display is not None:
        ipy_display(objeto)
    elif isinstance(objeto, pd.DataFrame):
        print(objeto.head(filas).to_string())
    else:
        print(objeto)


def numero(valor):
    """Convierte un valor a float finito o devuelve NaN."""
    try:
        resultado = float(valor)
        return resultado if np.isfinite(resultado) else np.nan
    except (TypeError, ValueError):
        return np.nan


def normalizar_nombre(nombre):
    """Normaliza etiquetas para tolerar diferencias de formato."""
    return re.sub(r"[^a-z0-9]", "", str(nombre).lower())


def normalizar_fecha(fecha):
    """Convierte una fecha en Timestamp sin zona horaria y a medianoche."""
    if fecha is None or pd.isna(fecha):
        return pd.NaT
    try:
        fecha = pd.Timestamp(fecha)
        if fecha.tzinfo is not None:
            fecha = fecha.tz_localize(None)
        return fecha.normalize()
    except (TypeError, ValueError):
        return pd.NaT


def preparar_estado(estado):
    """Elimina columnas duplicadas y prepara mapas de filas y fechas."""
    if estado is None or not isinstance(estado, pd.DataFrame) or estado.empty:
        vacio = pd.DataFrame()
        return vacio, {}, {}

    estado = estado.loc[:, ~estado.columns.duplicated()].copy()
    mapa_filas = {normalizar_nombre(idx): idx for idx in estado.index}
    mapa_fechas = {}
    for columna in estado.columns:
        fecha = normalizar_fecha(columna)
        if pd.notna(fecha):
            mapa_fechas[fecha] = columna
    return estado, mapa_filas, mapa_fechas


def obtener_valor(estado_preparado, fecha, posibles_nombres):
    """Obtiene una partida usando una lista de etiquetas alternativas."""
    estado, mapa_filas, mapa_fechas = estado_preparado
    if estado.empty:
        return np.nan

    fecha = normalizar_fecha(fecha)
    if pd.isna(fecha) or fecha not in mapa_fechas:
        return np.nan

    columna_real = mapa_fechas[fecha]
    for nombre in posibles_nombres:
        fila = mapa_filas.get(normalizar_nombre(nombre))
        if fila is None:
            continue
        try:
            valor = estado.loc[fila, columna_real]
            if isinstance(valor, pd.Series):
                valor = valor.iloc[0]
            valor = numero(valor)
            if pd.notna(valor):
                return valor
        except (KeyError, IndexError, TypeError):
            continue
    return np.nan


def dividir_seguro(numerador, denominador):
    numerador, denominador = numero(numerador), numero(denominador)
    if pd.isna(numerador) or pd.isna(denominador) or denominador == 0:
        return np.nan
    return numerador / denominador


def primer_valor_disponible(*valores):
    for valor in valores:
        valor = numero(valor)
        if pd.notna(valor):
            return valor
    return np.nan


def llamar_o_vacio(funcion, *args, **kwargs):
    """Ejecuta una consulta de Yahoo y devuelve DataFrame vacío si falla."""
    try:
        resultado = funcion(*args, **kwargs)
        return resultado if isinstance(resultado, pd.DataFrame) else pd.DataFrame()
    except Exception as error:
        warnings.warn(f"No se pudo descargar {funcion.__name__}: {error}")
        return pd.DataFrame()


def a_miles_millones(tabla, columnas):
    resultado = tabla.copy()
    for columna in columnas:
        if columna in resultado.columns:
            resultado[columna] = pd.to_numeric(resultado[columna], errors="coerce") / 1e9
    return resultado


def porcentaje(valor):
    valor = numero(valor)
    return valor * 100 if pd.notna(valor) else np.nan


def obtener_cagr(valor_inicial, valor_final, anios):
    """CAGR para valores positivos; si no procede, devuelve NaN."""
    valor_inicial = numero(valor_inicial)
    valor_final = numero(valor_final)
    if (
        pd.isna(valor_inicial) or pd.isna(valor_final)
        or valor_inicial <= 0 or valor_final <= 0 or anios <= 0
    ):
        return np.nan
    return (valor_final / valor_inicial) ** (1 / anios) - 1


def estadisticas_crecimiento(serie):
    """Crecimientos interanuales, media y desviación estándar muestral."""
    serie = pd.to_numeric(serie, errors="coerce").dropna().sort_index()
    crecimientos = []
    etiquetas = []
    for i in range(1, len(serie)):
        anio_anterior = int(serie.index[i - 1])
        anio_actual = int(serie.index[i])
        inicial = numero(serie.iloc[i - 1])
        final = numero(serie.iloc[i])
        if anio_actual != anio_anterior + 1:
            continue
        if pd.notna(inicial) and pd.notna(final) and inicial > 0 and final > 0:
            crecimientos.append(final / inicial - 1)
            etiquetas.append(f"{anio_anterior}-{anio_actual}")
    serie_crecimientos = pd.Series(crecimientos, index=etiquetas, dtype=float)
    return {
        "crecimientos": serie_crecimientos,
        "media": serie_crecimientos.mean(),
        "desviacion": serie_crecimientos.std(ddof=1),
        "observaciones": len(serie_crecimientos),
    }


def precio_cierre_en_o_antes(precios, fecha):
    fecha = normalizar_fecha(fecha)
    if precios.empty or pd.isna(fecha) or "Close" not in precios.columns:
        return np.nan
    anteriores = precios.loc[precios.index.normalize() <= fecha, "Close"].dropna()
    return numero(anteriores.iloc[-1]) if not anteriores.empty else np.nan


# ============================================================
# 3. DESCARGA DE INFORMACIÓN GENERAL Y ESTADOS FINANCIEROS
# ============================================================
print("=" * 100)
print(f"DESCARGANDO INFORMACIÓN DE {TICKER}")
print("=" * 100)

empresa = yf.Ticker(TICKER)
try:
    info = empresa.get_info() or {}
except Exception as error:
    warnings.warn(f"No se pudo obtener info de Yahoo: {error}")
    info = {}

try:
    fast_info = empresa.fast_info
except Exception:
    fast_info = {}


def fast_get(clave, defecto=np.nan):
    try:
        valor = fast_info.get(clave, defecto)
        return defecto if valor is None else valor
    except Exception:
        return defecto


nombre_empresa = info.get("longName") or info.get("shortName") or TICKER
divisa_financiera = (
    info.get("financialCurrency") or info.get("currency")
    or fast_get("currency", "No disponible") or "No disponible"
)
divisa_cotizacion = (
    info.get("currency") or fast_get("currency", divisa_financiera)
    or divisa_financiera
)

# Descarga anual y trimestral. Los estados de flujo de caja son flujos del periodo.
cuenta_anual_raw = llamar_o_vacio(empresa.get_income_stmt, freq="yearly")
balance_anual_raw = llamar_o_vacio(empresa.get_balance_sheet, freq="yearly")
flujo_anual_raw = llamar_o_vacio(empresa.get_cash_flow, freq="yearly")

cuenta_trim_raw = llamar_o_vacio(empresa.get_income_stmt, freq="quarterly")
balance_trim_raw = llamar_o_vacio(empresa.get_balance_sheet, freq="quarterly")
flujo_trim_raw = llamar_o_vacio(empresa.get_cash_flow, freq="quarterly")

cuenta_anual = preparar_estado(cuenta_anual_raw)
balance_anual = preparar_estado(balance_anual_raw)
flujo_anual = preparar_estado(flujo_anual_raw)
cuenta_trim = preparar_estado(cuenta_trim_raw)
balance_trim = preparar_estado(balance_trim_raw)
flujo_trim = preparar_estado(flujo_trim_raw)

fechas_anuales_yahoo = sorted({normalizar_fecha(c) for c in cuenta_anual_raw.columns if pd.notna(normalizar_fecha(c))})
fechas_anuales = list(fechas_anuales_yahoo)
fechas_trim_todas = sorted({normalizar_fecha(c) for c in cuenta_trim_raw.columns if pd.notna(normalizar_fecha(c))}, reverse=True)
fechas_trim = fechas_trim_todas[:max(1, int(NUM_TRIMESTRES))]
fecha_ultimo_ejercicio = max(fechas_anuales) if fechas_anuales else pd.NaT

# Precios históricos para valorar el cierre fiscal de cada ejercicio.
try:
    precios = empresa.history(period="max", interval="1d", auto_adjust=False)
except Exception as error:
    warnings.warn(f"No se pudo descargar el histórico de precios: {error}")
    precios = pd.DataFrame()
if not precios.empty:
    precios.index = pd.to_datetime(precios.index)
    if precios.index.tz is not None:
        precios.index = precios.index.tz_localize(None)
    precios = precios.sort_index().dropna(subset=["Close"] if "Close" in precios.columns else None)

# ------------------------------------------------------------
# Histórico anual principal: SEC EDGAR hasta 10 ejercicios.
# Yahoo se conserva para precio actual, cotización histórica y estados trimestrales.
# Si el ticker no está cubierto por SEC o la descarga falla, se activa fallback
# explícito a estados anuales de Yahoo (con menor profundidad histórica).
# ------------------------------------------------------------
tabla_financiera_sec_usd = pd.DataFrame()
tabla_fuentes_sec = pd.DataFrame()
sec_metadata = {"CIK": None, "Estado": "No consultado"}
try:
    if "replace-with-your-email@example.com" in SEC_USER_AGENT:
        warnings.warn(
            "Configura SEC_USER_AGENT con una dirección de contacto real. "
            "La SEC puede limitar solicitudes automatizadas sin identificación adecuada."
        )
    tabla_financiera_sec_usd, tabla_fuentes_sec, sec_metadata = download_sec_annual_history(
        ticker=TICKER,
        company_name=nombre_empresa,
        financial_currency=divisa_financiera,
        years=ANIOS_HISTORICO_SEC,
        user_agent=SEC_USER_AGENT,
        override_cik=SEC_CIK_OVERRIDE,
    )
except Exception as error:
    warnings.warn(f"No se pudo descargar el histórico anual de SEC EDGAR para {TICKER}: {error}")
    tabla_financiera_sec_usd = pd.DataFrame()
    tabla_fuentes_sec = pd.DataFrame()
    sec_metadata = {"CIK": None, "Estado": f"Error SEC: {error}"}

if not tabla_financiera_sec_usd.empty:
    fechas_anuales = [normalizar_fecha(x) for x in tabla_financiera_sec_usd["Fecha cierre fiscal"].tolist()]
    fechas_anuales = sorted([x for x in fechas_anuales if pd.notna(x)])
    fecha_ultimo_ejercicio = max(fechas_anuales)
    fuente_historico_anual = f"SEC EDGAR (CompanyFacts + Inline XBRL), hasta {len(fechas_anuales)} ejercicios"
    print(f"Fuente histórica anual seleccionada: {fuente_historico_anual}")
    print(f"CIK SEC: {sec_metadata.get('CIK')}; entidad SEC: {sec_metadata.get('Empresa SEC')}")
else:
    if cuenta_anual_raw.empty or not fechas_anuales_yahoo:
        raise ValueError(
            f"No se obtuvo histórico anual de SEC EDGAR ni cuenta de resultados anual de Yahoo para {TICKER}. "
            "Comprueba el ticker, la conexión, el User-Agent de la SEC o configura VALUACION_SEC_CIK."
        )
    fechas_anuales = list(fechas_anuales_yahoo)
    fecha_ultimo_ejercicio = max(fechas_anuales)
    fuente_historico_anual = "Yahoo Finance (fallback: SEC no disponible para este ticker)"
    warnings.warn(
        f"Se utilizará Yahoo Finance para el histórico anual de {TICKER}; "
        "no se ha podido obtener una serie SEC válida de 10 años."
    )

print(f"Empresa: {nombre_empresa}")
print(f"Ticker: {TICKER}")
print(f"Divisa financiera declarada: {divisa_financiera}")
print(f"Divisa de cotización declarada: {divisa_cotizacion}")
print(f"Último cierre fiscal anual disponible: {fecha_ultimo_ejercicio.date() if pd.notna(fecha_ultimo_ejercicio) else 'No disponible'}")
print(f"Ejercicios anuales utilizados: {[f.year for f in fechas_anuales]}")
print(f"Fuente del histórico anual: {fuente_historico_anual}")
print(f"Trimestres mostrados: {len(fechas_trim)} de {len(fechas_trim_todas)} disponibles")
print("Importes de estados financieros: miles de millones de la divisa financiera.")
print("EPS y precio por acción: divisa correspondiente por acción.")
if divisa_financiera != divisa_cotizacion:
    print("AVISO: la divisa financiera y la de cotización son distintas; las valoraciones EPS/PER pueden requerir conversión de divisa.")

# ============================================================
# 4. CAMPOS FINANCIEROS Y CONSTRUCCIÓN DE CADA PERIODO
# ============================================================
NOMBRES = {
    "ingresos": ["TotalRevenue", "OperatingRevenue"],
    "beneficio_bruto": ["GrossProfit"],
    "beneficio_operativo": ["OperatingIncome", "TotalOperatingIncomeAsReported", "OperatingIncomeLoss"],
    "beneficio_neto": ["NetIncome", "NetIncomeCommonStockholders", "NetIncomeIncludingNoncontrollingInterests"],
    "eps_diluido": ["DilutedEPS", "DilutedEps", "DilutedEPSCommonStockholders"],
    "eps_basico": ["BasicEPS", "BasicEps", "BasicEPSCommonStockholders"],
    "acciones_diluidas": ["DilutedAverageShares", "WeightedAverageDilutedShares"],
    "intereses": ["InterestExpenseNonOperating", "InterestExpense", "InterestAndDebtExpense"],
    "impuestos": ["TaxProvision", "IncomeTaxExpense"],
    "antes_impuestos": ["PretaxIncome", "IncomeBeforeTax"],
    "efectivo": ["CashAndCashEquivalents"],
    "leases": ["CapitalLeaseObligations", "FinanceLeaseLiability"],
    "efectivo_inversiones": ["CashCashEquivalentsAndShortTermInvestments", "CashCashEquivalentsAndMarketableSecurities"],
    "inversiones_cp": ["OtherShortTermInvestments", "ShortTermInvestments", "MarketableSecuritiesCurrent", "AvailableForSaleSecuritiesCurrent"],
    "deuda_cp": ["CurrentDebt", "CurrentPortionOfLongTermDebt", "ShortTermDebt"],
    "deuda_lp": ["LongTermDebt", "LongTermDebtNoncurrent"],
    "deuda_cp_con_arr": ["CurrentDebtAndCapitalLeaseObligation", "CurrentDebtAndFinanceLeaseObligation"],
    "deuda_lp_con_arr": ["LongTermDebtAndCapitalLeaseObligation", "LongTermDebtAndFinanceLeaseObligation"],
    "activos": ["TotalAssets"],
    "patrimonio": ["StockholdersEquity", "CommonStockEquity", "TotalEquityGrossMinorityInterest"],
    "flujo_operativo": ["OperatingCashFlow", "CashFlowFromContinuingOperatingActivities"],
    "capex": ["CapitalExpenditure", "CapitalExpenditures", "PurchaseOfPPE", "PurchaseOfPropertyPlantAndEquipment"],
    "da": ["DepreciationAndAmortization", "DepreciationAmortizationDepletion"],
    "dividendos": ["CommonStockDividendPaid", "CashDividendsPaid", "CommonStockDividendsPaid"],
    "recompras": ["RepurchaseOfCapitalStock", "CommonStockPayments"],
}


def construir_fila_financiera(fecha, estado_resultados, estado_balance, estado_flujo):
    """Construye una fila comparable para un cierre fiscal anual o trimestral."""
    get_i = lambda key: obtener_valor(estado_resultados, fecha, NOMBRES[key])
    get_b = lambda key: obtener_valor(estado_balance, fecha, NOMBRES[key])
    get_f = lambda key: obtener_valor(estado_flujo, fecha, NOMBRES[key])

    ingresos = get_i("ingresos")
    bruto = get_i("beneficio_bruto")
    operativo = get_i("beneficio_operativo")
    neto = get_i("beneficio_neto")
    eps_diluido = get_i("eps_diluido")
    eps_basico = get_i("eps_basico")
    acciones_diluidas = get_i("acciones_diluidas")
    intereses = get_i("intereses")
    impuestos = get_i("impuestos")
    antes_impuestos = get_i("antes_impuestos")

    efectivo = get_b("efectivo")
    efectivo_inversiones_directo = get_b("efectivo_inversiones")
    inversiones_cp = get_b("inversiones_cp")

    # Preferir la partida conjunta; si no existe, sumar caja e inversiones una vez.
    if pd.notna(efectivo_inversiones_directo):
        efectivo_total = efectivo_inversiones_directo
        efectivo_mas_inversiones_origen = "Partida conjunta Yahoo"
    elif pd.notna(efectivo):
        efectivo_total = efectivo + (inversiones_cp if pd.notna(inversiones_cp) else 0.0)
        efectivo_mas_inversiones_origen = "Caja + inversiones disponibles" if pd.notna(inversiones_cp) else "Solo caja (inversiones no disponibles)"
    else:
        efectivo_total = np.nan
        efectivo_mas_inversiones_origen = "No disponible"

    deuda_cp = get_b("deuda_cp")
    deuda_lp = get_b("deuda_lp")
    deuda_incluye_arrendamientos = False
    origen_deuda = "Deuda sin arrendamientos cuando está disponible"

    # Solo recurrir a partidas que incluyen arrendamientos si Yahoo no da deuda básica.
    if pd.isna(deuda_cp) and pd.isna(deuda_lp):
        deuda_cp_arr = get_b("deuda_cp_con_arr")
        deuda_lp_arr = get_b("deuda_lp_con_arr")
        if pd.notna(deuda_cp_arr) or pd.notna(deuda_lp_arr):
            deuda_cp, deuda_lp = deuda_cp_arr, deuda_lp_arr
            deuda_incluye_arrendamientos = True
            origen_deuda = "Alternativa Yahoo que incluye arrendamientos"

    activos = get_b("activos")
    patrimonio = get_b("patrimonio")

    importes_deuda = [v for v in [deuda_cp, deuda_lp] if pd.notna(v)]
    deuda_total = sum(importes_deuda) if importes_deuda else np.nan
    deuda_neta = deuda_total - efectivo_total if pd.notna(deuda_total) and pd.notna(efectivo_total) else np.nan

    flujo_operativo = get_f("flujo_operativo")
    capex_original = get_f("capex")
    da = get_f("da")
    dividendos_original = get_f("dividendos")
    recompras_original = get_f("recompras")

    capex = abs(capex_original) if pd.notna(capex_original) else np.nan
    dividendos = abs(dividendos_original) if pd.notna(dividendos_original) else np.nan
    recompras = abs(recompras_original) if pd.notna(recompras_original) else np.nan
    fcf = flujo_operativo - capex if pd.notna(flujo_operativo) and pd.notna(capex) else np.nan
    ebitda = operativo + da if pd.notna(operativo) and pd.notna(da) else np.nan

    margen_bruto = dividir_seguro(bruto, ingresos)
    margen_operativo = dividir_seguro(operativo, ingresos)
    margen_neto = dividir_seguro(neto, ingresos)
    margen_fcf = dividir_seguro(fcf, ingresos)
    deuda_neta_ebitda = dividir_seguro(deuda_neta, ebitda)
    cobertura_intereses = dividir_seguro(operativo, intereses)
    tasa_fiscal = dividir_seguro(impuestos, antes_impuestos)
    nopat = operativo * (1 - tasa_fiscal) if pd.notna(operativo) and pd.notna(tasa_fiscal) else np.nan
    capital_invertido = deuda_total + patrimonio - efectivo_total if pd.notna(deuda_total) and pd.notna(patrimonio) and pd.notna(efectivo_total) else np.nan
    roic = dividir_seguro(nopat, capital_invertido)

    return {
        "Fecha cierre fiscal": normalizar_fecha(fecha),
        "Ingresos": ingresos,
        "Beneficio bruto": bruto,
        "Beneficio operativo": operativo,
        "Beneficio neto": neto,
        "EPS básico": eps_basico,
        "EPS diluido": eps_diluido,
        "Acciones diluidas medias": acciones_diluidas,
        "Efectivo": efectivo,
        "Inversiones a corto plazo": inversiones_cp,
        "Efectivo e inversiones": efectivo_total,
        "Origen efectivo/inversiones": efectivo_mas_inversiones_origen,
        "Deuda a corto plazo": deuda_cp,
        "Deuda a largo plazo": deuda_lp,
        "Deuda total": deuda_total,
        "Deuda neta": deuda_neta,
        "Deuda incluye arrendamientos": deuda_incluye_arrendamientos,
        "Origen deuda": origen_deuda,
        "Activos totales": activos,
        "Patrimonio neto": patrimonio,
        "Flujo de caja operativo": flujo_operativo,
        "CAPEX": capex,
        "D&A": da,
        "Definición D&A": "D&A consolidada Yahoo; desglose no verificado",
        "Arrendamientos": get_b("leases"),
        "Flujo de caja libre": fcf,
        "EBITDA aproximado": ebitda,
        "Impuestos": impuestos,
        "Beneficio antes de impuestos": antes_impuestos,
        "Tasa fiscal": tasa_fiscal,
        "Gastos por intereses": intereses,
        "Margen bruto": margen_bruto,
        "Margen operativo": margen_operativo,
        "Margen neto": margen_neto,
        "Margen FCF": margen_fcf,
        "Deuda neta / EBITDA": deuda_neta_ebitda,
        "Cobertura de intereses": cobertura_intereses,
        "NOPAT aproximado": nopat,
        "Capital invertido aproximado": capital_invertido,
        "ROIC": roic,
        "Recompras de acciones": recompras,
        "Dividendos": dividendos,
    }


# ============================================================
# 4B. AUDITORÍA ANUAL YAHOO vs SEC (EJERCICIOS COINCIDENTES)
# ============================================================
tabla_comparacion_fuentes = pd.DataFrame()
tabla_resumen_comparacion = pd.DataFrame()
if not tabla_financiera_sec_usd.empty and fechas_anuales_yahoo:
    campos_comparables = [
        "Ingresos", "Beneficio bruto", "Beneficio operativo", "Beneficio neto",
        "EPS básico", "EPS diluido", "Acciones diluidas medias", "Efectivo",
        "Inversiones a corto plazo", "Efectivo e inversiones", "Deuda a corto plazo",
        "Deuda a largo plazo", "Deuda total", "Deuda neta", "Activos totales",
        "Patrimonio neto", "Flujo de caja operativo", "CAPEX", "D&A",
        "Flujo de caja libre", "EBITDA aproximado", "Impuestos",
        "Beneficio antes de impuestos", "Margen neto", "Margen FCF",
        "Tasa fiscal", "NOPAT aproximado", "Capital invertido aproximado", "ROIC",
        "Deuda neta / EBITDA", "Gastos por intereses", "Dividendos", "Recompras de acciones",
    ]
    registros_comparacion = []
    for fecha_yahoo in fechas_anuales_yahoo:
        anio = int(fecha_yahoo.year)
        if anio not in tabla_financiera_sec_usd.index:
            continue
        datos_yahoo = construir_fila_financiera(fecha_yahoo, cuenta_anual, balance_anual, flujo_anual)
        datos_sec = tabla_financiera_sec_usd.loc[anio]
        for campo in campos_comparables:
            val_yahoo = numero(datos_yahoo.get(campo, np.nan))
            val_sec = numero(datos_sec.get(campo, np.nan))
            if pd.isna(val_yahoo) or pd.isna(val_sec):
                diferencia = np.nan
                resultado = "No comparable (faltan datos)"
            elif abs(val_yahoo) < 1e-12:
                diferencia = 0.0 if abs(val_sec) < 1e-12 else 100.0
                resultado = "Coincide (<1%)" if diferencia == 0 else "Revisar (Yahoo cero, SEC no cero)"
            else:
                diferencia = abs(val_yahoo - val_sec) / abs(val_yahoo) * 100
                resultado = "Coincide (<1%)" if diferencia < 1 else "Revisar (>=1%)"
            registros_comparacion.append({
                "Ejercicio": anio, "Campo": campo,
                "Yahoo (unidades originales)": val_yahoo,
                "SEC (unidades originales)": val_sec,
                "Diferencia relativa (%)": diferencia, "Resultado": resultado,
            })
    tabla_comparacion_fuentes = pd.DataFrame(registros_comparacion)
    if not tabla_comparacion_fuentes.empty:
        for anio, datos in tabla_comparacion_fuentes.groupby("Ejercicio"):
            validos = datos["Diferencia relativa (%)"].notna()
            fallos = (datos["Diferencia relativa (%)"] >= 1).sum()
            tabla_fila = {
                "Ejercicio": anio, "Campos evaluados": len(datos),
                "Comparaciones numéricas": int(validos.sum()),
                "Coinciden (<1%)": int((datos["Diferencia relativa (%)"] < 1).sum()),
                "Diferencias >=1%": int(fallos),
                "No comparables": int((~validos).sum()),
                "Mayor diferencia (%)": datos["Diferencia relativa (%)"].max(),
                "Estado": "REVISAR" if fallos else ("OK en campos comparados" if validos.any() else "SIN DATOS COMPARABLES"),
            }
            tabla_resumen_comparacion = pd.concat(
                [tabla_resumen_comparacion, pd.DataFrame([tabla_fila])], ignore_index=True)
        if (tabla_resumen_comparacion["Diferencias >=1%"] > 0).any():
            warnings.warn("Se han detectado discrepancias Yahoo vs SEC >=1%. Ver hoja 'Comparacion Yahoo SEC'.")
        print("\nAUDITORÍA DE COINCIDENCIA ANUAL YAHOO vs SEC")
        mostrar(tabla_resumen_comparacion)

# ============================================================
# 5. ESTADOS FINANCIEROS ANUALES
# ============================================================
if not tabla_financiera_sec_usd.empty:
    # Fuente principal: hasta 10 ejercicios SEC. Los datos están en unidades originales.
    tabla_financiera_usd = tabla_financiera_sec_usd.copy().sort_index()
    tabla_financiera_usd.index = tabla_financiera_usd.index.astype(int)
    tabla_financiera_usd.index.name = "Ejercicio"
else:
    # Fallback transparente: conservar el histórico anual de Yahoo si SEC no está disponible.
    filas_anuales = []
    for fecha in fechas_anuales:
        fila = construir_fila_financiera(fecha, cuenta_anual, balance_anual, flujo_anual)
        fila["Ejercicio"] = int(fecha.year)
        fila["Origen financiero anual"] = "Yahoo Finance (fallback)"
        filas_anuales.append(fila)
    tabla_financiera_usd = pd.DataFrame(filas_anuales).set_index("Ejercicio").sort_index()

columnas_monetarias_financieras = [
    "Ingresos", "Beneficio bruto", "Beneficio operativo", "Beneficio neto",
    "Efectivo", "Inversiones a corto plazo", "Efectivo e inversiones",
    "Efectivo e inversiones combinado directo", "Deuda a corto plazo", "Deuda a largo plazo",
    "Deuda total", "Deuda neta", "Pasivos por arrendamientos",
    "Deuda total incl. arrendamientos", "Deuda neta incl. arrendamientos",
    "Activos totales", "Patrimonio neto", "Flujo de caja operativo", "CAPEX", "D&A",
    "Flujo de caja libre", "EBITDA aproximado", "Impuestos", "Beneficio antes de impuestos",
    "Gastos por intereses", "NOPAT aproximado", "Capital invertido aproximado",
    "Recompras de acciones", "Dividendos",
]
columnas_porcentajes_financieras = [
    "Tasa fiscal", "Margen bruto", "Margen operativo", "Margen neto", "Margen FCF", "ROIC"
]

tabla_financiera = a_miles_millones(tabla_financiera_usd, columnas_monetarias_financieras)
if "Acciones diluidas medias" in tabla_financiera.columns:
    tabla_financiera["Acciones diluidas medias"] /= 1e9
for columna in columnas_porcentajes_financieras:
    if columna in tabla_financiera.columns:
        tabla_financiera[columna] *= 100

print("\n" + "=" * 100)
print("ESTADOS FINANCIEROS ANUALES — SEC EDGAR como fuente principal")
print("Importes monetarios en miles de millones; acciones en miles de millones; ratios en % cuando proceda")
print("=" * 100)
mostrar(tabla_financiera)

# ============================================================
# 6. HISTÓRICO DE PRECIOS Y VALORACIÓN AL CIERRE FISCAL
# ============================================================
filas_valoracion = []
for anio, datos in tabla_financiera_usd.iterrows():
    fecha_fiscal = normalizar_fecha(datos["Fecha cierre fiscal"])
    precio = precio_cierre_en_o_antes(precios, fecha_fiscal)
    eps = numero(datos["EPS diluido"])
    acciones = numero(datos["Acciones diluidas medias"])
    deuda_neta = numero(datos["Deuda neta"])
    ebitda = numero(datos["EBITDA aproximado"])
    fcf = numero(datos["Flujo de caja libre"])

    # Aproximación: las acciones diluidas medias no son las acciones exactas al cierre.
    capitalizacion = precio * acciones if pd.notna(precio) and pd.notna(acciones) else np.nan
    valor_empresa = capitalizacion + deuda_neta if pd.notna(capitalizacion) and pd.notna(deuda_neta) else np.nan
    per = dividir_seguro(precio, eps)
    ev_ebitda = dividir_seguro(valor_empresa, ebitda)
    ev_fcf = dividir_seguro(valor_empresa, fcf)
    fcf_yield = dividir_seguro(fcf, capitalizacion)
    roic = dividir_seguro(datos["NOPAT aproximado"], datos["Capital invertido aproximado"])

    filas_valoracion.append({
        "Ejercicio": int(anio),
        "Fecha cierre fiscal": fecha_fiscal,
        "Precio cierre fiscal": precio,
        "EPS diluido": eps,
        "Acciones diluidas medias": acciones,
        "Capitalización bursátil aproximada": capitalizacion,
        "Deuda neta": deuda_neta,
        "EV aproximado": valor_empresa,
        "EBITDA aproximado": ebitda,
        "Flujo de caja libre": fcf,
        "PER": per,
        "EV/EBITDA": ev_ebitda,
        "EV/FCF": ev_fcf,
        "Rentabilidad FCF (%)": porcentaje(fcf_yield),
        "Deuda neta/EBITDA": dividir_seguro(deuda_neta, ebitda),
        "NOPAT aproximado": datos["NOPAT aproximado"],
        "Capital invertido aproximado": datos["Capital invertido aproximado"],
        "ROIC (%)": porcentaje(roic),
    })

tabla_historica_usd = pd.DataFrame(filas_valoracion).set_index("Ejercicio").sort_index()
# Bloquear históricos que mezclan las divisas (FX histórico no recuperado por ejercicio).
if divisa_financiera != divisa_cotizacion:
    for col in ("Capitalización bursátil aproximada", "EV aproximado", "PER", "EV/EBITDA", "EV/FCF", "Rentabilidad FCF (%)"):
        tabla_historica_usd[col]=np.nan
    warnings.warn("Histórico de múltiplos bloqueado: precio y estados financieros en divisas diferentes. No se inventa FX histórico.")
tabla_historica = a_miles_millones(
    tabla_historica_usd,
    [
        "Capitalización bursátil aproximada", "Deuda neta", "EV aproximado",
        "EBITDA aproximado", "Flujo de caja libre", "NOPAT aproximado",
        "Capital invertido aproximado",
    ],
)
if "Acciones diluidas medias" in tabla_historica.columns:
    tabla_historica["Acciones diluidas medias"] /= 1e9

print("\n" + "=" * 100)
print("VALORACIÓN HISTÓRICA AL CIERRE FISCAL")
print("Capitalización histórica aproximada = precio de cierre × acciones diluidas medias")
print("=" * 100)
mostrar(tabla_historica)

# ============================================================
# 7. ESTADÍSTICAS HISTÓRICAS DE RATIOS
# ============================================================
# Las ventanas corresponden a los últimos 5 y 10 EJERCICIOS (no últimos
# cinco/diez valores no nulos). Mostrar cobertura para no confundir medias
# parciales con series históricas completas.
metricas_historicas = [
    ("Ingresos", "fin"), ("Beneficio bruto", "fin"),
    ("Beneficio operativo", "fin"), ("Beneficio neto", "fin"),
    ("EPS diluido", "fin"), ("Acciones diluidas medias", "fin"),
    ("EBITDA aproximado", "fin"), ("Flujo de caja libre", "fin"),
    ("CAPEX", "fin"), ("Deuda neta", "fin"), ("Deuda total", "fin"),
    ("Margen neto", "fin"), ("Margen FCF", "fin"), ("ROIC", "fin"),
    ("PER", "hist"), ("EV/EBITDA", "hist"), ("EV/FCF", "hist"),
    ("Rentabilidad FCF (%)", "hist"), ("Deuda neta/EBITDA", "hist"),
    ("ROIC (%)", "hist"),
]

def serie_estadistica(indicador, origen, ventana):
    fuente = tabla_financiera if origen == "fin" else tabla_historica
    if indicador not in fuente.columns:
        return pd.Series(dtype=float), len(fuente.tail(ventana))
    subconjunto = fuente.tail(ventana)
    serie = pd.to_numeric(subconjunto[indicador], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if indicador in {"PER", "EV/EBITDA", "EV/FCF"}:
        serie = serie[serie > 0]
    return serie, len(subconjunto)

filas_stats = []
for indicador, origen in metricas_historicas:
    s5, a5 = serie_estadistica(indicador, origen, 5)
    s10, a10 = serie_estadistica(indicador, origen, 10)
    filas_stats.append({
        "Indicador": indicador,
        "Media 5 años": s5.mean(), "Mediana 5 años": s5.median(),
        "Media 10 años": s10.mean(), "Mediana 10 años": s10.median(),
        "Desviación 10 años": s10.std(ddof=1),
        "Datos 5 años": len(s5), "Datos 10 años": len(s10),
        "Ejercicios disponibles 5 años": a5, "Ejercicios disponibles 10 años": a10,
    })
estadisticas = pd.DataFrame(filas_stats).set_index("Indicador")

print("\n" + "=" * 100)
print("RESUMEN HISTÓRICO SEC: MEDIAS Y MEDIANAS DE 5 Y 10 EJERCICIOS")
print("Las columnas 'Datos' distinguen periodos realmente observados de periodos solicitados.")
print("=" * 100)
mostrar(estadisticas)

# ============================================================
# 8. VALORACIÓN ACTUAL DE MERCADO
# ============================================================
try:
    precio_actual = numero(fast_get("last_price"))
except Exception:
    precio_actual = np.nan
if pd.isna(precio_actual):
    precio_actual = primer_valor_disponible(info.get("currentPrice"), info.get("regularMarketPrice"))
if pd.isna(precio_actual) and not precios.empty:
    precio_actual = numero(precios["Close"].dropna().iloc[-1])

capitalizacion_actual = primer_valor_disponible(
    info.get("marketCap"), fast_get("market_cap")
)
acciones_en_circulacion = primer_valor_disponible(
    info.get("sharesOutstanding"), fast_get("shares")
)
if pd.isna(capitalizacion_actual) and pd.notna(acciones_en_circulacion) and pd.notna(precio_actual):
    capitalizacion_actual = acciones_en_circulacion * precio_actual

ultimo_anio = int(tabla_financiera_usd.index.max())
ultimo_anual = tabla_financiera_usd.loc[ultimo_anio]
eps_ultimo = numero(ultimo_anual["EPS diluido"])
deuda_neta_ultimo = numero(ultimo_anual["Deuda neta"])
ebitda_ultimo = numero(ultimo_anual["EBITDA aproximado"])
fcf_ultimo = numero(ultimo_anual["Flujo de caja libre"])

valor_empresa_actual = (
    capitalizacion_actual + deuda_neta_ultimo
    if pd.notna(capitalizacion_actual) and pd.notna(deuda_neta_ultimo)
    else np.nan
)
per_anual_actual = dividir_seguro(precio_actual, eps_ultimo)
ev_ebitda_actual = dividir_seguro(valor_empresa_actual, ebitda_ultimo)
ev_fcf_actual = dividir_seguro(valor_empresa_actual, fcf_ultimo)
fcf_yield_actual = dividir_seguro(fcf_ultimo, capitalizacion_actual)

valores_actuales = {
    "Empresa": nombre_empresa,
    "Ticker": TICKER,
    "Divisa financiera": divisa_financiera,
    "Divisa de cotización": divisa_cotizacion,
    "Último ejercicio fiscal disponible": ultimo_anio,
    "Precio actual (divisa cotización/acción)": precio_actual,
    "Capitalización actual (miles de millones)": capitalizacion_actual / 1e9 if pd.notna(capitalizacion_actual) else np.nan,
    "EPS del último ejercicio (divisa financiera/acción)": eps_ultimo,
    "PER con EPS del último ejercicio": per_anual_actual,
    "PER TTM publicado por Yahoo": numero(info.get("trailingPE")),
    "PER forward publicado por Yahoo": numero(info.get("forwardPE")),
    "Valor de empresa aproximado (miles de millones)": valor_empresa_actual / 1e9 if pd.notna(valor_empresa_actual) else np.nan,
    "EV/EBITDA aproximado": ev_ebitda_actual,
    "EV/FCF aproximado": ev_fcf_actual,
    "Rentabilidad FCF (%)": porcentaje(fcf_yield_actual),
    "FCF último ejercicio (miles de millones)": fcf_ultimo / 1e9 if pd.notna(fcf_ultimo) else np.nan,
    "EBITDA aproximado último ejercicio (miles de millones)": ebitda_ultimo / 1e9 if pd.notna(ebitda_ultimo) else np.nan,
}
tabla_actual = pd.DataFrame({"Valor": valores_actuales})
print("\n" + "=" * 100)
print("VALORACIÓN ACTUAL DE MERCADO")
print("La deuda neta usa el último balance anual disponible, no necesariamente un balance de hoy.")
print("=" * 100)
mostrar(tabla_actual)

# ============================================================
# 9. RESULTADOS TRIMESTRALES Y FECHAS DE PUBLICACIÓN
# ============================================================
try:
    earnings_dates = empresa.get_earnings_dates(limit=max(40, NUM_TRIMESTRES * 3))
    if earnings_dates is None:
        earnings_dates = pd.DataFrame()
except Exception as error:
    warnings.warn(f"No se pudieron obtener las fechas de resultados: {error}")
    earnings_dates = pd.DataFrame()

publicaciones = []
if not earnings_dates.empty:
    for fecha in earnings_dates.index:
        fecha_limpia = normalizar_fecha(fecha)
        if pd.notna(fecha_limpia):
            publicaciones.append(fecha_limpia)
publicaciones = sorted(set(publicaciones))

# Relacionar cada publicación con el cierre trimestral inmediatamente anterior,
# siempre que la publicación tenga lugar entre 1 y 90 días después del cierre.
mapa_publicaciones = {}
for publicacion in publicaciones:
    cierres_candidatos = [
        cierre for cierre in fechas_trim_todas
        if pd.Timedelta(days=1) <= publicacion - cierre <= pd.Timedelta(days=90)
    ]
    if cierres_candidatos:
        cierre_asociado = max(cierres_candidatos)
        # Si dos fechas aparentan corresponder al mismo trimestre, conservar la más próxima.
        anterior = mapa_publicaciones.get(cierre_asociado)
        if anterior is None or publicacion < anterior:
            mapa_publicaciones[cierre_asociado] = publicacion

hoy = pd.Timestamp.now().normalize()
fechas_futuras = [fecha for fecha in publicaciones if fecha >= hoy]
proxima_publicacion = min(fechas_futuras) if fechas_futuras else pd.NaT

# Si no hay fecha futura en get_earnings_dates, comprobar el calendario de Yahoo.
if pd.isna(proxima_publicacion):
    try:
        calendario = empresa.calendar
        posibles = []
        if isinstance(calendario, pd.DataFrame):
            if "Earnings Date" in calendario.index:
                valor = calendario.loc["Earnings Date"]
                posibles = list(valor if isinstance(valor, (pd.Series, list, tuple, np.ndarray)) else [valor])
        elif isinstance(calendario, dict):
            valor = calendario.get("Earnings Date", [])
            posibles = list(valor if isinstance(valor, (list, tuple, np.ndarray, pd.Series)) else [valor])
        candidatas = [normalizar_fecha(x) for x in posibles]
        candidatas = [x for x in candidatas if pd.notna(x) and x >= hoy]
        if candidatas:
            proxima_publicacion = min(candidatas)
    except Exception:
        pass

filas_trimestrales = []
for fecha in fechas_trim:
    fila = construir_fila_financiera(fecha, cuenta_trim, balance_trim, flujo_trim)
    fila["Cierre del trimestre"] = normalizar_fecha(fecha)
    fila["Publicación de resultados estimada/registrada"] = mapa_publicaciones.get(normalizar_fecha(fecha), pd.NaT)
    filas_trimestrales.append(fila)

tabla_trimestral_usd = pd.DataFrame(filas_trimestrales)
if not tabla_trimestral_usd.empty:
    tabla_trimestral_usd = tabla_trimestral_usd.sort_values("Cierre del trimestre", ascending=False).set_index("Cierre del trimestre")
    columnas_trimestrales_monetarias = [
        "Ingresos", "Beneficio bruto", "Beneficio operativo", "Beneficio neto",
        "Efectivo", "Inversiones a corto plazo", "Efectivo e inversiones",
        "Deuda a corto plazo", "Deuda a largo plazo", "Deuda total", "Deuda neta",
        "Activos totales", "Patrimonio neto", "Flujo de caja operativo", "CAPEX", "D&A",
        "Flujo de caja libre", "EBITDA aproximado", "Impuestos", "Beneficio antes de impuestos",
        "Gastos por intereses", "NOPAT aproximado", "Capital invertido aproximado",
        "Recompras de acciones", "Dividendos",
    ]
    tabla_trimestral = a_miles_millones(tabla_trimestral_usd, columnas_trimestrales_monetarias)
    for columna in ["Tasa fiscal", "Margen bruto", "Margen operativo", "Margen neto", "Margen FCF", "ROIC"]:
        if columna in tabla_trimestral.columns:
            tabla_trimestral[columna] *= 100
    tabla_trimestral.index = pd.to_datetime(tabla_trimestral.index).strftime("%d/%m/%Y")
    tabla_trimestral.index.name = "Cierre del trimestre"
    tabla_trimestral["Publicación de resultados estimada/registrada"] = pd.to_datetime(
        tabla_trimestral["Publicación de resultados estimada/registrada"], errors="coerce"
    ).dt.strftime("%d/%m/%Y")
else:
    tabla_trimestral = pd.DataFrame()

# Ratios de mercado a cierre trimestral: requieren datos acumulados TTM.
# Evitar multiplicar por 4 un único trimestre y evitar múltiplos negativos.
if not tabla_trimestral.empty:
    tdates = pd.to_datetime(tabla_trimestral.index, dayfirst=True, errors="coerce")
    # Mantener el mismo orden de las filas (del más reciente al más antiguo).
    q_eps = pd.to_numeric(tabla_trimestral.get("EPS diluido"), errors="coerce")
    q_ebitda = pd.to_numeric(tabla_trimestral.get("EBITDA aproximado"), errors="coerce")
    q_fcf = pd.to_numeric(tabla_trimestral.get("Flujo de caja libre"), errors="coerce")
    q_shares = pd.to_numeric(tabla_trimestral.get("Acciones diluidas medias"), errors="coerce")
    q_net_debt = pd.to_numeric(tabla_trimestral.get("Deuda neta"), errors="coerce")
    q_equity = pd.to_numeric(tabla_trimestral.get("Patrimonio neto"), errors="coerce")
    q_income = pd.to_numeric(tabla_trimestral.get("Beneficio neto"), errors="coerce")
    q_debt = pd.to_numeric(tabla_trimestral.get("Deuda total"), errors="coerce")
    q_prices = pd.Series([precio_cierre_en_o_antes(precios, d) if pd.notna(d) else np.nan for d in tdates], index=tabla_trimestral.index, dtype=float)
    # TTM solo cuando los cuatro trimestres están presentes y espaciados razonablemente.
    def ttm_sum(series, i):
        if i + 4 > len(series): return np.nan
        vals = series.iloc[i:i+4]
        dates = tdates[i:i+4]
        if vals.isna().any() or pd.isna(dates).any() or (dates[0]-dates[-1]).days not in range(240,341): return np.nan
        return float(vals.sum())
    ttm_eps = [ttm_sum(q_eps,i) for i in range(len(tabla_trimestral))]
    ttm_ebitda = [ttm_sum(q_ebitda,i) for i in range(len(tabla_trimestral))]
    ttm_fcf = [ttm_sum(q_fcf,i) for i in range(len(tabla_trimestral))]
    tabla_trimestral["Precio cierre trimestre"] = q_prices
    tabla_trimestral["PER TTM"] = [float(q_prices.iloc[i])/ttm_eps[i] if pd.notna(q_prices.iloc[i]) and pd.notna(ttm_eps[i]) and ttm_eps[i]>0 else np.nan for i in range(len(tabla_trimestral))]
    q_mc = q_prices * q_shares / 1e9
    q_ev = q_mc + q_net_debt
    tabla_trimestral["EV/EBITDA TTM"] = [float(q_ev.iloc[i])/ttm_ebitda[i] if pd.notna(q_ev.iloc[i]) and pd.notna(ttm_ebitda[i]) and ttm_ebitda[i]>0 else np.nan for i in range(len(tabla_trimestral))]
    tabla_trimestral["Deuda neta / EBITDA TTM"] = [float(q_net_debt.iloc[i])/ttm_ebitda[i] if pd.notna(q_net_debt.iloc[i]) and pd.notna(ttm_ebitda[i]) and ttm_ebitda[i]>0 else np.nan for i in range(len(tabla_trimestral))]
    tabla_trimestral["Rentabilidad FCF TTM (%)"] = [100*ttm_fcf[i]/float(q_mc.iloc[i]) if pd.notna(q_mc.iloc[i]) and q_mc.iloc[i]>0 and pd.notna(ttm_fcf[i]) else np.nan for i in range(len(tabla_trimestral))]
    # Multiples independientes por trimestre: denominador del trimestre anualizado x4.
    # NO se acumulan cuatro trimestres (no TTM).
    def ratio_trimestral_anualizado(numerador, denominador):
        a = pd.to_numeric(numerador, errors="coerce")
        b = pd.to_numeric(denominador, errors="coerce")
        return (a / (4.0 * b.where(b > 0))).replace([np.inf, -np.inf], np.nan)

    tabla_trimestral["PER trimestral anualizado"] = ratio_trimestral_anualizado(q_prices, q_eps)
    tabla_trimestral["EV/EBITDA trimestral anualizado"] = ratio_trimestral_anualizado(q_ev, q_ebitda)
    tabla_trimestral["Deuda neta / EBITDA trimestral anualizado"] = ratio_trimestral_anualizado(q_net_debt, q_ebitda)
    tabla_trimestral["ROE trimestral anualizado (%)"] = 400 * q_income / q_equity.replace(0,np.nan)
    tabla_trimestral["Deuda/Patrimonio (%)"] = 100 * q_debt / q_equity.replace(0,np.nan)
    # Los múltiplos de cotización no mezclan EPS/EBITDA financieros en otra divisa.
    # Para FX cruzado se muestran N/D; la valoración fundamental convierte FX.
    if str(divisa_financiera).upper()!=str(divisa_cotizacion).upper():
        for metric in ["PER TTM", "PER trimestral anualizado", "EV/EBITDA TTM",
                       "EV/EBITDA trimestral anualizado", "Deuda neta / EBITDA TTM",
                       "Deuda neta / EBITDA trimestral anualizado", "Rentabilidad FCF TTM (%)"]:
            tabla_trimestral[metric]=np.nan


print("\n" + "=" * 100)
print("ÚLTIMOS RESULTADOS TRIMESTRALES")
print("Las fechas de publicación pueden ser estimaciones de Yahoo y no siempre pueden asociarse a un trimestre.")
print("=" * 100)
if not tabla_trimestral.empty:
    mostrar(tabla_trimestral)
else:
    print("Yahoo Finance no devolvió suficientes datos trimestrales para mostrar una tabla.")

if pd.notna(proxima_publicacion):
    print(f"\nPróxima fecha de presentación de resultados que Yahoo muestra: {proxima_publicacion.strftime('%d/%m/%Y')}")
else:
    print("\nYahoo Finance no proporciona una próxima fecha de presentación futura disponible.")

tabla_publicacion = pd.DataFrame({
    "Concepto": ["Última consulta", "Próxima publicación indicada por Yahoo"],
    "Fecha": [hoy, proxima_publicacion],
})

# ============================================================
# 10. CAGR DE VENTAS, EPS Y FCF
# ============================================================
def obtener_cagr_columna(tabla, columna):
    serie = pd.to_numeric(tabla[columna], errors="coerce").dropna().sort_index()
    if len(serie) < 2:
        return np.nan, np.nan, np.nan, np.nan, np.nan, np.nan
    inicial = numero(serie.iloc[0])
    final = numero(serie.iloc[-1])
    anio_inicial = int(serie.index[0])
    anio_final = int(serie.index[-1])
    intervalo = anio_final - anio_inicial
    return obtener_cagr(inicial, final, intervalo), inicial, final, anio_inicial, anio_final, intervalo

cagr_ventas, ventas_iniciales, ventas_finales, anio_ventas_ini, anio_ventas_fin, n_ventas = obtener_cagr_columna(tabla_financiera_usd, "Ingresos")
cagr_eps, eps_inicial, eps_final, anio_eps_ini, anio_eps_fin, n_eps = obtener_cagr_columna(tabla_financiera_usd, "EPS diluido")
cagr_fcf, fcf_inicial, fcf_final, anio_fcf_ini, anio_fcf_fin, n_fcf = obtener_cagr_columna(tabla_financiera_usd, "Flujo de caja libre")

tabla_cagr = pd.DataFrame([
    {"Indicador": "Ventas", "Ejercicio inicial": anio_ventas_ini, "Valor inicial": ventas_iniciales / 1e9 if pd.notna(ventas_iniciales) else np.nan,
     "Ejercicio final": anio_ventas_fin, "Valor final": ventas_finales / 1e9 if pd.notna(ventas_finales) else np.nan,
     "Intervalos anuales": n_ventas, "CAGR (%)": porcentaje(cagr_ventas), "Unidad": f"Miles de millones de {divisa_financiera}"},
    {"Indicador": "EPS diluido", "Ejercicio inicial": anio_eps_ini, "Valor inicial": eps_inicial,
     "Ejercicio final": anio_eps_fin, "Valor final": eps_final,
     "Intervalos anuales": n_eps, "CAGR (%)": porcentaje(cagr_eps), "Unidad": f"{divisa_financiera} por acción"},
    {"Indicador": "Flujo de caja libre", "Ejercicio inicial": anio_fcf_ini, "Valor inicial": fcf_inicial / 1e9 if pd.notna(fcf_inicial) else np.nan,
     "Ejercicio final": anio_fcf_fin, "Valor final": fcf_final / 1e9 if pd.notna(fcf_final) else np.nan,
     "Intervalos anuales": n_fcf, "CAGR (%)": porcentaje(cagr_fcf), "Unidad": f"Miles de millones de {divisa_financiera}"},
])
print("\n" + "=" * 100)
print("CAGR HISTÓRICO DE VENTAS, EPS Y FCF")
print("El número de intervalos es el número de años entre los ejercicios inicial y final.")
print("=" * 100)
mostrar(tabla_cagr)

# Crecimiento anual: estadísticos de los últimos 5 y 10 ejercicios SEC.
# Estas medias NO son idénticas al CAGR, que se calcula desde los extremos.
filas_cagr_ventanas = []
for indicador, columna in [("Ventas", "Ingresos"), ("EPS diluido", "EPS diluido"),
                           ("Flujo de caja libre", "Flujo de caja libre")]:
    for ventana in (5, 10):
        recorte = tabla_financiera_usd[columna].tail(ventana)
        cagr_ventana, inicial, final, ani, anf, intervalos = obtener_cagr_columna(
            tabla_financiera_usd.tail(ventana), columna)
        tasa = estadisticas_crecimiento(recorte)
        filas_cagr_ventanas.append({
            "Indicador": indicador, "Ventana solicitada (años)": ventana,
            "Ejercicios en ventana": len(recorte), "Intervalos CAGR": intervalos,
            "CAGR (%)": porcentaje(cagr_ventana),
            "Media crecimiento interanual (%)": porcentaje(tasa["media"]),
            "Mediana crecimiento interanual (%)": porcentaje(tasa["crecimientos"].median()),
            "Intervalos interanuales válidos": tasa["observaciones"],
        })
tabla_cagr_ventanas = pd.DataFrame(filas_cagr_ventanas)

stats_eps = estadisticas_crecimiento(tabla_financiera_usd["EPS diluido"].tail(10))
stats_fcf = estadisticas_crecimiento(tabla_financiera_usd["Flujo de caja libre"].tail(10))
filas_crecimientos = []
for indicador, stats in [("EPS diluido", stats_eps), ("FCF", stats_fcf)]:
    for periodo, crecimiento in stats["crecimientos"].items():
        filas_crecimientos.append({"Indicador": indicador, "Periodo": periodo, "Crecimiento anual (%)": porcentaje(crecimiento)})
tabla_crecimientos = pd.DataFrame(filas_crecimientos)

print("\n--- ESTADÍSTICAS DE LOS CRECIMIENTOS ANUALES ---")
for nombre, stats in [("EPS", stats_eps), ("FCF", stats_fcf)]:
    media = stats["media"]
    desviacion = stats["desviacion"]
    print(f"{nombre}: media = {media * 100:.2f}%" if pd.notna(media) else f"{nombre}: media no disponible")
    print(f"{nombre}: desviación estándar muestral = {desviacion * 100:.2f} puntos porcentuales" if pd.notna(desviacion) else f"{nombre}: desviación estándar no disponible")
    print(f"Número de crecimientos interanuales válidos: {stats['observaciones']}")

# ============================================================
# 11. PER HISTÓRICO Y ESCENARIOS DE PRECIO EPS × PER
# ============================================================
per_historico = pd.to_numeric(tabla_historica_usd["PER"].tail(10), errors="coerce")
per_historico = per_historico[np.isfinite(per_historico) & (per_historico > 0)]
per_medio = per_historico.mean()
per_desviacion = per_historico.std(ddof=1)
tabla_per = pd.DataFrame({"PER histórico": per_historico})
tabla_per.index.name = "Ejercicio"

print("\n--- PER HISTÓRICO USADO EN LOS ESCENARIOS ---")
mostrar(tabla_per)
print(f"PER medio: {per_medio:.2f}" if pd.notna(per_medio) else "PER medio no disponible")
print(f"Desviación estándar muestral del PER: {per_desviacion:.2f}" if pd.notna(per_desviacion) else "Desviación estándar del PER no disponible")
print(f"Ejercicios válidos utilizados: {len(per_historico)}")

# Escenario medio usa la media de crecimientos anuales del EPS y el PER medio.
# Pesimista/optimista ajustan ambos parámetros en -/+ una desviación estándar.
crecimiento_medio_eps = stats_eps["media"]
desviacion_crecimiento_eps = stats_eps["desviacion"]

escenarios_eps = {}
ventana_diez_anios_completa = len(tabla_financiera_usd.tail(10)) == 10
if not ventana_diez_anios_completa:
    warnings.warn(f"Solo hay {len(tabla_financiera_usd)} ejercicios anuales; no se publicarán escenarios etiquetados a 10 años.")
if ventana_diez_anios_completa and len(per_historico) >= 8 and stats_eps["observaciones"] >= 7 and all(pd.notna(x) for x in [eps_ultimo, precio_actual, per_medio, per_desviacion, crecimiento_medio_eps, desviacion_crecimiento_eps]) and eps_ultimo > 0 and precio_actual > 0:
    escenarios_eps = {
        "Pesimista": {"crecimiento": crecimiento_medio_eps - desviacion_crecimiento_eps, "PER": per_medio - per_desviacion},
        "Medio": {"crecimiento": crecimiento_medio_eps, "PER": per_medio},
        "Optimista": {"crecimiento": crecimiento_medio_eps + desviacion_crecimiento_eps, "PER": per_medio + per_desviacion},
    }
    for nombre in list(escenarios_eps):
        if escenarios_eps[nombre]["PER"] <= 0 or 1 + escenarios_eps[nombre]["crecimiento"] <= 0:
            warnings.warn(f"Se omite escenario {nombre}: PER o crecimiento EPS no positivos/viables.")
            del escenarios_eps[nombre]
else:
    warnings.warn("No hay datos suficientes para completar escenarios EPS/PER.")

tabla_parametros = pd.DataFrame([
    {"Escenario": nombre, "Crecimiento EPS (%)": porcentaje(datos["crecimiento"]), "PER utilizado": datos["PER"]}
    for nombre, datos in escenarios_eps.items()
])
if not tabla_parametros.empty:
    tabla_parametros = tabla_parametros.set_index("Escenario")
else:
    tabla_parametros = pd.DataFrame(columns=["Crecimiento EPS (%)", "PER utilizado"])
    tabla_parametros.index.name = "Escenario"

filas_escenarios_eps = []
for nombre, datos in escenarios_eps.items():
    crecimiento = datos["crecimiento"]
    per_escenario = datos["PER"]
    for horizonte in HORIZONTES:
        eps_futuro = eps_ultimo * (1 + crecimiento) ** horizonte
        precio_objetivo = eps_futuro * per_escenario
        potencial = precio_objetivo / precio_actual - 1
        rentabilidad_anualizada = (precio_objetivo / precio_actual) ** (1 / horizonte) - 1 if precio_objetivo > 0 else np.nan
        filas_escenarios_eps.append({
            "Escenario": nombre,
            "Horizonte (años)": horizonte,
            "EPS base último ejercicio": eps_ultimo,
            "Crecimiento anual EPS (%)": porcentaje(crecimiento),
            "EPS estimado": eps_futuro,
            "PER medio histórico (ventana 10 años)": per_medio,
            "PER: ejercicios válidos": len(per_historico),
            "Crecimiento EPS: intervalos válidos": stats_eps["observaciones"],
            "Desviación estándar PER": per_desviacion,
            "PER aplicado": per_escenario,
            "Precio objetivo": precio_objetivo,
            "Precio actual": precio_actual,
            "Potencial acumulado (%)": porcentaje(potencial),
            "Rentabilidad anualizada (%)": porcentaje(rentabilidad_anualizada),
        })
tabla_escenarios_eps = pd.DataFrame(filas_escenarios_eps)

print("\n" + "=" * 100)
print("ESCENARIOS DE PRECIO MEDIANTE EPS × PER")
print("Los escenarios extremos aplican simultáneamente una desviación al crecimiento EPS y al PER.")
print("=" * 100)
if not tabla_parametros.empty:
    mostrar(tabla_parametros)
if not tabla_escenarios_eps.empty:
    mostrar(tabla_escenarios_eps.round(2))

# ============================================================
# 12. ESCENARIOS DE VALORACIÓN POR FCF Y FCF YIELD
# ============================================================
# Capitalización objetivo = FCF proyectado / rentabilidad FCF exigida.
# Precio objetivo = capitalización objetivo / número estimado de acciones.
# Para mantener una base coherente, el número de acciones se aproxima como
# capitalización bursátil actual / precio actual.
acciones_actuales_estimadas = (
    capitalizacion_actual / precio_actual
    if pd.notna(capitalizacion_actual) and pd.notna(precio_actual) and precio_actual > 0
    else np.nan
)

yield_fcf_historico = pd.to_numeric(tabla_historica_usd["Rentabilidad FCF (%)"].tail(10), errors="coerce") / 100
yield_fcf_historico = yield_fcf_historico[np.isfinite(yield_fcf_historico) & (yield_fcf_historico > 0)]
yield_fcf_media = yield_fcf_historico.mean()
yield_fcf_desviacion = yield_fcf_historico.std(ddof=1)

filas_escenarios_fcf = []
if ventana_diez_anios_completa and len(yield_fcf_historico) >= 8 and stats_fcf["observaciones"] >= 7 and all(pd.notna(x) for x in [fcf_ultimo, cagr_fcf, stats_fcf["media"], stats_fcf["desviacion"], yield_fcf_media, acciones_actuales_estimadas, precio_actual]) and fcf_ultimo > 0 and acciones_actuales_estimadas > 0 and yield_fcf_media > 0:
    escenarios_fcf = {
        "Pesimista": {
            "crecimiento": stats_fcf["media"] - stats_fcf["desviacion"],
            "yield": yield_fcf_media + (yield_fcf_desviacion if pd.notna(yield_fcf_desviacion) else 0),
        },
        "Medio": {"crecimiento": stats_fcf["media"], "yield": yield_fcf_media},
        "Optimista": {
            "crecimiento": stats_fcf["media"] + stats_fcf["desviacion"],
            "yield": max(yield_fcf_media - (yield_fcf_desviacion if pd.notna(yield_fcf_desviacion) else 0), 0.0001),
        },
    }
    for nombre, datos in escenarios_fcf.items():
        crecimiento = datos["crecimiento"]
        yield_objetivo = datos["yield"]
        for horizonte in HORIZONTES:
            fcf_futuro = fcf_ultimo * (1 + crecimiento) ** horizonte if 1 + crecimiento > 0 else np.nan
            capitalizacion_objetivo = fcf_futuro / yield_objetivo if pd.notna(fcf_futuro) and yield_objetivo > 0 else np.nan
            precio_objetivo = capitalizacion_objetivo / acciones_actuales_estimadas if pd.notna(capitalizacion_objetivo) else np.nan
            potencial = precio_objetivo / precio_actual - 1 if pd.notna(precio_objetivo) else np.nan
            rentabilidad_anualizada = (precio_objetivo / precio_actual) ** (1 / horizonte) - 1 if pd.notna(precio_objetivo) and precio_objetivo > 0 else np.nan
            filas_escenarios_fcf.append({
                "Escenario": nombre,
                "Horizonte (años)": horizonte,
                "FCF base (miles de millones)": fcf_ultimo / 1e9,
                "Crecimiento anual FCF (%)": porcentaje(crecimiento),
                "FCF estimado (miles de millones)": fcf_futuro / 1e9 if pd.notna(fcf_futuro) else np.nan,
                "Rentabilidad FCF histórica media (%)": porcentaje(yield_fcf_media),
                "FCF yield: ejercicios válidos": len(yield_fcf_historico),
                "Crecimiento FCF: intervalos válidos": stats_fcf["observaciones"],
                "Desviación estándar yield FCF (p.p.)": porcentaje(yield_fcf_desviacion),
                "Rentabilidad FCF objetivo (%)": porcentaje(yield_objetivo),
                "Capitalización objetivo (miles de millones)": capitalizacion_objetivo / 1e9 if pd.notna(capitalizacion_objetivo) else np.nan,
                "Precio objetivo": precio_objetivo,
                "Precio actual": precio_actual,
                "Potencial acumulado (%)": porcentaje(potencial),
                "Rentabilidad anualizada (%)": porcentaje(rentabilidad_anualizada),
            })
else:
    warnings.warn("No hay datos suficientes para completar escenarios FCF.")

tabla_escenarios_fcf = pd.DataFrame(filas_escenarios_fcf)
print("\n" + "=" * 100)
print("ESCENARIOS DE VALORACIÓN MEDIANTE FCF Y FCF YIELD")
print("Modelo simplificado: no descuenta flujos futuros como un DCF completo.")
print("=" * 100)
print(f"CAGR del FCF: {porcentaje(cagr_fcf):.2f}%" if pd.notna(cagr_fcf) else "CAGR del FCF no disponible")
print(f"Media histórica de FCF yield: {porcentaje(yield_fcf_media):.2f}%" if pd.notna(yield_fcf_media) else "Media histórica de FCF yield no disponible")
if not tabla_escenarios_fcf.empty:
    mostrar(tabla_escenarios_fcf.round(2))

# ============================================================
# 13. EMPRESAS COMPARABLES: MISMA INDUSTRIA Y, SI HACE FALTA, SECTOR
# ============================================================
# Fuente: Yahoo Finance a través de yfinance.
# Criterios:
# 1) Prioridad a empresas de la misma industria.
# 2) Si no hay suficientes comparables válidos, ampliar al mismo sector.
# 3) Dentro de cada grupo, priorizar tamaño parecido (capitalización e
#    ingresos cuando las divisas de referencia coinciden).
# 4) Máximo MAX_COMPARABLES empresas; la empresa analizada no entra en la
#    media/mediana de comparables.
# El índice de similitud es heurístico, no una clasificación oficial de Yahoo.
# ============================================================

sector_objetivo = info.get("sector") or "No disponible"
sector_key_objetivo = info.get("sectorKey")
industria_objetivo = info.get("industry") or "No disponible"
industria_key_objetivo = info.get("industryKey")
region_objetivo = (info.get("country") or "").strip().lower()

MAPA_REGION = {
    "united states": "us", "usa": "us", "canada": "ca",
    "united kingdom": "gb", "great britain": "gb", "ireland": "ie",
    "spain": "es", "germany": "de", "france": "fr", "italy": "it",
    "switzerland": "ch", "netherlands": "nl", "sweden": "se",
    "norway": "no", "denmark": "dk", "finland": "fi", "austria": "at",
    "belgium": "be", "portugal": "pt", "japan": "jp", "south korea": "kr",
    "korea": "kr", "taiwan": "tw", "hong kong": "hk", "china": "cn",
    "india": "in", "australia": "au", "new zealand": "nz",
    "brazil": "br", "mexico": "mx", "singapore": "sg", "israel": "il",
}
region_key_objetivo = MAPA_REGION.get(region_objetivo)

capitalizacion_objetivo = numero(capitalizacion_actual)
ingresos_objetivo_ttm = numero(info.get("totalRevenue"))
divisa_financiera_objetivo = str(
    info.get("financialCurrency") or info.get("currency") or divisa_financiera or ""
).upper()
divisa_cotizacion_objetivo = str(
    info.get("currency") or divisa_cotizacion or ""
).upper()
# Alias compatible con versiones anteriores de esta sección.
divisa_cot_objetivo = divisa_cotizacion_objetivo

# Diccionario de candidatos. Un valor de prioridad inferior es preferible.
candidatos = {}
comparables_economicos_config = selected_candidates(TICKER)

def normalizar_ticker_peer(valor):
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return None
    valor = str(valor).strip().upper()
    if not valor or valor in {"NAN", "NONE", "N/A"}:
        return None
    # Conserva símbolos de Yahoo habituales: puntos, guiones, caret y signo igual.
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9.\-^=]{0,19}", valor):
        return None
    return valor


def agregar_candidato(simbolo, origen, prioridad, market_cap_previo=np.nan):
    simbolo = normalizar_ticker_peer(simbolo)
    if simbolo is None or simbolo == TICKER.upper():
        return
    actual = candidatos.get(simbolo)
    nuevo = {
        "Ticker": simbolo,
        "Origen candidatos": origen,
        "Prioridad origen": prioridad,
        "Capitalización de screener": numero(market_cap_previo),
    }
    if actual is None or prioridad < actual["Prioridad origen"]:
        candidatos[simbolo] = nuevo
    elif actual is not None and pd.isna(actual["Capitalización de screener"]) and pd.notna(market_cap_previo):
        actual["Capitalización de screener"] = numero(market_cap_previo)


# Comparables seleccionados por ACTIVIDAD económica o introducidos manualmente.
# Se integran antes de la selección automática de Yahoo para tener preferencia.
for simbolo, meta in comparables_economicos_config.items():
    agregar_candidato(simbolo, meta["Origen curado"], -10)
# Semillas económicas se consultan siempre, sujetas a los mismos filtros.
for simbolo in economic_seeds(TICKER):
    agregar_candidato(simbolo,'Semilla económica: pendiente de evaluación',-5)
registro_candidatos={}

def procesar_resultado_screener(resultado, origen, prioridad):
    """Lee la respuesta de yf.screen() sin depender de columnas opcionales."""
    if not isinstance(resultado, dict):
        return
    quotes = resultado.get("quotes", [])
    if not isinstance(quotes, list):
        return
    for item in quotes:
        if not isinstance(item, dict):
            continue
        simbolo = item.get("symbol") or item.get("ticker")
        cap = primer_valor_disponible(
            item.get("marketCap"), item.get("intradaymarketcap"),
            item.get("lastclosemarketcap.lasttwelvemonths")
        )
        agregar_candidato(simbolo, origen, prioridad, cap)


def procesar_tabla_empresas(tabla_fuente, origen, prioridad):
    """Extrae tickers de tablas Industry/Sector de yfinance."""
    if not isinstance(tabla_fuente, pd.DataFrame) or tabla_fuente.empty:
        return
    columnas_normalizadas = {normalizar_nombre(c): c for c in tabla_fuente.columns}
    col_simbolo = next(
        (columnas_normalizadas[k] for k in ["symbol", "ticker", "tickersymbol", "quotesymbol"]
         if k in columnas_normalizadas),
        None,
    )
    col_cap = next(
        (col for clave, col in columnas_normalizadas.items()
         if clave in {"marketcap", "intradaymarketcap", "lastclosemarketcaplasttwelvemonths"}),
        None,
    )
    if col_simbolo is not None:
        for _, fila in tabla_fuente.iterrows():
            cap = numero(fila[col_cap]) if col_cap is not None else np.nan
            agregar_candidato(fila[col_simbolo], origen, prioridad, cap)
    else:
        # Algunas versiones pueden devolver el símbolo como índice.
        nombre_indice = normalizar_nombre(tabla_fuente.index.name or "")
        if nombre_indice in {"symbol", "ticker", "tickersymbol", "quotesymbol"}:
            for indice in tabla_fuente.index:
                agregar_candidato(indice, origen, prioridad)
        elif not isinstance(tabla_fuente.index, pd.RangeIndex):
            for indice in tabla_fuente.index:
                # Evita interpretar un índice numérico simple (0, 1, 2...) como ticker.
                if re.search(r"[A-Z]", str(indice).upper()):
                    agregar_candidato(indice, origen, prioridad)


def ejecutar_screener_industria(industry_name, region_key=None):
    """No usa EquityQuery para industria.

    En varias versiones de yfinance, Yahoo exige etiquetas de industria
    con puntuación exacta (por ejemplo, "Software—Infrastructure" con
    raya em), mientras Ticker.info devuelve "Software - Infrastructure".
    Para evitar filtros inválidos y depender de la versión instalada,
    los candidatos se obtienen mediante yf.Industry(...).top_companies,
    top_growth_companies y top_performing_companies.
    """
    return False


print("\n" + "=" * 100)
print("EMPRESAS COMPARABLES DE YAHOO FINANCE")
print("=" * 100)
print(f"Empresa analizada: {nombre_empresa} ({TICKER})")
print(f"Sector Yahoo: {sector_objetivo} | Industria Yahoo: {industria_objetivo}")

# A) Universo principal: empresas de la misma industria.
# Se usan los objetos Industry/Sector de yfinance en vez de EquityQuery,
# porque el nombre de industria devuelto por Ticker.info puede no coincidir
# exactamente con la enumeración estricta del screener.
if industria_key_objetivo and hasattr(yf, "Industry"):
    try:
        industria_yahoo = yf.Industry(
            industria_key_objetivo,
            region=(region_key_objetivo.upper() if region_key_objetivo else "US"),
        )
        procesar_tabla_empresas(
            industria_yahoo.top_companies, "Top companies: misma industria", 
            0 if region_key_objetivo else 1
        )
        # Estas listas complementan el universo si la tabla principal es pequeña.
        try:
            procesar_tabla_empresas(
                industria_yahoo.top_growth_companies,
                "Top growth: misma industria", 0 if region_key_objetivo else 1
            )
        except Exception:
            pass
        try:
            procesar_tabla_empresas(
                industria_yahoo.top_performing_companies,
                "Top performing: misma industria", 0 if region_key_objetivo else 1
            )
        except Exception:
            pass
    except Exception as error:
        warnings.warn(f"No se pudieron consultar empresas de la industria: {error}")


# Descubrimiento multi-región automático (sin catálogo por ticker).
# Complementa Industry local/US con Japón, Corea, Taiwán y buscador de actividad;
# elimina la limitación de solo un país y añade competidores transfronterizos.
try:
    descubiertos, errores_descubrimiento = discover_candidates(
        yf, TICKER, info, region=(region_key_objetivo or 'US').upper(),
        max_candidates=max(65, MAX_CANDIDATOS_INFO * 2),
    )
    for simbolo, meta in descubiertos.items():
        agregar_candidato(simbolo, meta['Origen candidatos'], meta['Prioridad origen'])
    print(f"Descubrimiento automático: {len(descubiertos)} candidatos, total {len(candidatos)}")
    if errores_descubrimiento:
        warnings.warn("Algunas fuentes de candidatos no respondieron: " +
                      "; ".join(errores_descubrimiento[:3]))
except Exception as exc:
    warnings.warn(f"Descubrimiento multi-región no disponible: {exc}")


def distancia_tamano(cap_peer, ingresos_peer, divisa_fin_peer, divisa_cot_peer):
    """Distancia relativa por tamaño; menor significa tamaño más parecido."""
    distancias = []
    pesos = []
    if (
        pd.notna(capitalizacion_objetivo) and capitalizacion_objetivo > 0
        and pd.notna(cap_peer) and cap_peer > 0
        and divisa_cotizacion_objetivo == str(divisa_cot_peer or "").upper()
    ):
        distancias.append(abs(np.log(cap_peer / capitalizacion_objetivo)))
        pesos.append(0.60)
    if (
        pd.notna(ingresos_objetivo_ttm) and ingresos_objetivo_ttm > 0
        and pd.notna(ingresos_peer) and ingresos_peer > 0
        and divisa_financiera_objetivo == str(divisa_fin_peer or "").upper()
    ):
        distancias.append(abs(np.log(ingresos_peer / ingresos_objetivo_ttm)))
        pesos.append(0.40)
    if not distancias:
        return np.nan
    pesos = np.asarray(pesos, dtype=float)
    pesos = pesos / pesos.sum()
    return float(np.sum(np.asarray(distancias) * pesos))


def extraer_metricas_peer(simbolo, datos_info, origen, prioridad_origen):
    """Normaliza métricas clave de la empresa comparable."""
    divisa_fin = datos_info.get("financialCurrency") or datos_info.get("currency") or "No disponible"
    divisa_cot = datos_info.get("currency") or "No disponible"
    cap = numero(datos_info.get("marketCap"))
    if pd.isna(cap):
        try:
            peer_fast = yf.Ticker(simbolo).fast_info
            cap = numero(peer_fast.get("market_cap"))
        except Exception:
            pass
    ingresos = numero(datos_info.get("totalRevenue"))
    fcf = numero(datos_info.get("freeCashflow"))
    # No calcula FCF yield cuando el FCF y la capitalización están en divisas distintas.
    fcf_yield_peer = (
        fcf / cap * 100
        if pd.notna(fcf) and pd.notna(cap) and cap > 0
        and str(divisa_fin).upper() == str(divisa_cot).upper()
        else np.nan
    )
    relacion = "Misma industria" if (
        industria_key_objetivo and datos_info.get("industryKey") == industria_key_objetivo
    ) else "Mismo sector"
    es_curado = simbolo.upper() in comparables_economicos_config
    if es_curado:
        grupo = comparables_economicos_config[simbolo.upper()].get('Grupo económico','Parcial')
        relacion = 'Manual / económico: ' + grupo
    if not es_curado and relacion == "Mismo sector" and sector_key_objetivo and datos_info.get("sectorKey") != sector_key_objetivo:
        # Yahoo puede omitir sectorKey; si lo indica y es distinto, no se considera peer.
        if datos_info.get("sectorKey"):
            return None
    if es_curado:
        prioridad_relacion = -10
    elif industria_key_objetivo and datos_info.get("industryKey") == industria_key_objetivo:
        prioridad_relacion = 0 if str(divisa_fin).upper() == divisa_financiera_objetivo else 1
    else:
        prioridad_relacion = 2

    distancia = distancia_tamano(
        cap, ingresos, divisa_fin, divisa_cot
    )
    similitud = 100 * np.exp(-distancia) if pd.notna(distancia) else np.nan

    return {
        "Ticker": simbolo,
        "Empresa": datos_info.get("longName") or datos_info.get("shortName") or simbolo,
        "Descripción actividad": str(datos_info.get("longBusinessSummary") or "")[:1800],
        "Industria clave": datos_info.get("industryKey") or "",
        "Sector clave": datos_info.get("sectorKey") or "",
        "Relación": relacion,
        "Sector": datos_info.get("sector") or "No disponible",
        "Industria": datos_info.get("industry") or "No disponible",
        "Divisa cotización": divisa_cot,
        "Divisa financiera": divisa_fin,
        "Precio actual": primer_valor_disponible(datos_info.get("currentPrice"), datos_info.get("regularMarketPrice")),
        "Capitalización (miles de millones)": cap / 1e9 if pd.notna(cap) else np.nan,
        "Ingresos TTM (miles de millones)": ingresos / 1e9 if pd.notna(ingresos) else np.nan,
        "PER trailing": numero(datos_info.get("trailingPE")),
        "PER forward": numero(datos_info.get("forwardPE")),
        "PER periodo": "No verificado FY1/NTM", "PER base": "No verificado GAAP/ajustado",
        "EV/EBITDA periodo": "LTM Yahoo; no NTM", "Perímetro deuda": "No verificado",
        "Emisor id": datos_info.get('underlyingSymbol') or datos_info.get('longName') or simbolo,
        "EV/EBITDA": numero(datos_info.get("enterpriseToEbitda")),
        "EV/Ingresos": numero(datos_info.get("enterpriseToRevenue")),
        "P/Ventas": numero(datos_info.get("priceToSalesTrailing12Months")),
        "P/Valor contable": numero(datos_info.get("priceToBook")),
        "Margen neto (%)": porcentaje(datos_info.get("profitMargins")),
        "Margen operativo (%)": porcentaje(datos_info.get("operatingMargins")),
        "Crecimiento ventas (%)": porcentaje(datos_info.get("revenueGrowth")),
        "Crecimiento beneficios (%)": porcentaje(datos_info.get("earningsGrowth")),
        "ROE (%)": porcentaje(datos_info.get("returnOnEquity")),
        "Deuda/Patrimonio (%)": numero(datos_info.get("debtToEquity")),
        "Rentabilidad FCF (%)": fcf_yield_peer,
        "Beta": numero(datos_info.get("beta")),
        "Similitud por tamaño (0-100)": similitud,
        "Origen": origen,
        "Prioridad relación": prioridad_relacion,
        "Prioridad origen": prioridad_origen,
        "Distancia de tamaño": distancia,
    }


def descargar_metricas_candidatos(lista_candidatos, max_candidatos=MAX_CANDIDATOS_INFO):
    """Consulta el perfil y las métricas de un máximo de N candidatos."""
    lista = list(lista_candidatos.values())
    if not lista:
        return []
    # Screener sin moneda acreditada: se conserva orden de prioridad, no tamaño nativo.
    # Reduce consultas: si Yahoo ofrece capitalización de screening, aproxima la cercanía
    # de tamaño antes de descargar info detallada.
    def distancia_previa(candidato):
        return 999.0 # Screener no acredita divisa; nunca comparar capitalizaciones nativas
    # Muestreo diversificado: evita que una única región o el primer listado de
    # Industry consuma toda la cuota de get_info() y oculte empresas afines.
    grupos = {'manual': [], 'industria_local': [], 'industria_global': [],
              'actividad': [], 'sector': []}
    for item in lista:
        origen = str(item.get('Origen candidatos','')).lower()
        if item['Ticker'] in comparables_economicos_config or item['Ticker'] in economic_seeds(TICKER):
            key='manual'
        elif 'búsqueda actividad' in origen or 'busqueda actividad' in origen:
            key='actividad'
        elif 'sector yahoo' in origen or 'mismo sector' in origen:
            key='sector'
        elif 'industria yahoo' in origen and region_key_objetivo and not origen.endswith(region_key_objetivo.upper().lower()):
            key='industria_global'
        elif 'industria yahoo' in origen and not origen.endswith(' us'):
            key='industria_global'
        else:
            key='industria_local'
        grupos[key].append(item)
    for items in grupos.values():
        items.sort(key=lambda c:(distancia_previa(c),c['Ticker']))
    cuotas={'manual':max(len(economic_seeds(TICKER)),len(comparables_economicos_config),3,int(max_candidatos*.10)),
            'industria_local':max(12,int(max_candidatos*.36)),
            'industria_global':max(10,int(max_candidatos*.25)),
            'actividad':max(7,int(max_candidatos*.20)),
            'sector':max(3,int(max_candidatos*.09))}
    chosen=[]; chosen_tickers=set()
    for key in ('manual','industria_local','industria_global','actividad','sector'):
        for item in grupos[key][:cuotas[key]]:
            if item['Ticker'] not in chosen_tickers and len(chosen)<max_candidatos:
                chosen.append(item);chosen_tickers.add(item['Ticker'])
    # Rellenar plazas que no se usaron porque Yahoo no encontró candidatos.
    remainder=sorted(lista,key=lambda c:(c['Prioridad origen'], distancia_previa(c),c['Ticker']))
    for item in remainder:
        if len(chosen)>=max_candidatos:break
        if item['Ticker'] not in chosen_tickers:
            chosen.append(item);chosen_tickers.add(item['Ticker'])
    filas = []
    for candidato in lista:
        registro_candidatos.setdefault(candidato['Ticker'],{**candidato,'Estado descarga':'NO_INTENTADO (límite consultas)','Detalle descarga':''})
    for candidato in chosen:
        simbolo = candidato["Ticker"]
        try:
            peer_ticker = yf.Ticker(simbolo)
            peer_info = peer_ticker.get_info() or {}
            if not peer_info:
                registro_candidatos[simbolo].update({'Estado descarga':'ERROR','Detalle descarga':'Perfil vacío'})
                continue
            fila = extraer_metricas_peer(
                simbolo, peer_info,
                candidato["Origen candidatos"], candidato["Prioridad origen"]
            )
            if fila is not None:
                filas.append(fila)
                registro_candidatos[simbolo].update({'Estado descarga':'DESCARGADO'})
            else:registro_candidatos[simbolo].update({'Estado descarga':'EXCLUIDO','Detalle descarga':'Fuera de sector/industria'})
        except Exception as error:
            registro_candidatos[simbolo].update({'Estado descarga':'ERROR','Detalle descarga':str(error)[:250]})
            warnings.warn(f"No se pudieron descargar las métricas de {simbolo}: {error}")
    return filas


filas_peer_industria = descargar_metricas_candidatos(candidatos)

def seleccionar_mejores_peers(filas, cantidad):
    if not filas:
        return []
    tabla = pd.DataFrame(filas)
    # La relación sectorial tiene prioridad; dentro de cada grupo, tamaño más parecido.
    tabla = tabla.sort_values(
        ["Prioridad relación", "Similitud por tamaño (0-100)", "Capitalización (miles de millones)"],
        ascending=[True, False, False], na_position="last"
    )
    return tabla.drop_duplicates("Ticker").head(cantidad).to_dict("records")


peers_seleccionados = seleccionar_mejores_peers(filas_peer_industria, MAX_COMPARABLES)

# B) Si no hay diez comparables de la misma industria, ampliar al mismo sector.
if len(peers_seleccionados) < MAX_COMPARABLES and sector_key_objetivo and hasattr(yf, "Sector"):
    candidatos_sector = {}
    try:
        sector_yahoo = yf.Sector(
            sector_key_objetivo,
            region=(region_key_objetivo.upper() if region_key_objetivo else "US"),
        )
        procesar_tabla_empresas(
            sector_yahoo.top_companies, "Top companies: mismo sector", 2
        )
    except Exception as error:
        warnings.warn(f"No se pudieron consultar empresas del sector: {error}")

    # Solo consultamos candidatos aún no valorados; conservamos los mejores de industria.
    tickers_ya_consultados = {fila["Ticker"] for fila in filas_peer_industria}
    candidatos_nuevos = {
        ticker: datos for ticker, datos in candidatos.items()
        if ticker not in tickers_ya_consultados
    }
    filas_peer_sector = descargar_metricas_candidatos(
        candidatos_nuevos, max_candidatos=MAX_CANDIDATOS_INFO
    )
    todas_filas_peer = filas_peer_industria + filas_peer_sector
    peers_seleccionados = seleccionar_mejores_peers(todas_filas_peer, MAX_COMPARABLES)
else:
    todas_filas_peer = filas_peer_industria

# En el caso de que industria+sector no hayan generado candidates, evita fallos de salida.
if "todas_filas_peer" not in locals():
    todas_filas_peer = filas_peer_industria

# V5: el modelo fundamental clasifica UNA sola vez TODO el universo.
# No eliminar candidatos antes de la clasificación final por actividad/finanzas.
# Esta tabla preliminar informa sobre candidatos; no alimenta las medianas.
universo_df = (pd.DataFrame(todas_filas_peer).drop_duplicates('Ticker')
               if todas_filas_peer else pd.DataFrame())
tabla_universo_peers = pd.DataFrame()
peers_seleccionados = []  # Se fijarán DESPUÉS de la selección única del modelo.

columnas_peer = [
    "Ticker", "Empresa", "Relación", "Sector", "Industria", "Industria clave", "Sector clave",
    "Descripción actividad", "Puntuación económica (0-100)", "Similitud de actividad (0-100)", "Elegible",
    "Divisa cotización", "Divisa financiera", "Precio actual",
    "Capitalización (miles de millones)", "Ingresos TTM (miles de millones)",
    "PER trailing", "PER forward", "EV/EBITDA", "EV/Ingresos", "P/Ventas",
    "P/Valor contable", "Margen neto (%)", "Margen operativo (%)",
    "Crecimiento ventas (%)", "Crecimiento beneficios (%)", "ROE (%)",
    "Deuda/Patrimonio (%)", "Rentabilidad FCF (%)", "Beta",
    "Similitud por tamaño (0-100)", "Origen",
]

# No más de 10 empresas comparables; la compañía analizada se presenta por separado.
tabla_comparables = pd.DataFrame(peers_seleccionados)
if not tabla_comparables.empty:
    tabla_comparables = tabla_comparables.reindex(columns=columnas_peer)
    tabla_comparables = tabla_comparables.sort_values(
        ["Elegible", "Puntuación económica (0-100)"],
        ascending=[False, False], na_position="last"
    ).reset_index(drop=True)
else:
    tabla_comparables = pd.DataFrame(columns=columnas_peer)

# Fila de referencia de la empresa analizada; no se incluye en la media/mediana.
fila_objetivo_peer = extraer_metricas_peer(
    TICKER, info, "Empresa analizada", 0
)
if fila_objetivo_peer is not None:
    fila_objetivo_peer["Relación"] = "Empresa analizada"
    fila_objetivo_peer["Similitud por tamaño (0-100)"] = 100.0
    fila_objetivo_peer["Origen"] = "Ticker configurado"
    tabla_comparacion_empresa = pd.concat(
        [pd.DataFrame([fila_objetivo_peer]).reindex(columns=columnas_peer), tabla_comparables],
        ignore_index=True,
    )
else:
    tabla_comparacion_empresa = tabla_comparables.copy()

metricas_para_estadisticas = [
    "PER trailing", "PER forward", "EV/EBITDA", "EV/Ingresos",
    "P/Ventas", "P/Valor contable", "Margen neto (%)",
    "Margen operativo (%)", "Crecimiento ventas (%)",
    "Crecimiento beneficios (%)", "ROE (%)", "Deuda/Patrimonio (%)",
    "Rentabilidad FCF (%)", "Beta",
]
filas_stats_peers = []
for metrica in metricas_para_estadisticas:
    serie = pd.to_numeric(tabla_comparables[metrica], errors="coerce") if metrica in tabla_comparables else pd.Series(dtype=float)
    serie = serie.replace([np.inf, -np.inf], np.nan).dropna()
    # Los múltiplos de valoración negativos/no positivos no son interpretables
    # como una valoración convencional; se excluyen solo para esos múltiplos.
    if metrica in ["PER trailing", "PER forward", "EV/EBITDA", "EV/Ingresos", "P/Ventas", "P/Valor contable"]:
        serie = serie[serie > 0]
    filas_stats_peers.append({
        "Métrica": metrica,
        "Media comparables": serie.mean() if len(serie) else np.nan,
        "Mediana comparables": serie.median() if len(serie) else np.nan,
        "Número de empresas con dato": int(serie.count()),
    })
tabla_estadisticas_comparables = pd.DataFrame(filas_stats_peers).set_index("Métrica")

print("\n--- COMPARABLES SELECCIONADOS (máximo 10; empresa objetivo excluida) ---")
if tabla_comparables.empty:
    print("Yahoo Finance no ha devuelto comparables utilizables para este ticker.")
    print("Comprueba que el ticker tenga sector/industria asignados en Yahoo Finance y que yfinance esté actualizado.")
else:
    mostrar(tabla_comparables.round(2), filas=MAX_COMPARABLES)
    print(f"\nNúmero de comparables seleccionados: {len(tabla_comparables)} (máximo {MAX_COMPARABLES})")
    print("La puntuación de similitud compara tamaños, no la calidad ni la competencia directa de cada negocio.")
    print("Las empresas se obtienen de las listas de industria/sector y del screener de Yahoo cuando está disponible.")

print("\n--- EMPRESA ANALIZADA Y COMPARABLES ---")
if not tabla_comparacion_empresa.empty:
    mostrar(tabla_comparacion_empresa.round(2), filas=MAX_COMPARABLES + 1)

print("\n--- MEDIA Y MEDIANA DE LOS COMPARABLES ---")
mostrar(tabla_estadisticas_comparables.round(2))
print("Nota: la empresa analizada no entra en la media/mediana. Los múltiplos no positivos se excluyen.")

# ============================================================
# 14. COMPARACIÓN DE MODELOS Y REVISIÓN DE DATOS AUSENTES
# ============================================================

comparacion = pd.DataFrame()
if not tabla_escenarios_eps.empty:
    comparacion = tabla_escenarios_eps[["Escenario", "Horizonte (años)", "Precio objetivo", "Potencial acumulado (%)"]].rename(columns={
        "Precio objetivo": "Precio objetivo EPS/PER",
        "Potencial acumulado (%)": "Potencial EPS/PER (%)",
    })
if not tabla_escenarios_fcf.empty:
    comparacion_fcf = tabla_escenarios_fcf[["Escenario", "Horizonte (años)", "Precio objetivo", "Potencial acumulado (%)"]].rename(columns={
        "Precio objetivo": "Precio objetivo FCF",
        "Potencial acumulado (%)": "Potencial FCF (%)",
    })
    comparacion = comparacion.merge(comparacion_fcf, on=["Escenario", "Horizonte (años)"], how="outer") if not comparacion.empty else comparacion_fcf

filas_faltantes = []
for nombre_tabla, tabla in [
    ("Trimestral", tabla_trimestral),
    ("Financiera anual", tabla_financiera),
    ("Valoración histórica", tabla_historica),
    ("Valoración actual", tabla_actual),
    ("Comparables", tabla_comparables),
    ("Empresa y comparables", tabla_comparacion_empresa),
]:
    if tabla is None or tabla.empty:
        filas_faltantes.append({"Tabla": nombre_tabla, "Columna": "Tabla completa", "Datos ausentes": np.nan, "Filas": 0})
        continue
    faltantes = tabla.isna().sum()
    for columna, cantidad in faltantes.items():
        if cantidad > 0:
            filas_faltantes.append({
                "Tabla": nombre_tabla,
                "Columna": columna,
                "Datos ausentes": int(cantidad),
                "Filas": len(tabla),
            })
tabla_datos_ausentes = pd.DataFrame(filas_faltantes)

print("\n" + "=" * 100)
print("COMPARACIÓN DE MÉTODOS")
print("=" * 100)
if not comparacion.empty:
    mostrar(comparacion.round(2))
else:
    print("No hay suficientes datos para comparar las valoraciones.")
print("\n" + "=" * 100)
print("REVISIÓN DE DATOS AUSENTES")
print("=" * 100)
if not tabla_datos_ausentes.empty:
    mostrar(tabla_datos_ausentes)
else:
    print("No hay datos ausentes en las tablas evaluadas.")

# ============================================================
# 14B. NUEVO MODELO FUNDAMENTAL: DIVISAS, PROYECCIÓN Y DCF
# ============================================================
def _precio_fx(ticker_fx):
    try:
        serie = yf.Ticker(ticker_fx).history(period="14d", auto_adjust=False)
        return numero(serie["Close"].dropna().iloc[-1]) if not serie.empty else np.nan
    except Exception:
        return np.nan

fx_fin_a_cot, fx_origen = fx_rate(divisa_financiera, divisa_cotizacion, _precio_fx)
# Vigencia: se contrasta el último trimestre Yahoo con publicaciones posteriores
# mediante SEC cuando haya CIK; para el resto se advierte con fecha Yahoo.
try:
    from actualidad_financiera import comprobar_actualidad
    comprobacion_actualidad = comprobar_actualidad(
        sec_cik=sec_metadata.get('CIK'), sec_user_agent=SEC_USER_AGENT,
        quarterly_dates=list(tabla_trimestral_usd.index) if not tabla_trimestral_usd.empty else [],
        earnings_dates=list(earnings_dates.index) if not earnings_dates.empty else [],
        as_of=hoy,
    )
except Exception as exc:
    comprobacion_actualidad={'newer_filing_confirmed':False,
       'status':'NO_VERIFICADO','detail':f'No se pudo comprobar fecha de presentación: {exc}'}
tabla_actualidad = pd.DataFrame([comprobacion_actualidad])

from referencias_oficiales import comprobar_ir
comprobacion_ir=comprobar_ir(TICKER,tabla_trimestral_usd,divisa_financiera,hoy)
if comprobacion_ir['status']=='BLOQUEO':
    comprobacion_actualidad.update(status='BLOQUEO',
       newer_filing_confirmed=comprobacion_ir['newer_filing_confirmed'],detail=comprobacion_ir['detail'])
tabla_actualidad=pd.DataFrame([{k:v for k,v in comprobacion_actualidad.items() if k not in ('comparisons','extraordinary')}])
fundamental_kwargs=dict(
    price=precio_actual,
    market_cap=capitalizacion_actual, shares_outstanding=primer_valor_disponible(info.get("sharesOutstanding"), acciones_en_circulacion),
    financial_currency=divisa_financiera, quote_currency=divisa_cotizacion,
    fx=fx_fin_a_cot, fx_source=fx_origen, source=fuente_historico_anual,
    stock_comp=info.get("stockBasedCompensation"), is_demo=False,
    quarterly=tabla_trimestral_usd if not tabla_trimestral_usd.empty else None,
    fiscal_end_date=fecha_ultimo_ejercicio,
    as_of=hoy, ticker=TICKER, info=info,
    recent_results_check=comprobacion_actualidad,
)
from auditoria_io import write_snapshot
from pathlib import Path
snapshot_dir=os.environ.get('VALUACION_SNAPSHOT_DIR','')
if snapshot_dir:
    write_snapshot(Path(snapshot_dir)/(TICKER+'_inputs.json'),tabla_financiera_usd,universo_df,fundamental_kwargs,
        {'Escenarios EPS PER':tabla_escenarios_eps,'Escenarios FCF':tabla_escenarios_fcf},evidence={'ir':comprobacion_ir})
resultados_fundamentales = build_fundamental_model(tabla_financiera_usd,universo_df,**fundamental_kwargs)
tabla_supuestos_fundamentales = resultados_fundamentales.assumptions
tabla_proyeccion_fundamental = resultados_fundamentales.projected
tabla_valoracion_fundamental = resultados_fundamentales.valuation
tabla_dcf_detalle = resultados_fundamentales.dcf_detail
tabla_control_modelo = resultados_fundamentales.checks
tabla_comparables_depurados = resultados_fundamentales.peers
# V5: universo y lista seleccionada obtenidos del MISMO cálculo de puntuación.
tabla_universo_peers = resultados_fundamentales.peer_universe
if registro_candidatos:
    tracked=pd.DataFrame(registro_candidatos.values())
    if tabla_universo_peers.empty:tabla_universo_peers=tracked
    else:tabla_universo_peers=tabla_universo_peers.merge(tracked[['Ticker','Estado descarga','Detalle descarga']],on='Ticker',how='outer')
if not tabla_universo_peers.empty and not tabla_comparables_depurados.empty:
    elegidos=set(tabla_comparables_depurados['Ticker'])
    tabla_comparables=tabla_universo_peers[
        tabla_universo_peers['Ticker'].isin(elegidos)].copy().reset_index(drop=True)
    tabla_comparacion_empresa=pd.concat([
        pd.DataFrame([fila_objetivo_peer]) if fila_objetivo_peer is not None else pd.DataFrame(),
        tabla_comparables],ignore_index=True)
else:
    tabla_comparables=pd.DataFrame()
    tabla_comparacion_empresa=(pd.DataFrame([fila_objetivo_peer])
                               if fila_objetivo_peer is not None else pd.DataFrame())

tabla_roic_medio = resultados_fundamentales.roic
tabla_valoracion_inversa = resultados_fundamentales.reverse
tabla_puente_fiscal = resultados_fundamentales.fiscal_bridge
tabla_base_ttm = resultados_fundamentales.base_ttm
tabla_referencia_peers = resultados_fundamentales.peer_reference
# Comparación de métricas: se eligen solo los peers ECONÓMICAMENTE comparables,
# evitando contaminar las medias con toda la lista sectorial de Yahoo.
seleccion_peers_calidad = (set(tabla_comparables_depurados.loc[
    tabla_comparables_depurados['Elegible'] == True, 'Ticker'])
    if not tabla_comparables_depurados.empty else set())
peers_para_stats = tabla_comparables[tabla_comparables['Ticker'].isin(seleccion_peers_calidad)] if not tabla_comparables.empty else pd.DataFrame()
filas_stats_economicos = []
for campo in metricas_para_estadisticas:
    v=pd.to_numeric(peers_para_stats[campo],errors='coerce').replace([np.inf,-np.inf],np.nan).dropna() if campo in peers_para_stats else pd.Series(dtype=float)
    if campo in ('PER trailing','PER forward','EV/EBITDA','EV/Ingresos','P/Ventas','P/Valor contable'):
        v=v[v>0]
    v=v if len(v)>=3 else pd.Series(dtype=float)
    filas_stats_economicos.append({'Métrica':campo,'Media comparables':v.mean() if len(v) else np.nan,
             'Mediana comparables':v.median() if len(v) else np.nan,'Número de empresas con dato':len(v)})
tabla_stats_peers_economicos=pd.DataFrame(filas_stats_economicos).set_index('Métrica')
# Este resumen es el único autorizado para promedios de comparables.
# Se abandona la tabla preliminar (vacía antes del scoring definitivo).
tabla_estadisticas_comparables = tabla_stats_peers_economicos.copy()
print(f"V5: {len(tabla_universo_peers)} candidatos revisados; "
      f"{len(tabla_comparables_depurados)} comparables económicos seleccionados; "
      f"medianas PER / EV: {tabla_referencia_peers.to_dict('records') if not tabla_referencia_peers.empty else 'N/D'}")



if divisa_financiera != divisa_cotizacion:
    # Los escenarios antiguos no aplicaban conversión FX de moneda por acción.
    # V2 hace la conversión de forma explícita y, si no está disponible, bloquea.
    tabla_escenarios_eps = tabla_escenarios_eps.iloc[0:0]
    tabla_escenarios_fcf = tabla_escenarios_fcf.iloc[0:0]
    if np.isfinite(fx_fin_a_cot):
        per_corregido = dividir_seguro(precio_actual,eps_ultimo*fx_fin_a_cot)
        ev_corregido = capitalizacion_actual+deuda_neta_ultimo*fx_fin_a_cot if pd.notna(capitalizacion_actual) and pd.notna(deuda_neta_ultimo) else np.nan
        tabla_actual.loc['PER con EPS del último ejercicio','Valor']=per_corregido
        tabla_actual.loc['Valor de empresa aproximado (miles de millones)','Valor']=ev_corregido/1e9
        tabla_actual.loc['EV/EBITDA aproximado','Valor']=dividir_seguro(ev_corregido,ebitda_ultimo*fx_fin_a_cot)
        tabla_actual.loc['EV/FCF aproximado','Valor']=dividir_seguro(ev_corregido,fcf_ultimo*fx_fin_a_cot)
        tabla_actual.loc['Rentabilidad FCF (%)','Valor']=100*dividir_seguro(fcf_ultimo*fx_fin_a_cot,capitalizacion_actual)
    else:
        for c in ('PER con EPS del último ejercicio','Valor de empresa aproximado (miles de millones)','EV/EBITDA aproximado','EV/FCF aproximado','Rentabilidad FCF (%)'):
            tabla_actual.loc[c,'Valor']=np.nan
    warnings.warn("Sin FX histórico, los escenarios de valoración heredados se bloquean para monedas diferentes. El modelo fundamental usa FX explícito.")

from auditoria_io import valuation_registry
tabla_registro=valuation_registry(tabla_valoracion_fundamental,tabla_escenarios_eps,tabla_escenarios_fcf,
    as_of=hoy.date(),fy_date=fecha_ultimo_ejercicio.date(),
    ttm_date=resultados_fundamentales.assumptions.set_index('Supuesto').loc['Fecha base TTM','Valor'],
    currency=divisa_cotizacion,source=fuente_historico_anual,freshness=comprobacion_actualidad['status'])
tabla_estadisticas_crecimiento=pd.DataFrame([
    {'Indicador':name,'Media (%)':100*stats['media'],'Mediana (%)':100*stats['crecimientos'].median(),
     'CAGR (%)':100*cagr,'Desviación (pp)':100*stats['desviacion'],'Intervalos':stats['observaciones'],
     'Limitación':'Sensibilidad histórica; media compuesta no es pronóstico; atípicos conservados'}
    for name,stats,cagr in [('EPS',stats_eps,cagr_eps),('FCF',stats_fcf,cagr_fcf)]])

# Resumen de metadatos para la hoja general del Excel y el panel web.
tabla_general = pd.DataFrame([
    {"Concepto": "Empresa", "Valor": nombre_empresa},
    {"Concepto": "Ticker", "Valor": TICKER},
    {"Concepto": "Divisa financiera", "Valor": divisa_financiera},
    {"Concepto": "Divisa de cotización", "Valor": divisa_cotizacion},
    {"Concepto": "Sector", "Valor": sector_objetivo},
    {"Concepto": "Industria", "Valor": industria_objetivo},
    {"Concepto": "Último cierre fiscal disponible", "Valor": fecha_ultimo_ejercicio.date() if pd.notna(fecha_ultimo_ejercicio) else "No disponible"},
    {"Concepto": "Fuente histórico anual", "Valor": fuente_historico_anual},
    {"Concepto": "CIK SEC", "Valor": sec_metadata.get("CIK") or "No disponible"},
    {"Concepto": "FX moneda financiera a moneda cotización", "Valor": fx_fin_a_cot},
    {"Concepto": "Fuente FX", "Valor": fx_origen},
    {"Concepto": "Previsión económica", "Valor": "Base TTM + puente FY + sensibilidad, NO consenso de analistas"},
    {"Concepto": "Fecha valoración", "Valor": hoy.date()},
    {"Concepto": "Comparables económicos", "Valor": "Selección automática multi-región por actividad + finanzas"},
    {"Concepto": "Candidatos comparables evaluados", "Valor": len(tabla_universo_peers)},
    {"Concepto": "Comparables elegibles", "Valor": int(tabla_universo_peers.get('Elegible',pd.Series(dtype=bool)).fillna(False).sum())},
    {"Concepto": "Ejercicios anuales disponibles", "Valor": len(tabla_financiera_usd)},
    {"Concepto": "Cobertura SEC 10 ejercicios", "Valor": "Completa" if len(tabla_financiera_usd) >= 10 and not tabla_financiera_sec_usd.empty else "Incompleta / no SEC"},
    {"Concepto": "Auditoría Yahoo vs SEC", "Valor": ("OK (<1%) en campos comparados" if not tabla_resumen_comparacion.empty and (tabla_resumen_comparacion["Diferencias >=1%"] == 0).all() else "Con incidencias o no disponible")},
    {"Concepto": "Estado de extracción SEC", "Valor": sec_metadata.get("Estado", "No disponible")},
    {"Concepto": "Próxima publicación indicada por Yahoo", "Valor": proxima_publicacion},
])

# ============================================================
# 15. EXPORTAR TODA LA INFORMACIÓN A UN ÚNICO EXCEL
# ============================================================
ticker_archivo = re.sub(r"[^A-Za-z0-9_.-]", "_", TICKER)
archivo_salida = Path(f"valoracion_completa_{ticker_archivo}.xlsx")


def escribir_informe_excel(ruta):
    """Escribe todas las tablas disponibles en el archivo indicado."""
    with pd.ExcelWriter(ruta, engine="openpyxl") as writer:
        tabla_general.to_excel(writer, sheet_name="General", index=False)
        tabla_registro.to_excel(writer,sheet_name="Registro valoraciones",index=False)
        tabla_estadisticas_crecimiento.to_excel(writer,sheet_name="Estadisticas crecimiento",index=False)
        pd.DataFrame(comprobacion_ir['comparisons']).to_excel(writer,sheet_name="Contraste IR",index=False)
        pd.DataFrame(comprobacion_ir['extraordinary']).to_excel(writer,sheet_name="Extraordinarios IR",index=False)
        # V2: la valoración principal (no requiere diez años SEC para funcionar).
        tabla_supuestos_fundamentales.to_excel(writer, sheet_name="Supuestos fundamentales", index=False)
        tabla_proyeccion_fundamental.to_excel(writer, sheet_name="Proyeccion negocio", index=False)
        tabla_valoracion_fundamental.to_excel(writer, sheet_name="Valoracion fundamental", index=False)
        tabla_dcf_detalle.to_excel(writer, sheet_name="DCF detalle", index=False)
        resultados_fundamentales.risk_parameters.to_excel(writer,sheet_name="Parametros riesgo",index=False)
        tabla_control_modelo.to_excel(writer, sheet_name="Control modelo", index=False)
        tabla_actualidad.to_excel(writer, sheet_name="Actualidad resultados", index=False)
        tabla_comparables_depurados.to_excel(writer, sheet_name="Comparables depurados", index=False)
        if not tabla_universo_peers.empty:
            tabla_universo_peers.to_excel(writer, sheet_name="Universo comparables", index=False)
        tabla_roic_medio.to_excel(writer, sheet_name="ROIC capital medio", index=False)
        resultados_fundamentales.roic_ttm.to_excel(writer,sheet_name="ROIC TTM capital medio",index=False)
        tabla_valoracion_inversa.to_excel(writer, sheet_name="Valoracion inversa", index=False)
        tabla_puente_fiscal.to_excel(writer, sheet_name="Puente ejercicio fiscal", index=False)
        tabla_base_ttm.to_excel(writer, sheet_name="Base TTM y balance", index=False)
        tabla_referencia_peers.to_excel(writer, sheet_name="Referencia comparables", index=False)
        tabla_stats_peers_economicos.to_excel(writer, sheet_name="Estadisticas peers economicos")
        if not tabla_trimestral.empty:
            tabla_trimestral.to_excel(writer, sheet_name="Resultados trimestrales", index=False)
        tabla_financiera.to_excel(writer, sheet_name="Financieros anuales")
        if not tabla_fuentes_sec.empty:
            tabla_fuentes_sec.to_excel(writer, sheet_name="Fuentes SEC", index=False)
        if not tabla_resumen_comparacion.empty:
            tabla_resumen_comparacion.to_excel(writer, sheet_name="Resumen Yahoo SEC", index=False)
        if not tabla_comparacion_fuentes.empty:
            tabla_comparacion_fuentes.to_excel(writer, sheet_name="Comparacion Yahoo SEC", index=False)
        tabla_historica.to_excel(writer, sheet_name="Valoracion historica")
        estadisticas.to_excel(writer, sheet_name="Estadisticas historicas")
        tabla_actual.to_excel(writer, sheet_name="Valoracion actual")
        if not tabla_comparables.empty:
            tabla_comparables.to_excel(writer, sheet_name="Comparables", index=False)
        if not tabla_comparacion_empresa.empty:
            tabla_comparacion_empresa.to_excel(writer, sheet_name="Empresa y comparables", index=False)
        tabla_estadisticas_comparables.to_excel(writer, sheet_name="Estadisticas comparables")
        tabla_publicacion.to_excel(writer, sheet_name="Fecha resultados", index=False)
        tabla_cagr.to_excel(writer, sheet_name="CAGR", index=False)
        tabla_cagr_ventanas.to_excel(writer, sheet_name="CAGR 5 y 10", index=False)
        tabla_crecimientos.to_excel(writer, sheet_name="Crecimientos EPS FCF", index=False)
        tabla_per.to_excel(writer, sheet_name="PER historico")
        if not tabla_parametros.empty:
            tabla_parametros.to_excel(writer, sheet_name="Parametros escenarios")
        if not tabla_escenarios_eps.empty:
            tabla_escenarios_eps.to_excel(writer, sheet_name="Escenarios EPS PER", index=False)
        if not tabla_escenarios_fcf.empty:
            tabla_escenarios_fcf.to_excel(writer, sheet_name="Escenarios FCF", index=False)
        if not comparacion.empty:
            comparacion.to_excel(writer, sheet_name="Comparacion", index=False)
        tabla_datos_ausentes.to_excel(writer, sheet_name="Datos ausentes", index=False)


try:
    escribir_informe_excel(archivo_salida)
except PermissionError:
    # Excel suele bloquear el archivo si está abierto. En vez de detener todo
    # el proceso, guardar el informe con una marca de tiempo.
    marca_tiempo = datetime.now().strftime("%Y%m%d_%H%M%S")
    archivo_respaldo = Path(
        f"valoracion_completa_{ticker_archivo}_{marca_tiempo}.xlsx"
    )
    try:
        escribir_informe_excel(archivo_respaldo)
        warnings.warn(
            f"No se pudo sobrescribir '{archivo_salida}'. Puede estar abierto "
            f"en Excel o bloqueado por otro proceso. El informe se guardó en "
            f"'{archivo_respaldo.resolve()}'. Cierra el archivo original para "
            "poder sobrescribirlo en la próxima ejecución."
        )
        archivo_salida = archivo_respaldo
    except PermissionError as error:
        raise PermissionError(
            f"No se pudo guardar el Excel ni en '{archivo_salida}' ni en "
            f"'{archivo_respaldo}'. Cierra los archivos Excel abiertos y "
            "comprueba que tienes permisos de escritura en la carpeta."
        ) from error

print("\n" + "=" * 100)
print("ANÁLISIS FINALIZADO")
print("=" * 100)
print(f"Empresa: {nombre_empresa} ({TICKER})")
print(f"Archivo Excel creado: {archivo_salida.resolve()}")
print("Hojas: General, Resultados trimestrales, Financieros anuales, Valoracion historica,")
print("       Fuentes SEC (si está disponible), Estadisticas historicas, Valoracion actual, Comparables,")
print("       Empresa y comparables, Estadisticas comparables, Fecha resultados,")
print("       CAGR, Crecimientos EPS FCF, PER historico, Parametros escenarios,")
print("       Escenarios EPS PER, Escenarios FCF, Comparacion y Datos ausentes.")
print("\nIMPORTANTE: los escenarios son cálculos condicionados a supuestos históricos; no son predicciones garantizadas.")
