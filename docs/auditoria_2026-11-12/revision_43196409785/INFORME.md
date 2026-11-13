# Revisión de 43196409785: fuentes, comparables y sensibilidad DCF

Fecha de corte: 12/11/2026. PR [#1](https://github.com/AlvaroAlonsoLarre/valoracion-bursatil/pull/1), rama `fix/auditoria-msft-sk-hynix`. Código ejecutado: `01e056fb3f1f636b8d01e1c99c91219b18d6b2e3`. No se fusiona a `main` ni se activa auto-merge.

Se refuerzan la evidencia y los controles, pero **no se han obtenido datos oficiales suficientes para cerrar CAPEX/D&A de SK hynix ni tres comparables NTM homogéneos**. Microsoft conserva nueve DCF condicionales, con limitaciones de supuestos explícitas. No se ajustan parámetros para aproximar precios a la cotización.

## Ejecuciones verificadas

Se revisó [43196409785](https://github.com/AlvaroAlonsoLarre/valoracion-bursatil/actions/runs/43196409785), código `25d358ce47e2ecedaed2065c7c0952e57bd88d72`, incluidos sus JSON, snapshots, Excel, logs y cobertura. Se ejecutó el código nuevo con red autorizada localmente a las 10:49:27 UTC y en [Actions 43203723794](https://github.com/AlvaroAlonsoLarre/valoracion-bursatil/actions/runs/43203723794). Los tres ZIP de cada ejecución se descargaron y sus tamaños y SHA-256 coinciden con los metadatos de GitHub: [artefactos.json](artefactos.json). Los ZIP y Excel completos siguen disponibles en Actions; se conservan snapshots y diagnósticos compactos en esta carpeta.

En la nueva ejecución pasan **55 pruebas**, las tres suites originales, el análisis MSFT y el manifiesto de cobertura. SK devuelve **2/BLOQUEO**, conserva los artefactos y provoca el estado global `failure`. No es un error técnico del motor. Evidencia: [pruebas](pruebas_actions.txt), [cobertura](cobertura_after.json). La ejecución intermedia 43203066792, código `f88aaf4…`, también ejecutó ambos tickers y 53 pruebas; la versión final añade el contraste oficial del tipo sin riesgo y corrige la presentación de periodos del SDK.

| Indicador | MSFT antes → después | 000660.KS antes → después |
|---|---:|---:|
| Pruebas de pytest del código | 36 → 55 | 36 → 55 |
| Objetivos fundamentales disponibles | 9 → 9 | 0 → 0 |
| Bloqueos globales de entrada | 0 → 0 | 3 → 3 |
| Estado / exit code | PARCIAL / 0 → igual | BLOQUEO / 2 → igual |
| Candidatos registrados en línea | 156 → 156 | 149 → 149 |
| Comparables económicos elegibles | 1 → 1 | 7 → 7 |
| Emisores con evidencia admisible PER / EV | 0 / 0 → 0 / 0 | 0 / 0 → 0 / 0 |
| Consultas adicionales de forecasts conservadas | 0 → 10 | 0 → 10 |
| Casos DCF de auditoría × horizontes | 0 → 27 | 0 → 27, todos N/D |
| Cobertura de ambos tickers y SHA | Completa → completa | Completa → completa |

[Comparación completa](comparacion_ejecuciones.csv). Los tres bloqueos de SK corresponden a CAPEX, D&A y su integridad conjunta; no representan tres carencias independientes. Los métodos por múltiplos N/D de MSFT son restricciones por método, distintas de los bloqueos globales de entradas. Las nuevas consultas de fuentes aumentan la trazabilidad, **no la cobertura de valoraciones admisibles**.

## 1. SK hynix: búsqueda oficial y conciliación sin sustituciones

`filing_review.py` consulta por configuración el índice SEC del emisor y examina como máximo ocho documentos 6-K/20-F, presentados entre el cierre buscado y la fecha de valoración. Comprueba el CIK y conserva accession, fecha, URL y hash del índice/documento. Un candidato con texto de cash flow no se admite automáticamente: necesita extractor, unidades, periodo y conciliación. Un 6-K extranjero no equivale a cobertura CompanyFacts US-GAAP. También se registra la consulta al índice público DART. La falta de configuración de otro ticker no incorpora reglas de SK.

Revisión acotada efectuada:

- [Submissions oficial CIK 2120882](https://data.sec.gov/submissions/CIK0002120882.json): ocho 6-K recientes revisados, de 26 a 29 de octubre. Los accessions y hashes están en [SK_filings.csv](SK_filings.csv). Ninguno de esos documentos incluye el estado consolidado de cash flow requerido.
- [6-K de resultados 0001193125-26-434994](https://www.sec.gov/Archives/edgar/data/2120882/000119312526434994/d162547d6k.htm): resultados Q3 y acumulados preliminares; no desglosa el CAPEX total ni concilia ambas D&A. Los otros siete documentos tratan retribución al accionista, autocartera y aclaraciones corporativas. Se revisaron además los otros dos 6-K del índice desde el cierre: 0001193125-26-429184 (23/10, aclaración Solidigm) y 0001193125-26-420934 (14/10, anuncio de conferencia); tampoco incluyen el cash flow. Véanse [fuentes adicionales](SK_filings_adicionales.json). La automatización conserva el límite de ocho; la revisión adicional de esta auditoría no se confunde con su cobertura automática.
- [CompanyFacts del mismo CIK](https://data.sec.gov/api/xbrl/companyfacts/CIK0002120882.json): la respuesta observada contiene sólo taxonomía `ffd`, sin conceptos financieros que permitan completar estos flujos. Se conserva la respuesta, no se fabrica una serie XBRL.
- [Índice público DART del emisor](https://dart.fss.or.kr/navi/searchNavi.do?naviCode=C001&naviCrpCik=00164779&naviCrpNm=SK%ED%95%98%EC%9D%B4%EB%8B%89%EC%8A%A4): el índice observado muestra el semestre 2026 y receipt `20260814003509`. Esto no prueba ausencia global de cualquier otro documento Q3.
- El enlace de estados financieros de IR lleva a la herramienta Euroland; el acceso directo devolvió HTTP 599 y no produjo un estado utilizable. No se presenta esa consulta como verificación financiera.

La [presentación oficial Q3 del 28/10](https://mis-prod-koce-homepage-cdn-01-blob-ep.azureedge.net/web/attach/21435786328187801.pdf) sigue siendo la fuente consolidada disponible utilizada. Mantiene su estado preliminar. Para Q3, en KRW billion:

| Componente | Observado | Tratamiento |
|---|---:|---|
| Compras PP&E | 12.670 | Componente, no CAPEX total |
| Compras intangibles | N/D | No se rellena con cero |
| CAPEX total | N/D | No se deduce de inversión neta ni de variación del balance |
| D&A cash flow | 4.335 | Serie separada, nota incluye activos ociosos/no operativos |
| D&A operativa = EBITDA − EBIT | 4.341 | Serie separada, no se mezcla con cash flow |
| Diferencia CFO − operativa | −6 | Diferencia observada; no partida identificada ni «ajuste» |

El nuevo registro [Componentes CAPEX/D&A](SK_componentes.csv) muestra cada trimestre, los componentes observados y un residual sólo cuando los tres importes existen. El mismo diagnóstico funciona para cualquier emisor; no supone que CAPEX PP&E equivale a total ni que la falta de intangibles implica cero. Para MSFT también deja visible que la desagregación de intangibles no se ha acreditado en esa tabla; no modifica el CAPEX ya seleccionado por el modelo.

Ingresos TTM **269,336686 billones KRW**, EBIT **200,656465** y OCF **167,385237** se conservan. CAPEX y D&A TTM continúan invalidados; no vuelven a una mediana anual ni se desbloquean mediante shocks. Faltan el cash-flow consolidado Q3/9M con adquisiciones de intangibles y el puente entre D&A operativa y de cash flow, enlazados al semestre y al FY del mismo perímetro. Tampoco se ha resuelto la cuantificación del extraordinario Kioxia. **La prioridad de completar estos datos permanece abierta por falta de evidencia utilizable**, no se declara resuelta a partir de una búsqueda acotada.

## 2. Comparables automáticos: datos observados y prueba de homogeneidad

Antes se rechazaban las etiquetas Yahoo no documentadas, pero una fila etiquetada NTM/GAAP podía superar el filtro sin reconstruir el múltiplo. Ahora `multiple_evidence.py` exige evidencia estructurada y comprueba la identidad financiera. `Comparables requisitos` y el filtro de admisión usan el mismo validador; cambiar etiquetas en una fila no crea cobertura.

La captura automática consulta `get_earnings_estimate` para hasta diez candidatos por prioridad de origen y conserva el resultado del SDK, URL de referencia, fecha efectiva de consulta y SHA-256 del JSON canónico. Expone EPS FY0/FY1, periodos realmente devueltos y metodología publicada. El hash es del **resultado del SDK**, no se afirma que sea un digest de la respuesta HTTP original ni una autenticación independiente de la semántica del proveedor. Los payloads están íntegros en los snapshots.

Resultado: diez respuestas con forecasts para MSFT y ocho para SK; las otras dos consultas SK no aportaron estimaciones. Las 18 respuestas con metodología observada dicen **`normalized`**. Los periodos son `0y`, `+1y`, `0q`, `+1q`: **FY1 no acredita NTM**. Ejemplos de EPS FY1 de proveedor: ADBE 27,40718 USD, ORCL 11,05881 USD, MU 207,76048 USD, Samsung 77.323,65 KRW. Son cifras de proveedor observadas, no EPS GAAP/NTM adoptados. Fuentes por candidato: [MSFT](MSFT_fuentes_comparables.csv) y [SK](000660.KS_fuentes_comparables.csv). El límite de diez consultas es un presupuesto operativo; no es revisión exhaustiva de todos los candidatos descubiertos.

Para admitir PER se exige precio/EPS diluido ordinario, fechas no futuras, quote ≤7 días, estimación ≤30 días, ventana NTM exacta desde el día siguiente a la valoración hasta un año después, marco contable explícito compatible con el objetivo, divisas/FX documentados y capitalización conciliada con precio × acciones. Se requiere documentación de definiciones y perímetro consolidado, no una etiqueta genérica inferida. Sin base contable documentada en el objetivo, no se presume US-GAAP por mercado de cotización.

Para EV/EBITDA se reconstruye `(capitalización + deuda financiera − caja/inversiones líquidas) / EBITDA NTM` en moneda homogénea, con balance vigente, exclusión documentada de leases y `EBITDA = EBIT + D&A operativa pura`. Minoritarios y preferentes deben estar explícitamente documentados como cero para este puente: si existen, falta un puente compatible y el método se rechaza. No se supone cero cuando falta el campo. Se verifica que el ratio reconstruido y el publicado difieran menos del 1 %. Se conservan mínimo tres emisores independientes, puntuaciones económicas, límites de múltiplos, control de outliers y cohortes homogéneas de ventana, marco contable y perímetro. ADR sin reconciliar y EBITDA LTM quedan fuera.

Las pruebas positivas contienen evidencia **sintética identificada**, nunca forecasts atribuidos a fuentes reales. En producción las bases desconocidas permanecen `UNKNOWN`; las URL/hash documentan procedencia e integridad, sin convertir afirmaciones no contrastadas en definiciones válidas. **Ambos múltiplos siguen N/D**: se ha mejorado la captura y cerrado una admisión insuficientemente comprobada; no se ha conseguido un consenso documental utilizable.

## 3. Microsoft: contraste de supuestos y sensibilidad sin calibración

El cálculo base sigue usando TTM, D&A pura 42,6 mil millones USD y CAPEX seleccionado sin modificaciones. Crecimiento inicial de ingresos 15,3011 %, margen EBIT 46,6597 %, fiscalidad normalizada 18,2313 %, CAPEX/ventas 35,9690 %, D&A/ventas 11,7069 %, circulante 1 % del incremento de ingresos, pagos a accionistas 15,2595 % de ventas y acciones constantes. Son hipótesis mecánicas; una fórmula correcta no acredita su plausibilidad prospectiva.

WACC base **9,81236 %**, compuesto con Rf **4,10 %**, ERP **5,50 %**, beta Yahoo **1,045** y Kd histórico **7,31260 %**. La nueva referencia oficial nominal USD a diez años es **4,98 % al 10/11/2026**, último dato admisible observado en [Treasury](https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?field_tdr_date_value_month=202611&type=daily_treasury_yield_curve). El supuesto queda **0,88 pp por debajo** y se marca `DIFIERE_REFERENCIA`. No se reemplaza automáticamente: el diez años es un benchmark nominal documentado, no justificación completa de la selección de plazo ni del WACC. No se aplica Treasury USD a KRW. ERP, ventana de beta y coste prospectivo de deuda siguen sin verificar; Kd conserva su identidad histórica interés FY / deuda media del mismo FY.

El [transcript oficial FY27 Q1](https://www.microsoft.com/en-us/investor/events/fy-2027/earnings-fy-2027-q1) declara CapEx de 45,2 mil millones USD, finance leases de 7,4 y cash PP&E de 39,4; estos últimos concuerdan por redondeo con 39,367 del flujo trimestral. La guía de aproximadamente 170 mil millones para CY2026 corresponde a CapEx de otro perímetro y a un periodo calendario. **No se sustituye cash CAPEX por esa guía**, ni se suman automáticamente cash PP&E y altas de leases como identidad. Falta el calendario que vincule pagos, altas, depreciación y deuda por leases, así como mantenimiento/expansión y vidas útiles de activos. La concentración en activos de vida corta citada por el emisor refuerza esa limitación de usar ratios constantes. Extractos y hashes de fuentes están en [evidencia_oficial.json](evidencia_oficial.json).

Año terminal común T8, g **2,50 %**, reinversión coherente aritméticamente con la trayectoria; el ROIC terminal implícito es **3,92739 %**, frente a WACC **9,81236 %**: diferencial **−5,88496 pp**. El terminal representa **61,9733 %** del EV presente, **64,8348 %** a un año y **71,9894 %** a tres. Este ROIC no sostiene una tesis de creación de valor marginal; es una limitación económica del escenario, no evidencia de que se deba reducir CAPEX o aumentar g. Los DCF permanecen `CONDICIONAL`, `publicable=false`.

`dcf_audit.py` ejecuta nueve experimentos sobre el escenario Base, para horizontes 0/1/3. Cada experimento recalcula la trayectoria, reinversión, caja y DCF, manteniendo datos fuente, Kd, payout y los restantes supuestos. Cambiar g también cambia la convergencia del crecimiento en los años explícitos; no es una variación exclusiva de Gordon con FCFF final fijo. Los shocks están separados del resultado base, tienen límites y conservan los bloqueos. No son probabilidades ni optimizaciones frente al precio de mercado.

| Experimento | Presente USD | 1 año USD | 3 años USD |
|---|---:|---:|---:|
| Base | 156,58 | 163,07 | 174,28 |
| WACC −1 pp | 182,35 | 189,58 | 202,26 |
| WACC +1 pp | 137,05 | 142,96 | 153,04 |
| CAPEX/ventas -1 pp | 167,61 | 175,18 | 188,72 |
| CAPEX/ventas +1 pp | 145,54 | 150,95 | 159,84 |
| D&A/ventas -1 pp | 145,54 | 150,95 | 159,84 |
| D&A/ventas +1 pp | 167,61 | 175,18 | 188,72 |
| g terminal -0.5 pp | 148,65 | 154,36 | 163,78 |
| g terminal +0.5 pp | 165,66 | 173,04 | 186,31 |

Los resultados completos, incluyendo los 27 importes sin redondear y los diagnósticos de supuestos, están en [MSFT_sensibilidad.csv](MSFT_sensibilidad.csv) y [MSFT_validacion.csv](MSFT_validacion.csv). SK genera los mismos experimentos, todos N/D; no se permite que una sensibilidad rellene datos ausentes.

## Fórmulas, comparación por cambio y pruebas

Se recalcularon independientemente:

- `Ke = Rf + beta × ERP`; `Kd = intereses FY / media(deuda inicio FY, deuda fin FY)`; `WACC = E/(E+D) × Ke + D/(E+D) × Kd × (1−t)`, con equity de mercado y deuda financiera en USD. Resultado en [MSFT_wacc_independiente.json](MSFT_wacc_independiente.json). Se verifica la identidad, no la validez prospectiva de esos inputs.
- `FCFF = EBIT × (1−t) + D&A − CAPEX − ΔNWC` en los ocho años de los tres escenarios.
- `VT8 = FCFF8 × (1+g)/(WACC−g)`; `EVh = suma(FCFFy/(1+WACC)^(y−h)) + VT8/(1+WACC)^(8−h)`; `precioh = (EVh−deuda netah)/accionesh × FX`, para horizontes 0/1/3. Los nueve residuales frente al motor son inferiores a 1e-9 USD por acción: [cálculos independientes](MSFT_formulas_independientes.csv).

Las mismas entradas exactas de 43196409785 se ejecutaron con el código anterior, al añadir el diagnóstico de componentes/búsqueda, al introducir la comprobación de evidencia de comparables y finalmente al añadir sensibilidad y contraste de supuestos. No se inyectaron nuevos importes en las etapas de diagnóstico. En cada transición se mantienen los nueve precios MSFT y los N/D de SK; se comparan también los bloqueos. El caso Base usa shocks vacíos y la referencia Treasury no reemplaza un parámetro. [Comparación por etapas](comparacion_entradas_fijas.csv), [detalle](etapas_entradas_fijas.json).

DCF Base MSFT antes y después, tanto con entradas fijas como en ambas ejecuciones en línea: presente **156,5772575411946**, un año **163,0667191219797**, tres años **174,2797213697988** USD. La identidad numérica es comprobable; no se atribuyen ganancias de cobertura financiera a nuevas tablas de auditoría. Los universos de replay contienen 53/55 filas descargadas, mientras el descubrimiento en línea registra 156/149 candidatos; esas métricas tienen distinto denominador y no indican pérdida de cobertura entre ejecuciones.

Las 19 pruebas añadidas a las 36 previas cubren integridad de hashes; etiquetas sin evidencia; reconstrucción de ambos ratios; FY1/NTM; moneda/FX; precio/forecast futuro; ADR y base de EPS; deuda con leases; EBITDA y D&A; mínimo de tres emisores; perímetro consolidado/minoritarios/preferentes; captura SDK sin inventar fechas o bases; formatos de periodos del proveedor; shocks que no mutan entradas ni saltan controles; replay con el entorno del snapshot; revisión oficial que excluye filings futuros; PP&E sin intangibles y diferencia de D&A; referencia Treasury futura, caducada o ambigua; moneda KRW y contraste que no recalibra WACC. Las tres suites originales siguen pasando con fuentes sintéticas explícitas para sus casos positivos de peers.

Reproducción con dependencias de `requirements.lock`:

```bash
python -m pytest -q tests
python autoprueba_modelo.py
python prueba_comparables_automaticos.py
python test_v5.py
python ejecutar_analisis.py --snapshot docs/auditoria_2026-11-12/revision_43196409785/inputs/MSFT_after.json --outdir Resultados/revision_MSFT
python ejecutar_analisis.py --snapshot docs/auditoria_2026-11-12/revision_43196409785/inputs/000660.KS_after.json --outdir Resultados/revision_SK
python docs/auditoria_2026-11-12/revision_43196409785/verificar_revision.py
```

Los replays no consultan red. Devuelven respectivamente 0/PARCIAL y 2/BLOQUEO. El verificador requiere el objeto Git del commit anterior `25d358ce…` disponible en un clon con historial; comprueba las etapas, sus precios/bloqueos, las sensibilidades y las identidades de FCFF/Gordon. `sha256.json` permite comprobar la evidencia archivada. Las respuestas de fuentes dinámicas pueden cambiar su HTML y su hash entre consultas; cada hash corresponde a la respuesta de su captura, no a una identidad inmutable del sitio.

## Pendientes materiales

SK requiere los datos oficiales y puentes descritos; los múltiplos necesitan al menos tres emisores económicamente admisibles con forecasts y definiciones documentadas; MSFT requiere justificar descuento, reinversión, activos/leases, caja distribuible y política de acciones. El contraste de Treasury acredita una referencia, no todo el WACC. La falta de esos datos se muestra como tal y no se sustituye con etiquetas, parámetros ajustados o métodos propios de la empresa.

El modelo conserva la API anterior y sus rutas para otros tickers. El catálogo declara fuentes y marco contable sólo cuando existe cobertura explícita; los validadores y diagnósticos son generales, sin una excepción que libere MSFT o 000660.KS. La referencia USD depende de moneda, no de ticker. Se mantiene la separación de sensibilidades históricas y métodos fundamentales y la prohibición de publicar automáticamente una valoración condicional.
