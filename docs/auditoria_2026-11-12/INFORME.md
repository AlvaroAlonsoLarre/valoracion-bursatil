# Continuación de la auditoría: 12 de noviembre de 2026

La PR #1 incorpora ahora D&A consolidada pura de Microsoft y el trimestre oficial Q3 de SK hynix. **MSFT recupera el DCF condicional; sus múltiplos y las valoraciones de SK siguen bloqueados por carencias concretas de datos.** No se eliminaron controles ni se ajustaron parámetros para acercar precios a la cotización. La PR permanece abierta y no se fusionó a `main`.

## Evidencia de ejecución y comparación

Se descargaron y revisaron los tres artefactos de [Actions 43086248781](https://github.com/AlvaroAlonsoLarre/valoracion-bursatil/actions/runs/43086248781), SHA `35db5f80fa3f7d0c5f6eb81646ed7ad4bfc06e97`. Sus ZIP se recalcularon con SHA-256 y coinciden con los digest de GitHub; sus identificadores, tamaños y hashes están en `artefactos_43086248781.json`. Se leyeron JSON, entradas, Excel y logs. Las pruebas y la cobertura habían pasado, pero ambos análisis devolvían 2.

La ejecución nueva verificable es [Actions 43189252381](https://github.com/AlvaroAlonsoLarre/valoracion-bursatil/actions/runs/43189252381), SHA `e424b193fef7b7d24b7b3bcc190ba76b48fb7a03`. Pruebas, MSFT y cobertura pasan; SK devuelve 2 y conserva los artefactos. El estado global es `failure` por ese bloqueo financiero, no por omitir pruebas. Se descargaron también los tres ZIP nuevos, se verificaron sus digest y se archivaron sus referencias en `artefactos_43189252381.json`.

Los archivos `inputs/*_before.json` proceden de la ejecución anterior y `inputs/*_after.json` de esta ejecución nueva de Actions. `resultados/` conserva diagnósticos compactos de ambos y de las ejecuciones locales. No se incorporan credenciales a estos archivos.

| Indicador | MSFT anterior → actual | SK anterior → actual |
|---|---|---|
| Último trimestre operativo | 30/09/2026 → 30/09/2026 | 30/06/2026 → **30/09/2026** |
| Objetivos fundamentales disponibles | 0 → **9 DCF condicionales** | 0 → 0 |
| Bloqueos globales de entradas | 0 → 0 | 2 → 3 |
| Estado financiero | BLOQUEO → **PARCIAL** | BLOQUEO → BLOQUEO |
| Exit code | 2 → **0** | 2 → 2 |
| Candidatos registrados | 156 → 156 | 150 → 149 |
| Comparables económicos elegibles | 1 → 1 | 7 → 7 |
| Emisores válidos por múltiplo NTM | 0 → 0 | 0 → 0 |
| Cobertura de tickers/SHA | Completa → Completa | Completa → Completa |

Los tres bloqueos actuales de SK son CAPEX, D&A y la comprobación global que depende de ambos. No son tres defectos económicos independientes. El bloqueo anterior por trimestre desactualizado desaparece porque se incorpora un periodo oficial completo para las métricas que sí se publican. Los candidatos no equivalen a descargas válidas ni a múltiplos utilizables; el descubrimiento dinámico puede variar entre consultas.

También se ejecutaron ambos tickers localmente con red autorizada a las 09:06:34 UTC, sobre el código financiero `e17c2ff5f63eec640dd3dd567437e65f05d0f4ce`: MSFT devuelve 0/PARCIAL y SK 2/BLOQUEO. El commit posterior `e424b193…` identifica las solicitudes HTTP con el nombre real del software; no cambia fórmulas ni inventa un contacto SEC.

## Comparación por corrección con entradas de mercado fijas

`comparacion_precios_entradas_fijas.csv` y `comparacion_bloqueos_entradas_fijas.csv` mantienen el precio, acciones, moneda, fecha, peers y demás entradas de la ejecución 43086248781. Incorporan por etapas únicamente los datos oficiales y el diagnóstico. Los snapshots `*_after_fixed_inputs.json` permiten reproducir la comparación final sin red. No se atribuyen a una fórmula las diferencias de cotización entre ejecuciones reales.

DCF base de MSFT en USD; las cifras intermedias son sensibilidades, no objetivos validados:

| Etapa | Valor presente | Futuro 1 año | Futuro 3 años |
|---|---:|---:|---:|
| Anterior, D&A agregada sin reconciliar | N/D | N/D | N/D |
| Componentes Inline XBRL; Q2 derivado de acumulados redondeados | 156,339472 | 162,805528 | 173,968309 |
| CompanyFacts; preferencia por Q2 directamente publicado | 156,578321 | 163,067813 | 174,280877 |
| Diagnóstico de definiciones de comparables | 156,578321 | 163,067813 | 174,280877 |

La identificación HTTP no altera valores cuando la respuesta es la misma; permite que Actions reciba la fuente oficial. En la ejecución real nueva, el DCF base es 156,577258 USD presente, 163,066719 USD a un año y 174,279721 USD a tres. La pequeña diferencia frente a la comparación fija corresponde a otras entradas consultadas, no a un ajuste del modelo al precio.

No se cambian CAPEX/ventas, crecimiento terminal, primas de riesgo, bandas ni umbrales económicos para obtener estas cifras. SK conserva todos sus precios en N/D en cada etapa. Se mantienen el mínimo de tres emisores y las exigencias GAAP/NTM/perímetro por múltiplo.

## Microsoft: D&A pura y precisión de la conciliación

El extractor genérico une `us-gaap:Depreciation` y `us-gaap:AmortizationOfIntangibleAssets` con el mismo emisor, moneda, inicio/fin y accession. CompanyFacts se consulta con fecha de presentación no posterior a la valoración; no se mezclan dos filings ni se toman cifras futuras. Inline XBRL ofrece una ruta alternativa y descarta contextos segmentados y unidades incompatibles.

Fuentes oficiales:

- [CompanyFacts de Microsoft](https://data.sec.gov/api/xbrl/companyfacts/CIK0000789019.json).
- [10-K FY2026, accession 0001193125-26-323660](https://www.sec.gov/Archives/edgar/data/789019/000119312526323660/msft-20260630.htm).
- [10-Q marzo de 2026, accession 0001193125-26-191507](https://www.sec.gov/Archives/edgar/data/789019/000119312526191507/msft-20260331.htm).
- [10-Q septiembre de 2026, copia del emisor](https://microsoft.gcs-web.com/node/35416/html).

FY2026: depreciación de PP&E 34,3 + amortización de intangibles 4,7 = **39,0 mil millones USD**. La amortización de activos finance-lease ya incluida en PP&E no se suma de nuevo. El agregado anterior de 38,534 se conserva aparte y su residual respecto a los componentes es −0,466; no se presenta ese residual como una partida «otros» identificada.

La serie trimestral seleccionada es 8,6 / **9,1** / 10,1 / 11,3 / 12,1 mil millones, de septiembre de 2025 a septiembre de 2026. Q2 de 9,1 procede directamente del filing 0001193125-26-027207. Sin ese dato, las notas acumuladas redondeadas daban un residual de 9,0. Se prefiere el trimestre publicado y no se modifica para forzar una igualdad anual.

Los cuatro trimestres de FY2026 suman 39,1 frente a 39,0 anual: residual de publicación/redondeo de 0,1 (0,2564%), dentro de la tolerancia <1% existente. Se conserva y se explica; no se declara igualdad exacta ni verificación independiente adicional por una identidad derivada. El TTM seleccionado es **42,6 mil millones**. El puente FY + Q1 actual − Q1 previo daría 42,5 con los importes anuales redondeados; esta diferencia también permanece visible. Los valores heredan la precisión de las notas, sin decimales económicos adicionales inventados.

`Fuentes fundamentales` registra conceptos, periodos, importes anteriores/nuevos, derivaciones y fuente; el snapshot conserva hashes de las respuestas oficiales. `Anuales proveedor` y `Trimestres proveedor` conservan la base anterior. `Conciliacion TTM` separa cobertura aritmética y contraste FY por flujo. Los importes históricos de las hojas originales de proveedor no deben confundirse con la serie seleccionada tras enriquecimiento.

La extracción no valida por sí sola WACC, reinversión terminal, caja distribuible, SBC o el calendario completo de leases. Se conserva el estado **CONDICIONAL** de cada DCF y `publicable=false`. La consulta de actualidad SEC sin contacto sigue `NO_VERIFICADO`; recibir CompanyFacts no se convierte artificialmente en verificación de ausencia de publicaciones posteriores.

## Comparables: definición homogénea aún pendiente

`forwardPE` no documenta por sí solo GAAP frente a ajustado ni FY1 frente a NTM. `enterpriseToEbitda` tampoco acredita EBITDA NTM y una deuda consistente con los flujos proyectados. No se renombraron esos campos ni se admitieron múltiplos LTM como si fueran NTM.

La hoja y JSON `Comparables requisitos` muestran por candidato y método el periodo, base, perímetro, fuente/fecha de la definición y requisitos pendientes. En esta ejecución hay **cero emisores con evidencia completa por múltiplo**, además de insuficiente cobertura económica válida para MSFT. Se mantienen N/D tanto PER como EV/EBITDA. No se incorporó una cifra de forecast desde un comunicado no-GAAP como si fuera GAAP ni se sustituyó por el múltiplo propio.

**Esta parte del bloqueo no está resuelta.** Para completarla hacen falta al menos tres emisores independientes con forecasts y definiciones documentados, fechas y horizontes comparables y un puente de deuda/EBITDA compatible. El diagnóstico ahora identifica esos campos concretamente; no simula que la ausencia se haya solventado.

## SK hynix: Q3 oficial y TTM por flujo

Se incorpora la [presentación oficial FY2026 Q3 del 28/10/2026](https://mis-prod-koce-homepage-cdn-01-blob-ep.azureedge.net/web/attach/21435786328187801.pdf), con contraste del [comunicado oficial](https://news.skhynix.com/en/q3-2026-business-results/). Se verifican emisor, periodo, orden de columnas, K-IFRS consolidado y unidad KRW billion (×10^9). El documento declara que la revisión no ha finalizado; se conserva **PRELIMINAR_NO_REVISADO**.

La extracción obtiene los valores del documento, no de constantes numéricas del catálogo. Las páginas 16, 19 y 20 contienen flujos, balance e ingresos. Q3 publicado, en miles de millones KRW: ventas 104.615, EBIT 83.334, beneficio 39.776, OCF 54.781, compras de PP&E 12.670, deuda financiera 15.800 y caja/instrumentos/inversiones CP 114.460. EPS diluido 54.454 KRW/acción; no se multiplica por 10^9. Deuda neta = 15.800 − 114.460 = −98.660. La caja ampliada IR se etiqueta como tal, sin presentarla como caja estricta ni como disponibilidad distribuible verificada.

La suma trimestral hasta el 30/09/2026 da ingresos TTM 269,336686 billones KRW, EBIT 200,656465 y OCF 167,385237. Son cuatro periodos presentes con fuente identificada; la ausencia de cuatro trimestres FY completos y comparables impide afirmar una conciliación FY independiente para SK. `Conciliacion TTM` lo indica expresamente.

**Dos requisitos siguen pendientes:**

1. CAPEX total: la presentación revela adquisiciones de PP&E, pero no todo el CAPEX de intangibles. El campo de Yahoo usado por el modelo incluye ambos: por ejemplo, Q2 2026 desglosa aproximadamente 10,671 billones de PP&E y 0,457 de intangibles, frente a CAPEX total 11,129 (cifras redondeadas). No se usa PP&E Q3 como sustituto de todo el CAPEX ni se rellena lo ausente con cero o un ratio FY.
2. D&A homogénea: EBITDA−EBIT de la presentación implica D&A operativa 4.341, mientras el cash flow publica 4.335, con nota que incluye activos ociosos/no operativos. Se guardan ambas definiciones y no se mezclan automáticamente con la serie de cash flow de Yahoo para autorizar FCFF/EBITDA.

Los flujos afectados y sus derivados quedan invalidados; los datos de ventas/EBIT/OCF sí se conservan. La invalidación se propaga a la base TTM y evita el fallback anual que produciría un precio aparentemente completo. Falta un estado/cash-flow consolidado con CAPEX total y el puente de D&A, y sigue pendiente el importe reconciliado de los extraordinarios Kioxia. No se inventa un 6-K US-GAAP ni cobertura SEC equivalente.

## Pruebas y reproducibilidad

**36 pruebas locales aprobadas**, frente a 25 anteriormente; siguen pasando `autoprueba_modelo.py`, `prueba_comparables_automaticos.py` y `test_v5.py`. Los casos nuevos cubren:

- Componentes D&A completos, moneda/emisor/contexto, no doble conteo de finance-lease D&A y diferencias entre acumulados.
- CompanyFacts con mismo accession, ausencia de un componente y rechazo de presentaciones futuras.
- Columnas/periodos/unidades PDF, EPS por acción y separación de las dos definiciones de D&A.
- CAPEX ausente que no vuelve a FY; fuente caída que no se presenta verificada; ticker sin configuración que conserva su comportamiento.
- Definiciones de peers sin documentación, conciliación por flujo y regresión con ambos snapshots reales.
- Reproducción independiente de Gordon/EV/equity para los tres escenarios y horizontes 0/1/3 de MSFT, sin omitir el bloqueo de los múltiplos.

Se ejecutó el flujo completo con red tanto localmente como en Actions. Los intentos 43187501948 y 43188535177 conservaron errores 403 al solicitar fuentes sin identificación de aplicación y MSFT permaneció bloqueada correctamente; no se presentaron como éxitos. La ruta oficial CompanyFacts y un User-Agent que identifica realmente el software, sin un correo inventado, permiten el resultado comprobado de 43189252381. Si existe un contacto SEC configurado se utiliza; no se crea ni solicita un secreto para fabricar verificación.

Los snapshots se reproducen sin red:

```bash
python ejecutar_analisis.py --snapshot docs/auditoria_2026-11-12/inputs/MSFT_after.json --outdir Resultados/replay_MSFT
python ejecutar_analisis.py --snapshot docs/auditoria_2026-11-12/inputs/000660.KS_after.json --outdir Resultados/replay_SK
```

La primera orden devuelve 0/PARCIAL y la segunda 2/BLOQUEO. Se verifican precios y tablas con tolerancia relativa 1e-12 por el paso por Excel; se normaliza únicamente la representación vacío/null de celdas sin información. No se normalizan discrepancias numéricas. `sha256.json` permite comprobar los archivos de evidencia.

El catálogo de fuentes contiene URLs, emisor y selectores, no cifras objetivo ni excepciones para admitir datos ausentes. Los extractores y reglas por flujo son genéricos; un ticker sin cobertura oficial adicional sigue usando su ruta anterior. No se modificaron los umbrales de comparabilidad, los mínimos por múltiplo ni los controles de publicación. La PR mantiene los límites de información anteriores que no se han resuelto y no se fusiona automáticamente.
