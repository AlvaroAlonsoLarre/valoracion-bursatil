# V6 generalizada: diagnóstico multiempresa y escenarios independientes

Corte **12/11/2026**, hora de Madrid (UTC+1). Baseline: `f508b480ebacf085b9d8af467f0986f8d06ee119`. Código nuevo, publicado y ejecutado con red: **`5b9140121d624948841134b59973b8c4c92c0d47`**. Rama `fix/auditoria-msft-sk-hynix`, [PR #1](https://github.com/AlvaroAlonsoLarre/valoracion-bursatil/pull/1), sin fusionar a `main`.

Se ejecutaron los **13 tickers antes y después**: once generan seis precios EPS × PER, frente a cinco con seis precios y NVDA con dos en la V6 anterior. El total principal pasa de **32 a 66**. SNDK y SPCX conservan cuentas y diagnóstico, sin precios automáticos insuficientemente fundamentados. Todos los procesos terminan sin fallo técnico: salida 0 o insuficiencia financiera documentada 2.

## Cambios y evidencia de cada corrección

| Regla general | Antes | Después y evidencia |
|---|---|---|
| Conciliación SEC–Yahoo por campo | AMZN tenía ingresos/EBIT/neto ausentes en junio de 2026 | SEC completa el trimestre: ingresos 200.606 M USD y neto 62.647 M USD. Fuente y componentes en `Conciliacion SEC Yahoo`; seis precios EPS. No completa CAPEX mediante cero. |
| Cierres fiscales de 52/53 semanas | MU y SNDK confundían un cierre de calendario con una publicación posterior | Fecha real acreditada por al menos dos flujos coincidentes a <1%. MU: 31/08→03/09; SNDK: 30/09→02/10. El control de publicaciones posteriores continúa activo. |
| Clases y acciones consolidadas | GOOG/GOOGL y META bloqueaban EPS porque acciones de clase × precio no igualaba la capitalización del emisor | El control mantiene su ámbito de capitalización/EV. Un total implícito del proveedor es evidencia de mercado, nunca sustituye a las acciones diluidas contables. Las cuentas anuales GOOG/GOOGL son idénticas, CIK `0001652044`; los precios y referencias históricas son propios de cada clase. |
| Splits frente a dilución | La tendencia de acciones podía mezclar bases anteriores y posteriores a un split | Factores por fecha de presentación ajustan la serie antes de medir dilución; no se infieren splits a partir de saltos. NVDA y NFLX tienen diez referencias históricas conciliadas; la corrección sintética prueba un split que antes simulaba dilución. En NFLX las medianas recientes ya evitaban el salto y sus precios calculados no cambian. |
| Ciclo y crecimiento excepcional | Tasas constantes; NVDA superaba la salvaguarda de crecimiento en Base/Optimista | Mediana de tasas anuales hasta cinco observaciones al inicio y hasta diez al final; margen TTM converge a la mediana normalizada hasta el año 3. Ambos extremos se editan. Se mantiene el rango de tasas, sin ampliarlo para que pasen. NVDA pasa de 2 a 6 precios. |
| Registros de separación | El histórico anterior podía entrar en la normalización sin una advertencia de perímetro | Evidencia de registro `10-12B` o descripción de separación y fecha inicial de cotización identifican un perímetro pendiente. Se conserva la historia financiera; los periodos anteriores no entran en supuestos automáticos sin acreditar continuidad. SNDK mantiene cobertura, pero no se fuerzan crecimiento ni PER. |
| IPO sin CompanyFacts anual | SPCX sólo ofrecía un fallback Yahoo anual | Se verificó identidad SEC `0001181412`. El prospecto **424B4 del 12/06/2026**, accession `0001628280-26-042639`, contiene tres estados anuales oficiales 2023–2025. El extractor exige tabla consolidada, años únicos, periodo anual y escala expresa. Sus etiquetas se registran como etiquetas de tabla, sin inventar conceptos XBRL. No se crean cotizaciones anteriores a la IPO ni un PER histórico inexistente. |
| Ausencias y controles por dependencia | Falta de PER podía impedir hasta proyectar EPS | EPS/ingresos se proyectan independientemente del múltiplo y del precio observado si sus datos propios bastan. CAPEX/ROIC/DCF no invalidan EPS. Los cinco estados públicos separan dato disponible, proyección, advertencia, ausencia e inconsistencia. |
| Emisores comparables | Otra clase del mismo emisor podía aparecer como otro par | Se deduplica por CIK de evidencia disponible o nombre legal, conservando descartes. Se prefiere PER propio válido; TTM y NTM se contrastan por separado. No se fuerza una cohorte de tres. |
| Empresa nueva sin datos | Podía terminar como error técnico sin exportación | El ticker real de prueba inexistente `ZZUNLISTEDTEST` devuelve diagnóstico, Excel, captura y JSON, salida 2; ninguna cifra financiera se rellena con cero. |

Las nuevas reglas no contienen nombres de los tickers de validación. Permanecen los enriquecimientos oficiales anteriores de MSFT/SK y su auditoría. Los tickers sólo definen la muestra de prueba, los ejemplos y los resultados archivados.

## Aceptación de datos reales

“SEC disponible/validado” cuenta años con hechos oficiales y, para la validación de cobertura, los cuatro campos ingresos, neto, EPS diluido y acciones diluidas. **No equivale a auditar todas sus cuentas**. Los primeros años de Alphabet no tienen acciones diluidas SEC suficientes; no se imputan. En SPCX hay EPS redondeado a cero y diferencias de atribución: que se haya extraído un valor no acredita una valoración utilizable.

TTM muestra disponibilidad de siete flujos: ingresos, EBIT, neto, EPS, OCF, CAPEX y FCF. El porcentaje cuenta valores disponibles en trece métricas: esos siete, acciones diluidas, deuda, efectivo, ROIC FY aproximado, PER TTM y EV/EBITDA. Un EV/EBITDA sin D&A pura/puente EV no entra como disponible. Los flujos negativos válidos sí cuentan como datos; las diferencias materiales no. Una caída de cobertura puede ser la detección correcta de una discrepancia, no una pérdida de extracción.

| Ticker | SEC FY (disponibles/validados) | Último cierre | Q consecutivos / TTM flujos | Métricas % antes→después | PER historia n | Pares economía/TTM/NTM | Objetivos EPS antes→después | Críticas/ausencias / advertencias |
|---|---|---|---|---|---|---|---|---|
| MSFT | 2017–2026 (10/10) | 2026-09-30 | 5 / 7/7 | 92.3→92.3 | 10 | 1/0/0 | 6→6 | 0 / 1 |
| NVDA | 2017–2026 (10/10) | 2026-07-26 | 5 / 7/7 | 92.3→92.3 | 10 | 2/0/0 | 2→6 | 0 / 3 |
| AMZN | 2016–2025 (10/10) | 2026-09-30 | 6 / 5/7 | 46.2→76.9 | 9 | 0/0/0 | 0→6 | 0 / 1 |
| NFLX | 2016–2025 (10/10) | 2026-09-30 | 5 / 7/7 | 92.3→92.3 | 10 | 0/0/0 | 6→6 | 0 / 1 |
| META | 2016–2025 (10/10) | 2026-09-30 | 7 / 7/7 | 84.6→84.6 | 10 | 0/0/0 | 0→6 | 0 / 2 |
| GOOGL | 2016–2025 (10/4) | 2026-09-30 | 7 / 7/7 | 92.3→92.3 | 4 | 0/0/0 | 0→6 | 0 / 2 |
| GOOG | 2016–2025 (10/4) | 2026-09-30 | 7 / 7/7 | 92.3→92.3 | 4 | 0/0/0 | 0→6 | 0 / 2 |
| MU | 2017–2026 (10/10) | 2026-09-03 | 5 / 7/7 | 84.6→84.6 | 9 | 5/0/0 | 0→6 | 0 / 3 |
| SNDK | 2023–2026 (4/4) | 2026-10-02 | 7 / 6/7 | 92.3→84.6 | 1 | 2/0/0 | 0→0 | 5 / 6 |
| SPCX | 2023–2025 (3/3) | 2026-09-30 | 6 / 5/7 | 76.9→61.5 | 0 | 0/0/0 | 0→0 | 6 / 5 |
| JNJ | 2016–2025 (10/10) | 2026-09-27 | 7 / 5/7 | 84.6→69.2 | 10 | 0/0/0 | 6→6 | 0 / 2 |
| JPM | 2016–2025 (10/10) | 2026-09-30 | 5 / 4/7 | 61.5→61.5 | 10 | 6/1/0 | 6→6 | 0 / 2 |
| 000660.KS | Sin SEC (Yahoo/IR) | 2026-09-30 | 7 / 4/7 | 61.5→61.5 | 3 | 6/0/0 | 6→6 | 0 / 5 |

Los motivos completos y cada métrica están en [aceptacion.json](aceptacion.json); [comparacion.csv](comparacion.csv) contiene los valores y las incidencias por ticker. El registro de comparables conserva todos los candidatos y motivos. Sólo JPM tiene un PER TTM admisible en esta descarga; ninguna empresa alcanza tres PER homogéneos, ni hay una cohorte NTM verificable suficiente. ORCL frente a MSFT y AMD/INTC frente a NVDA tienen ventanas TTM distintas; no se relaja la ventana para completar el grupo. Los pares de MU de otras bolsas carecen del marco/CIK exacto exigido por esta ruta SEC y no se renombran como GAAP homogéneo.

## Precios de los escenarios Base y coherencia económica

Son **estimaciones mecánicas con confianza Baja**, no objetivos de consenso ni recomendaciones garantizadas. Cotizaciones y estados son los devueltos por las fuentes en la fecha de corte. KRW no se agrega con USD.

| Ticker | Moneda | Cotización observada | Base 1 año antes→después | Base 3 años antes→después |
|---|---|---|---|---|
| MSFT | USD | 528.40 | 696.84→696.84 | 940.68→940.68 |
| NVDA | USD | 164.55 | —→619.72 | —→1,268.89 |
| AMZN | USD | 270.30 | —→199.00 | —→237.93 |
| NFLX | USD | 63.60 | 93.86→93.86 | 121.78→121.78 |
| META | USD | 625.68 | —→924.33 | —→1,370.30 |
| GOOGL | USD | 298.40 | —→285.63 | —→377.74 |
| GOOG | USD | 295.35 | —→287.77 | —→380.56 |
| MU | USD | 790.54 | —→1,590.10 | —→964.04 |
| SNDK | USD | 945.78 | —→— | —→— |
| SPCX | USD | 143.41 | —→— | —→— |
| JNJ | USD | 283.68 | 234.23→234.23 | 282.74→282.74 |
| JPM | USD | 345.50 | 290.93→290.93 | 383.68→383.68 |
| 000660.KS | KRW | 1,254,000.00 | 976,869.50→3,519,301.95 | 1,602,159.41→2,326,328.42 |

MSFT, NFLX, JPM y JNJ mantienen sus precios principales, salvo redondeo. GOOG/GOOGL/META recuperan el método por corregir la dependencia de capitalización; AMZN por completar flujos oficiales; MU por conciliar fechas y normalizar el ciclo. NVDA recupera escenarios por usar tasas anuales medianas observadas en lugar de extrapolar un CAGR excepcional fuera de rango.

La mayor sensibilidad es SK: el margen inicial TTM es **74,50%** y converge al **25,36%** histórico; la tasa de crecimiento mecánica es **46,76%**, basada en sólo cuatro FY disponibles. En MU el margen converge del **74,59% al 26,14%**, y el crecimiento del **48,85% al 29,25%**: el precio Base a tres años puede quedar por debajo del de un año. NVDA parte de crecimiento **65,47%** y converge al **52,73%**, todavía exigente. Estas hipótesis son visibles y editables; requieren revisión económica. No se cambian para acercarse a la cotización. Un horizonte mayor no garantiza más precio.

[aislamiento_codigo.json](aislamiento_codigo.json) aplica el motor nuevo a las mismas trece capturas anteriores, sin red. Aísla los efectos de clases/ámbitos, splits y normalización. AMZN y MU sólo recuperan sus valoraciones completas después de la corrección de captura SEC; el replay no inventa los datos ausentes ni descarta una alerta de actualidad anterior sin evidencia.

## Inconsistencias y límites que permanecen

- **SNDK:** EBIT SEC/Yahoo de Q3 FY2026: 4.111 frente a 4.164 M USD (>1%); ese flujo queda bloqueado. Falta un PER histórico suficiente (una observación) o tres pares homogéneos y falta crecimiento automático comparable tras la separación. Se conservan ingresos, neto, EPS y caja válidos. No se mezclan sin advertencia cifras pre/post separación.
- **SPCX:** tres FY oficiales y breve cotización desde 2026; cero PER históricos. Pérdidas, atribución a acciones comunes y fiscalidad no interpretable limitan EPS/PER. En 2024 el prospecto diferencia neto consolidado 791 M USD de neto atribuible diluido 21 M USD y EPS redondeado a cero. También hay divergencias SEC–Yahoo por trimestre. Un PER manual justificado existe como opción general, pero no elimina estos controles ni genera un precio por sí solo.
- **JNJ:** CAPEX de Q3 2026: Yahoo 2.357 M USD frente a SEC reconstruido 1.362 M USD; FCF/contraste se omiten en esa ventana. Los seis precios principales permanecen disponibles, sin forzar CAPEX para recuperarlos.
- **AMZN/META:** inversión intensa y conversión de FCF no representativa; no se extrapola FCF ni se invalida EPS. **SK** sigue sin CAPEX/D&A Q3 completamente conciliados para FCF/DCF. Su histórico anual es fallback Yahoo con contraste oficial IR, no se presenta como diez años SEC.
- **Financieras/REIT:** JPM usa PBT directo y mantiene revisión de capital regulatorio; no recibe un FCFF genérico ni señal automática de compra. REIT exige FFO/AFFO/NAV. EPS negativo requiere hipótesis explícita de recuperación y sus propios datos suficientes.
- El extractor de prospectos cubre tablas anuales consolidadas con cabecera y escala reconocibles; otros formatos siguen como ausencia explícita/fallback auditado. No se promete cobertura universal de todos los documentos EDGAR. El enlace y hash permiten revisar el documento concreto.

## Fórmulas, métodos opcionales y verificación

Para cada año se compone el crecimiento aplicado; crecimiento y margen interpolan linealmente desde año 1 hasta año 3, y conservan el extremo en año 4 para PER NTM. Se calcula EBIT (o PBT directo), no operativo, PBT, impuesto sobre beneficio positivo, beneficio común normalizado, acciones diluidas y EPS. PER TTM aplica EPS del año del horizonte; NTM aplica el siguiente. El precio es EPS × PER × FX × acciones ordinarias por título/ADR documentado. El valor razonable de referencia es el Base a un año descontado al retorno exigido. No se promedian métodos.

`verificar_generalizacion.py` valida **132 trayectorias escenario/año**, las identidades de ingresos, EBIT/PBT, impuestos, EPS/acciones, EPS×PER y FCF=OCF−CAPEX, sin fijar cotizaciones como resultados esperados. [aceptacion.json](aceptacion.json) registra los controles independientes. Las pruebas sintéticas comprueban también la composición anual de ventas, el efecto de cada extremo editable y la ausencia de dependencia de la cotización para generar supuestos.

Se ejecutaron adicionalmente los opcionales sobre las capturas MSFT y SK, sin nuevas descargas: MSFT conserva seis precios EPS y nueve sensibilidades DCF; EV/EBITDA sigue bloqueado. SK conserva seis precios EPS y DCF/EV bloqueados por sus requisitos propios. El contraste P/FCF válido se registra a horizonte cero, nunca como precio futuro.

**107 pruebas unitarias/integración**, más las tres suites originales, pasan localmente y en [GitHub Actions 43258694679](https://github.com/AlvaroAlonsoLarre/valoracion-bursatil/actions/runs/43258694679). El job de PR ejecuta sólo pruebas; los jobs con red se omiten deliberadamente. La matriz completa de trece es manual o semanal; la ejecución aquí archivada se hizo con red autorizada en este entorno. Salida 2 no oculta fallos técnicos: se conserva el diagnóstico financiero; salida 1 sí falla el job.

Chromium verifica las seis pestañas en **1440×1200 y 390×844**, sin excepciones de la aplicación ni desbordamiento horizontal de página en móvil. [Capturas y comprobantes](interfaz/) muestran Resumen y Valoración. Se descargan Excel, resultados JSON y captura; sus valores coinciden con el replay. Al editar retorno exigido de 10% a 20%, el valor descontado cambia y los precios futuros permanecen iguales. El hash de la captura exportada coincide con el JSON de resultados. Las tablas anchas conservan desplazamiento interno en móvil.

## Artefactos y reproducción

Los ZIP [antes](ejecuciones_antes.zip), [después 1](ejecuciones_despues_1.zip) y [después 2 y pruebas complementarias](ejecuciones_despues_2.zip) conservan Excel, JSON de resultados, capturas JSON y logs de los trece tickers **antes y después**, los dos replays opcionales, el ticker desconocido, las exportaciones del navegador y el prospecto SEC real de SPCX. [manifest_artefactos.json](manifest_artefactos.json) enumera **148 archivos**, tamaño y SHA-256, comprobados tras volver a leer los tres ZIP. Los hashes del prospecto descargado y del documento auditado coinciden (`17a62560…c7481d`). `SHA256SUMS` protege los artefactos del informe.

```bash
unzip ejecuciones_antes.zip -d evidencia
unzip ejecuciones_despues_1.zip -d evidencia
unzip ejecuciones_despues_2.zip -d evidencia
python verificar_generalizacion.py --before evidencia/before --after evidencia/after --output comprobacion
python ejecutar_analisis.py --snapshot evidencia/after/MSFT/MSFT_inputs.json --outdir replay
python -m pytest -q tests
```

Para la matriz con red, usar `workflow_dispatch` con ticker vacío; para una empresa nueva indicar su ticker. No hace falta repetir trece descargas para editar supuestos o revisar un cambio pequeño. Las cifras y controles completos permanecen en los ZIP; los informes anteriores se conservan como evidencia de sus versiones, sin sobrescribirlos.
