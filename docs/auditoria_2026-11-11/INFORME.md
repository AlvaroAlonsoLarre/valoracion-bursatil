# Corrección de la auditoría MSFT y SK hynix

Fecha inicial: 11 de noviembre de 2026. Actualizado el 12 de noviembre de 2026. Las horas de los artefactos se expresan en UTC.

**Estado más reciente:** [continuación del 12/11/2026](../auditoria_2026-11-12/INFORME.md), con revisión de Actions 43086248781 y comparación con Actions 43189252381. MSFT recupera nueve DCF condicionales gracias a D&A pura oficial; sus múltiplos y las valoraciones de SK continúan bloqueados. Las cifras y el dictamen del resto de este documento corresponden a la fase inicial del 11/11 y se conservan como evidencia histórica.

## Resultado

Se corrigieron errores de periodo, controles trimestrales, terminal DCF, actualidad, coste histórico de deuda, definiciones de comparables, exportación y orquestación. Se preservó la entrada de cualquier ticker y el tratamiento de divisas. No se calibró ningún parámetro para aproximar objetivos a la cotización. No se fusionaron cambios a `main` y se eliminó la publicación automática de resúmenes en esa rama.

Las ejecuciones reales de ambos emisores terminaron técnicamente y conservaron sus diagnósticos. **Ambos quedan financieramente bloqueados**: MSFT carece de D&A pura reconciliada y de múltiplos con definiciones suficientes; SK hynix está atrasada en Yahoo respecto a su publicación oficial. El bloqueo es el resultado correcto de estos controles, no una estimación de precio cero. Las sensibilidades históricas FY de MSFT siguen disponibles y expresamente separadas de los métodos fundamentales.

El adjunto se trató como evidencia y propuestas de aceptación, no como instrucciones que sustituyeran la solicitud del usuario.

## Procedencia y reproducción

Referencia inicial: `6ef0742a4d37fcabd77cda886895c7685a7f6dd7` (main al clonar). Las ejecuciones originales de ambos tickers comenzaron a las 19:00:16 UTC; las corregidas, a las 19:13:46 UTC. Se conservan las entradas financieras exactas en `inputs/*_baseline.json` y `inputs/*_after.json`, sin credenciales ni código ejecutable.

La implementación probada localmente es `411aac9704b92188e9c10c7838d177290517d9c7`. El commit remoto de implementación es `f5efb83383edea57a9ca8bef99b49cd1dd67941c`: tiene exactamente el mismo árbol de fuentes `341e46cbf66e7c291044dc5bc2248f7018c3968b`. Los commits locales de desarrollo no se reescribieron ni se presentaron como SHA remotos; GitHub recibió un commit de implementación y un commit de evidencia/revisión.

`comparacion_por_cambio.csv` compara cada etapa sobre las **mismas entradas originales**, incluidos precio, acciones, divisa y fecha. Las nuevas rutas de descubrimiento y la consulta IR se comprueban además en las ejecuciones reales corregidas. Sus entradas son distintas y no se usan para atribuir a una fórmula el efecto de un cambio de datos de mercado. `cobertura.json` acredita ambos tickers vinculados al mismo SHA local de código probado. `sha256.json` identifica los archivos de evidencia.

Los snapshots permiten reproducir el registro y las tablas del motor fundamental sin red. No reproducen toda la descarga original de Yahoo/SEC ni sustituyen los filings originales. Las versiones instaladas constan en `requirements.lock` y en cada snapshot. La reproducción numérica se comprueba con tolerancia relativa 1e-12 por el redondeo de Excel; no se exige igualdad binaria entre números JSON leídos directamente y números pasados por Excel.

```bash
python ejecutar_analisis.py --snapshot docs/auditoria_2026-11-11/inputs/MSFT_after.json --outdir Resultados/replay_MSFT
python ejecutar_analisis.py --snapshot docs/auditoria_2026-11-11/inputs/000660.KS_after.json --outdir Resultados/replay_SK
```

