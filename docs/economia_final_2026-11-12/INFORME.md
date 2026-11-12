# Revisión económica final de la V6 — 12/11/2026

Se validan los **13 tickers con datos reales** y ambos motores sobre **las mismas capturas**. Las fórmulas EPS × PER se conservan; cambian la normalización y las referencias admisibles. **No se calibran las hipótesis a la cotización.** Las valoraciones siguen teniendo confianza Baja.

| Ticker | Moneda | Base 1 año: antes → final | Base 3 años: antes → final |
|---|---|---|---|
| NVDA | USD | 619,72 → 496,90 | 1.268,89 → 1.159,41 |
| MU | USD | 1.590,10 → 416,88 | 964,04 → 665,60 |
| META | USD | 924,33 → 912,55 | 1.370,30 → 1.352,84 |
| 000660.KS | KRW | 3.519.301,95 → Sin automático | 2.326.328,42 → Sin automático |
| AMZN | USD | 199,00 → Sin automático | 237,93 → Sin automático |
| GOOG | USD | 287,77 → 273,43 | 380,56 → 361,59 |
| GOOGL | USD | 285,63 → 271,79 | 377,74 → 359,43 |
| MSFT | USD | 696,84 → 696,84 | 940,68 → 940,68 |
| NFLX | USD | 93,86 → 93,86 | 121,78 → 121,78 |
| JNJ | USD | 234,23 → 234,23 | 282,74 → 282,74 |
| JPM | USD | 290,93 → 290,93 | 383,68 → 383,68 |
| SNDK | USD | Sin automático → Sin automático | Sin automático → Sin automático |
| SPCX | USD | Sin automático → Sin automático | Sin automático → Sin automático |

**Por qué cambian:**

- **NVDA:** el margen inicial pasa de 65,2% a **54,1% normalizado**. El crecimiento compuesto se desacelera de **68,3% a 46,6%**, en lugar de usar medianas de tasas; el PER pasa de 51,29 a **48,51**, con tres FY del régimen reciente y sin fiscalidad atípica. Aun así, supone casi **3,9× los ingresos TTM en tres años**: sigue siendo una hipótesis exigente.
- **MU:** margen inicial **74,6% → 26,1%**; crecimiento **44,3% → 23,2%**; PER **14,48 → 11,25**, excluyendo beneficios cíclicos de pico/valle y fiscalidad atípica. Se evita aplicar otra vez el margen de pico sobre ingresos TTM ya elevados.
- **SK:** margen **74,5% → 25,4%** y crecimiento compuesto **29,6%**. El FY2022 de baja rentabilidad/fiscalidad atípica deja sólo **dos PER limpios**. Se conserva la proyección EPS, pero no se fuerza un precio automático con menos observaciones que las exigidas.
- **META:** crecimiento **19,9%** y margen **39,6%** se mantienen. El cambio pequeño procede del PER **24,43 → 24,11** al excluir FY2025 por fiscalidad atípica (29,6% frente a mediana 17,6%).
- **AMZN:** se separan los resultados financieros de inversión del puente recurrente. Su 10-Q oficial declara **62.853 M USD** de revalorizaciones de inversiones privadas y **4.474 M USD** de reclasificaciones de deuda en nueve meses de 2026, principalmente Anthropic; el desglose dimensional atribuye **62.800 M USD** a Anthropic. **No se suman totales con sus desgloses ni YTD con trimestres.** La previsión utiliza intereses identificados menos gasto puro; otros no operativos no se extrapolan sin evidencia. No se inventa un impuesto ni un EPS ajustado. Tras excluir ganancias materiales y el régimen anterior de márgenes, quedan sólo **dos PER limpios**: EPS proyectado disponible, precio automático pendiente. El criterio se aplica a cualquier empresa no financiera; las financieras conservan su tratamiento propio.
- **GOOG/GOOGL:** bajan por el puente recurrente de intereses y la depuración del PER. Conservan estados consolidados comunes y precios de clase distintos. MSFT, NFLX, JNJ y JPM mantienen sus objetivos.

**Sensibilidad del precio Base a tres años**, una variable cada vez, resto fijo (USD; no intervalos de confianza):

