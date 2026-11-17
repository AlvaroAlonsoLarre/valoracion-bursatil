# Cinco comparables económicos: revisión del 16-11-2026

Base: `feat/mi-seguimiento`, commit `b522600e6dd5a2c2c199fedd8eb416e5a4650992`.
Cambios propuestos en `fix/comparables-cinco`. No se modifica `main`.

## Resultado con perfiles descargados durante esta revisión

| Empresa | Comparables informativos seleccionados | Cobertura |
|---|---|---|
| MSFT | ORCL, SAP, CRM, NOW, ADBE | 5/5 |
| 000660.KS | 005930.KS, MU, 2408.TW, 2344.TW, 285A.T | 5/5 |
| JNJ | ABBV, LLY, MRK, AMGN, GILD | 5/5 |
| JPM | BAC, RY, WFC, C, TD | 5/5 |
| NVDA | AVGO, AMD, INTC, QCOM, MRVL | 5/5 |

Cada JSON dentro de `evidencias.zip` conserva `captured_at`, el perfil del objetivo, los perfiles
descargados, las peticiones fallidas y la selección. Cada CSV presenta la tabla.
Se descargaron los perfiles mediante Yahoo/yfinance; la selección final se volvió
a calcular sobre esos mismos perfiles al corregir las reglas. No son cotizaciones
en tiempo real ni un dictamen de equivalencia completa entre negocios.

Las consultas sufrieron límites de Yahoo. Se conservaron perfiles ya descargados
y se completaron los pendientes en ejecuciones posteriores. En una primera
pasada, JPM/NVDA quedaron sin cobertura suficiente: no se contaron como éxitos.
La tabla anterior describe el resultado final de la selección, no el éxito de
cada intento de red. Los errores permanecen en los JSON.

## Justificación y límites económicos

- MSFT: software empresarial y suscripciones; Oracle también tiene cloud.
  Adobe tiene otra mezcla de clientes/productos; SAP, Salesforce y ServiceNow no
  reproducen todos los segmentos de Microsoft.
- SK hynix: memoria DRAM/NAND y/o especializada. Samsung es un conglomerado;
  Kioxia está centrada en NAND; Nanya/Winbond tienen exposiciones diferentes.
  No se incorporan UMC/TSMC ni diseñadores de IP HBM para completar el grupo.
- JNJ: farmacéuticas con productos terapéuticos; no replican el segmento MedTech.
- JPM: bancos diversificados. Se excluye Berkshire/aseguradoras aunque sus
  descripciones mencionen negocios bancarios o inversiones en bancos.
- NVDA: procesadores, aceleración, conectividad y chips para cómputo; QCOM tiene
  más exposición a móviles, Broadcom a infraestructura/software e Intel integra
  fabricación. No se confunden los clientes de automoción con el sector de la
  empresa; no se incorporan fabricantes de memoria ni proveedores analógicos
  solo por compartir la industria genérica de semiconductores.

## Cambios

1. Hasta cinco emisores únicos con actividad relacionada, al menos dos datos
   básicos entre precio/capitalización/ingresos y un ratio positivo disponible.
   Se conserva cada indicador ausente por separado; no se exige tener los tres.
2. Selección heurística por actividad, industria, tamaño en moneda comparable y
   disponibilidad. No se rellena hasta cinco con candidatos incompatibles.
3. Tabla `Comparables informativos` y cobertura en dashboard, Mi seguimiento y
   Excel. Fechas, monedas y límites visibles.
4. Descubrimiento opcional FMP/Finnhub mediante claves de entorno, con caché y
   fallos aislados. No había claves disponibles: estos conectores se probaron
   con respuestas controladas; NO se afirma haber probado su acceso real ni
   que los endpoints estén incluidos gratuitamente en una cuenta concreta.
5. Un único descubrimiento Yahoo por análisis, menos regiones/peticiones
   redundantes y descarga por lotes con parada al reunir cobertura suficiente.
   Una respuesta de límite interrumpe el lote; el diagnóstico conserva el fallo.
6. Los ratios informativos no se usan automáticamente para objetivos. Los
   controles existentes de TTM/NTM, base contable, divisa y deuda siguen vigentes.

## Validación

- 137 pruebas locales superadas: comparables, modelo financiero, datos generales,
  sensibilidad, auditoría, periodos, fuentes oficiales, exportación y dashboard.
- Tres scripts de regresión heredados superados: `autoprueba_modelo.py`,
  `prueba_comparables_automaticos.py`, `test_v5.py`.
- Streamlit AppTest: ninguna excepción; cobertura 5/5 en la pestaña Comparables
  usando la captura MSFT archivada. Las capturas archivadas no se presentan como
  consultas de hoy.
- Sintaxis Python y `git diff --check` correctos.
- Los resultados locales no equivalen a ejecutar toda la batería Linux/Windows:
  la validación completa se realiza en el workflow de la PR, que dispone de los
  ZIP históricos del repositorio.

## Reproducir

```bash
python verificar_comparables.py --tickers MSFT 000660.KS JNJ JPM NVDA --outdir Resultados/comparables
python -m pytest -q tests/test_comparables_cinco.py
```

El comando usa las fuentes disponibles, guarda evidencia y devuelve 2 si algún
ticker no reúne cinco empresas. La cobertura puede cambiar con los proveedores.
Las semillas económicas revisables de `comparables_config.json` complementan la
búsqueda de MSFT/SK hynix; las otras tres empresas se probaron sin semillas por
ticker. La selección automática requiere revisión al ampliar sectores.