Ambas órdenes devuelven 2 deliberadamente. Excel, JSON, entradas y log permanecen disponibles. Los Excel/log completos se generan también en Actions como artefactos por ticker/SHA/run/intento; el repositorio conserva los diagnósticos compactos, inputs y comparación, evitando añadir binarios a la PR.

## Comparación antes y después de cada grupo de cambios

DCF base futuro; precios en USD para MSFT y KRW para SK hynix. Las cifras intermedias son pruebas de atribución de cambios y **no objetivos finales autorizados**.

| Etapa acumulada | MSFT 1 año | MSFT 3 años | SK 1 año | SK 3 años |
|---|---:|---:|---:|---:|
| Original reproducido | 121,353623 | 128,913308 | 685.664,081587 | 817.427,110934 |
| 01 Periodos y actualidad desconocida | 160,161826 | 175,275643 | 618.121,952885 | 733.156,579418 |
| 02 Terminal común, deuda media y financiación bruta | 163,376824 | 174,649337 | 617.554,924335 | 730.787,614820 |
| 03 Definiciones D&A, leases y múltiplos | N/D | N/D | 617.554,924335 | 730.787,614820 |
| 04 Contraste IR y registro común | N/D | N/D | N/D | N/D |
| 05 Integración, ROIC TTM y diagnóstico | N/D | N/D | N/D | N/D |

El CSV incluye todos los escenarios, métodos y horizontes, no solo esta tabla base. La consolidación del workflow no altera las fórmulas. El cambio de crecimiento pasa MSFT de 8,2164% a 15,3011% usando la mediana FY etiquetada; al faltar ocho trimestres, su crecimiento TTM interanual queda N/D. No se usa el Q1 interanual como si fuera TTM. En SK se conserva el límite histórico existente de crecimiento FY del 40%, sin introducir parámetros para acercarse al precio.

## Fórmulas y controles

- TTM = suma de cuatro flujos de tres meses consecutivos. Crecimiento TTM interanual = suma de los últimos cuatro / suma de los cuatro anteriores − 1, con ocho periodos completos. Sin esos datos, fallback FY identificado o N/D; no cero inventado.
- Cada flujo de ingresos, EBIT, OCF, CAPEX y D&A se concilia con su FY si hay cuatro cierres coincidentes. Tolerancia relativa estricta <1%, con tolerancia absoluta de una unidad para redondeo. Duplicados idénticos son idempotentes; conflictos invalidan el flujo y sus derivados. YTD se diferencia dentro del mismo ejercicio solo con inicio explícito; EPS acumulado no se diferencia sin acciones ponderadas.
- FCFF = EBIT × (1 − tasa fiscal normalizada) + D&A − CAPEX − ΔNWC. No se redujeron ratios CAPEX, ni se inventó desglose mantenimiento/expansión.
- Se usa un año terminal común T=8, ya con crecimiento estable. EV(h) = Σ FCFF(t)/(1+WACC)^(t−h), t=h+1…8, + FCFF(8)×(1+g)/(WACC−g)/(1+WACC)^(8−h). Equity(h) = EV(h) − deuda neta(h). Precio = equity/acciones × FX. Se exporta también h=0 como valor presente.
- Reinversión terminal = (CAPEX−D&A+ΔNWC)/NOPAT; ROIC terminal implícito = g/reinversión. Se muestran ambos y el peso del terminal. Si la reinversión no permite FCFF positivo/coherente, no se calcula Gordon. Es una sensibilidad derivada de ratios, no una validación externa del ROIC terminal.
- Kd histórico = intereses del último FY/deuda financiera media inicial-final del mismo FY, nunca un flujo FY dividido por un saldo trimestral posterior. Si no existe base comparable, el fallback es un supuesto explícito. Los intereses de la proyección usan deuda bruta financiera constante como hipótesis, no deuda neta que pudiera convertirse en caja.
- ROIC FY y TTM usan NOPAT/capital medio del mismo periodo. Sin saldo inicial comparable queda N/D. El TTM se exporta en hoja separada; el diferencial histórico se etiqueta frente a WACC **actual**.
- El calendario documentado de acciones admite emisiones/SBC y cancelaciones con precio cash de recompra en divisa financiera; reconcilia caja y acciones. Sin evidencia, conserva acciones constantes y declara la limitación. El retorno total añade dividendos cobrados al retorno de precio, sin devolverlos a la caja final.
- FX requiere monedas declaradas y tipo directo o inverso válido. KRW→KRW=1. No se compara tamaño por capitalizaciones nativas de monedas distintas. Se retiró la clasificación previa por capitalización de screener sin divisa; la señal de tamaño solo usa moneda común acreditada.

