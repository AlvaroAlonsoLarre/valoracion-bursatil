# Valoración bursátil multiempresa

Motor de sensibilidades financieras con entradas Yahoo, histórico SEC cuando existe cobertura y contraste IR fechado. Los resultados son condicionales; una ejecución técnica completada no acredita una valoración financiera validada.

Instalación reproducible (Python 3.12):

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.lock
.venv/bin/python -m pytest -q tests
.venv/bin/python autoprueba_modelo.py
.venv/bin/python prueba_comparables_automaticos.py
.venv/bin/python test_v5.py
.venv/bin/python ejecutar_analisis.py --ticker MSFT --outdir Resultados/MSFT
.venv/bin/python ejecutar_analisis.py --ticker 000660.KS --outdir Resultados/000660.KS
```

Cada análisis guarda Excel, JSON, log y entradas financieras en JSON. Código 0 indica que hay al menos un resultado fundamental condicional utilizable, 2 indica insuficiencia financiera/bloqueo y 1 un fallo técnico. Los artefactos se conservan. Comparables insuficientes afectan a sus múltiplos; por sí solos no invalidan un DCF que cumpla sus requisitos. Los objetivos históricos se identifican como sensibilidades FY y no se agregan con DCF.

Para reproducir las entradas sin consultar red:

```bash
.venv/bin/python ejecutar_analisis.py --snapshot Resultados/MSFT/MSFT_inputs.json --outdir Resultados/replay
```

Configura un contacto SEC real con `SEC_CONTACT_EMAIL` si dispones de él. Su ausencia se declara `NO_VERIFICADO`; no se inventa un contacto. Los parámetros WACC tienen fuente/fecha/moneda/estado en `Parametros riesgo`; los valores por defecto siguen siendo supuestos. Los overrides usan `VALUACION_TIPO_LIBRE_RIESGO`, `VALUACION_PRIMA_RIESGO_MERCADO`, `VALUACION_BETA`, `VALUACION_COSTE_DEUDA`, `VALUACION_WACC` y `VALUACION_PARAMETROS_MONEDA`. Para los cuatro primeros se admite `_FECHA`, `_FUENTE`, `_CADUCIDAD`. La caducidad vencida bloquea y `VALUACION_ERP_INCLUYE_PAIS=true` impide volver a añadir `VALUACION_RIESGO_PAIS`.

El workflow instalado es `.github/workflows/main.yml`; `analisis_bursatil.yml` es una copia de referencia. Push/PR analiza MSFT y 000660.KS con el mismo SHA. La ejecución manual admite cualquier ticker o la matriz por defecto. No escribe resultados en `main` ni fusiona PRs. Los artefactos por ticker y el manifiesto distinguen cobertura completa de suficiencia financiera. En particular, un job de valoración puede fallar correctamente por código 2 y conservar todo su diagnóstico.

Los JSON de `Resultados_publicados/` y los documentos V3/V5/V6 son evidencia histórica del comportamiento anterior. **No son objetivos validados ni describen las garantías actuales.** Consulta el [informe de correcciones](docs/auditoria_2026-11-11/INFORME.md), sus entradas congeladas y el CSV de comparación.

La [continuación del 12/11/2026](docs/auditoria_2026-11-12/INFORME.md) incorpora D&A pura oficial de MSFT y Q3 oficial de SK. MSFT dispone de DCF condicional; los múltiplos y las valoraciones de SK conservan sus bloqueos. Las nuevas hojas `Fuentes fundamentales`, `Conciliacion TTM`, `Comparables requisitos` y `Pendientes fundamentales` detallan fuentes y cobertura por método.