| Ticker | Crecimiento ±5 puntos anuales | Margen ±3 puntos | PER ±20% |
|---|---|---|---|
| NVDA | 1.052,09–1.273,78 | 1.096,75–1.222,07 | 927,53–1.391,29 |
| MU | 593,41–743,40 | 588,45–742,74 | 532,48–798,72 |
| META | 1.190,54–1.529,25 | 1.251,75–1.453,93 | 1.082,27–1.623,40 |

En **SK**, sin escoger un PER, esas variaciones cambian el EPS a tres años **−11,1%/+12,0%** por crecimiento y **±13,3%** por margen; a múltiplo fijo tendrían el mismo efecto porcentual sobre el precio. No se publica por ello un objetivo.

**Dashboard:** Resumen muestra cotización, objetivos y crecimiento/margen/PER Base. Valoración añade las sensibilidades y un contraste inverso explícito de **retorno de precio cero**: iguala el precio futuro a la cotización, manteniendo el resto fijo. No es un pronóstico de las expectativas del mercado ni recalibra los supuestos.

**Límites pendientes:** no existe una cohorte suficiente de tres comparables homogéneos forward. El consenso secundario Yahoo de FY+1 (no año 3 ni NTM) muestra crecimiento de ingresos de aproximadamente 68% NVDA, 16% MU, 60% SK y 22% META: no valida márgenes ni PER futuros. El 23,2% terminal de MU requiere especialmente revisión. Una normalización histórica también puede infravalorar un cambio estructural persistente en IA/HBM. Los filtros de PER detectan distorsiones, no prueban ausencia de todos los extraordinarios. SNDK mantiene los problemas de EBIT/perímetro y SPCX los de pérdidas, atribución, fiscalidad e histórico bursátil. SK sigue sin CAPEX/D&A suficientes para FCF/DCF. Ningún control se elimina para recuperar precios.

**Validación y evidencias:** **126 pruebas** y tres suites originales aprobadas; [Actions](https://github.com/AlvaroAlonsoLarre/valoracion-bursatil/actions/runs/43284910445). Paridad numérica y textual de Excel/JSON/replay **13/13**, 132 trayectorias y 162 sensibilidades de precios verificadas. Se comprueban las seis pestañas en escritorio y móvil y las tres descargas del navegador. Quedan **54 precios principales** (nueve tickers × seis), frente a 66: retirar AMZN/SK por insuficiencia de PER limpio es deliberado. P/FCF, DCF y EV/EBITDA mantienen sus requisitos independientes.

[Comparación completa](comparacion.csv) · [Sensibilidad de precios](sensibilidad.csv) · [Sensibilidad de EPS](sensibilidad_relativa.csv) · [Comprobaciones](validacion.json) · [Fuentes AMZN y contraste Yahoo](fuentes/) · [Interfaz](interfaz/).

Los ZIP [1](ejecuciones_1.zip) y [2](ejecuciones_2.zip) conservan resultados, capturas, Excel, logs de descarga y replays del motor anterior; [manifest.json](manifest.json) enumera 148 archivos con SHA-256 comprobados al releer ambos ZIP. El 10-Q AMZN completo se conserva para revisar el desglose. Los snapshots duplicados del replay anterior se omiten: se utilizan las mismas entradas finales. Los datos de la ejecución previa también permanecen en el informe de generalización anterior.

Captura con red: `8a0e8d48236b19692af8beffbc964ceb97981a8e`. Código de cálculo/exportación verificado: `9fae07248d881e4c95d3f8d24a9dd911707eb720`. Motor anterior: `c6ee619f77ecd0062f3896bf8627e6b019bbd1dd`. Los cambios posteriores al cálculo económico sólo aclaran etiquetas/presentación e incorporan el verificador. La PR #1 permanece abierta, **sin fusionar a main**.

```bash
unzip ejecuciones_1.zip -d evidencia
unzip ejecuciones_2.zip -d evidencia
python docs/economia_final_2026-11-12/validar.py --after evidencia/final --before evidencia/antes_mismos_datos --previous evidencia_previa/after --output comprobacion
```