## Fuentes oficiales y resultado de las ejecuciones corregidas

**MSFT:** [Microsoft FY27 Q1](https://www.microsoft.com/en-us/Investor/earnings/FY-2027-Q1/press-release-webcast), publicado el 28/10/2026, confirma el periodo 30/09/2026. Se contrastan 92.279, 45.915 y 36.629 millones USD de ingresos, EBIT y beneficio neto, respectivamente, con diferencia cero frente a Yahoo en esta ejecución. El efecto neto OpenAI de 207 millones USD se registra separado, sin trasladarlo automáticamente a una proyección normalizada. La ausencia de contacto SEC conserva `NO_VERIFICADO` para la consulta de actualidad SEC; el contraste del periodo IR no acredita que no existan publicaciones posteriores.

Se registraron 156 candidatos descubiertos, de los cuales uno superó la comparabilidad económica. Estos recuentos incluyen estados no intentado/error/excluido, no 156 descargas válidas. Los campos Yahoo `forwardPE` y `enterpriseToEbitda` no acreditan por sí solos GAAP/NTM y un perímetro homogéneo. No se rellenan referencias con múltiplos propios. D&A conserva el agregado `DepreciationAmortizationAndOther` como agregado aproximado cuando falta D&A consolidada pura; ese agregado bloquea DCF y EV/EBITDA. No se sustituye por depreciación de PP&E aislada. Runner: 0 bloqueos globales de entradas, 0 objetivos fundamentales disponibles, estado financiero BLOQUEO, exit 2.

**SK hynix:** [comunicado oficial Q3 2026](https://news.skhynix.com/en/q3-2026-business-results/), publicado el 28/10/2026. La referencia expresa cifras en trillion KRW y se convierte explícitamente con ×10^12. El periodo oficial 30/09/2026 es posterior al último trimestre Yahoo 30/06/2026; no se atribuye coincidencia a campos que faltan. Se conserva N/D para el importe reconciliado del efecto Kioxia. No se introduce Q3 parcial en el TTM ni se inventan OCF, CAPEX, D&A o deuda. No hay cobertura CompanyFacts equivalente a un emisor US-GAAP: SEC ausente no cuenta como conciliación satisfactoria. Se registraron 150 candidatos y siete económicamente elegibles, sujetos además a los requisitos por múltiplo. Runner: 2 bloqueos globales de entradas, 0 objetivos disponibles, exit 2.

## Pruebas realizadas

`python -m pytest -q tests`: 25 pruebas unitarias y de integración, incluyendo ejecución real del CLI offline y ruta completa runner→subproceso simulado→Excel→JSON. También pasan `autoprueba_modelo.py`, `prueba_comparables_automaticos.py` y `test_v5.py`. El fixture anual de la autoprueba se hizo coherente con sus propios trimestres para no mantener un dato sintético que ahora incumple la conciliación.

Se verificaron de forma independiente FCFF, EV/equity DCF a 0/1/3 años, reinversión/ROIC implícitos, deuda media, recompra/emisión/SBC, retorno total, FX directo/inverso, periodos de ROIC, mínimos de tres emisores, bloqueo por definiciones, estados de actualidad, YTD y duplicados. Las pruebas de integración comprueban conservación de artefactos, código de salida, mismo registro de métodos en Excel/JSON, snapshot y hashes, fallo técnico y cobertura por SHA.

Las dos ejecuciones completas con red autorizada se ejecutaron localmente; no se depende de un resultado futuro de Actions para afirmar que se probaron ambos tickers. El workflow se valida como YAML y se consolida en un único archivo con jobs. Una ejecución Actions roja por bloqueo financiero no debe convertirse en verde mediante `continue-on-error` ni publicando precios sin soporte.

## Cobertura de los criterios del informe adjunto y límites pendientes

| Criterios | Implementación y límite material |
|---|---|
| A01, A08, A16 | Matriz por defecto de ambos tickers, ejecución manual genérica, artefactos únicos, manifiesto por SHA, código 2 financiero y código 1 técnico con diagnóstico. Sin escritura a main ni auto merge. |
| A02, A03, A19 | Periodos equivalentes, conciliación por flujo, duplicados conflictivos y YTD. Yahoo se solicita con `freq=quarterly`; si no publica metadatos originales de inicio, no se inventan. Sin FY completo de contraste no se afirma que el periodo haya quedado independientemente conciliado. |
| A04 | Trayectoria y terminal comunes; cálculo independiente; reinversión/ROIC terminal visibles. Sigue faltando un calendario de activos y depreciación sustentado en notas para validar económicamente el estado estable. |
| A05 | Convención financiera sin leases declarada; deuda que explícitamente incluye leases bloquea los métodos afectados. No se suman leases anuales al balance trimestral ni se resta dos veces la obligación. **Pendiente** un calendario completo de leases/activos/pagos y caja estratégica/distribuible; por ello las salidas posibles siguen condicionales. |
| A06, A12 | Semillas económicas complementan discovery automático, registro de candidatos, tres emisores independientes por método, GAAP/NTM/perímetro explícitos y monedas comunes para tamaño. Yahoo no aporta por sí solo las definiciones exigidas; por tanto los múltiplos pueden quedar N/D aunque haya candidatos económicos. El identificador de emisor depende de underlyingSymbol/nombre/ID declarado y requiere revisión para listados complejos. |
| A07 | Se conserva NO_VERIFICADO/REVISAR/BLOQUEO; VERIFICADO exige consulta SEC válida. IR confirma un periodo y puede bloquear datos viejos; una fecha estimada Yahoo nunca confirma publicación. |
| A09 | Moneda, consulta, fuente, fecha y caducidad explícitas; vencimiento y doble prima país bloquean. **Pendiente** obtener rf/ERP/beta/Kd prospectivos verificables y calibración por plazo; los defaults no pasan a verificados por añadir una fecha de consulta. |
| A10, A11, A15 | ROIC comparable y TTM separado; calendario opcional de acciones documentadas; retorno total separado. **Pendiente** conciliación económica de efectivo operativo/goodwill/leases, historial WACC y evidencia real de cancelaciones/SBC de cada compañía. |
| A13 | Ausencias no cuentan como coincidencia; cero/cero coincide, cero/no cero discrepa; denominador y umbral <1% explícitos. La coincidencia de datos derivados con entradas compartidas no es una verificación independiente adicional. |
| A14 | IR contrastado con fuente, periodo, unidad y hash; OpenAI separado y Kioxia N/D donde falta importe reconciliado. **Pendiente** estados consolidados Q3 completos de SK y conciliación DART/IR de extraordinarios. |
| A17 | Registro común de todas las familias con method_id, fechas, moneda, periodo, escenario y validación; Excel y JSON exportan históricos y fundamentales. Media, mediana, CAGR y dispersión se conservan y no se promedian familias. |
| A18 | D&A pura y agregado D&A/otros se separan; se conserva el concepto original. El agregado no autoriza FCFF ni EV/EBITDA; no se infiere amortización consolidada de PP&E aislada. |

Estos límites son necesidades de información o validación económica, no parámetros que deban modificarse para obtener un precio deseado. La PR corrige el comportamiento del software ante esas ausencias y conserva la evidencia para completar una valoración cuando existan datos suficientes.
