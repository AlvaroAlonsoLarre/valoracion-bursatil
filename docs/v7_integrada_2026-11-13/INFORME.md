# V7 integrada sobre la V6 verificada — 13/11/2026

La aplicación única vuelve a mostrar los seis objetivos de MSFT. No se han cambiado las fórmulas EPS × PER ni calibrado supuestos contra la cotización. La rama `feat/v7-integrada` parte exactamente de `b50a51d37523d6cef0a2ca1013e5ecfb8ce9ba61`; integra la interfaz V7 sobre el motor y los controles existentes. `main` y la rama de la PR #1 no se modifican.

## Diagnóstico y alcance de la reproducción

Se revisó el instalador proporcionado, sin ejecutar sus scripts Windows de instalación/reparación. Identidad del ZIP: SHA-256 `3973ea015de35008b2ef85560b5007763d8e5239ec784fdd3b98e836c8b01871`. `aplicar_v7.py`: SHA-256 `1632534fc7487bbc53987342dfc01395fcd088a4860dd40bd7203a6828149b1d`.

**Una instalación limpia de ese parche sobre b50, con la captura MSFT completa y los mismos supuestos, sí calcula 696,84 / 940,68 USD y seis objetivos.** Por tanto, el ZIP por sí solo no demuestra el estado exacto del equipo del usuario: no incluye la carpeta instalada, su captura activa ni su sesión Streamlit. No se atribuye su caso particular a una fórmula incorrecta sin evidencia.

Se identificaron estos fallos concretos:

1. `instalar_v7.py:23–26` conserva cualquier directorio existente que tenga `dashboard_app.py`, sin verificar commit ni versión. Reutilizar una instalación puede ejecutar código distinto del b50 anunciado.
2. El parche cambia la tabla inicial de escenarios a `result.assumptions`, pero deja el guardado original que empieza con `scenarios={}` y sólo guarda diferencias. Al pulsar **Recalcular escenarios** sin cambios se pierden los ajustes previos, incluido el PER manual.
3. Reproducción real de ese segundo fallo: mismos estados MSFT, referencias PER ausentes y PER manual válido 20×. Antes del clic hay seis objetivos (Base 396,16 / 534,79); después se borran los PER y quedan cero. No se eliminaron controles ni se alteraron estados contables para habilitar objetivos. La ausencia de referencias es un caso de captura incompleta explícitamente preparado para aislar el defecto de persistencia.
4. El gráfico del instalador descarta un escenario entero si falta uno de sus dos horizontes. Oculta así un objetivo válido del otro horizonte.
5. La carga inicial de capturas de V6 descartaba sus supuestos guardados. La caché de Streamlit tampoco identificaba revisiones de los módulos financieros importados. Ambos riesgos están corregidos y probados.

Las evidencias de reproducción están en `evidencias.zip` (`repro_estado.json`, `repro_state.log`, `repro_instalador.log`). El nuevo test de integración repite la captura sin referencias, el PER manual y el clic: conserva el PER y los objetivos.

## Cambios integrados

- Un solo `dashboard_app.py`, los seis apartados originales y el motor financiero original. Se conservan fuentes, estados, métricas, estadísticos 5/10 años, comparables, normalización económica, divisas/ADR y controles por método.
- Guardado de escenarios mediante cambios sobre los ajustes existentes. Aplicar PER modifica sólo PER/base temporal/justificación y su opción exploratoria; conserva crecimiento, margen, fiscalidad, dilución, política, ADR y opciones avanzadas. Cambiar de pestaña no borra ajustes. La captura reproducible exporta los supuestos activos.
- Resumen: histórico de 1 semana, 4 meses o 1 año y previsión Ninguna/1 mes/4 meses/1 año/3 años. Cotización sólida y tres escenarios discontinuos. Los objetivos a 1/3 años salen exclusivamente del motor EPS × PER; los intermedios son interpolaciones geométricas ilustrativas identificadas como tales. No cuentan como nuevos objetivos en el registro financiero.
- Se conservan horizontes disponibles cuando falta otro. Sin objetivo a tres años se detiene la curva en el año uno; sin objetivo a uno no se inventa uno. Sin precios diarios archivados se informa de la ausencia, manteniendo objetivos válidos y evitando descargas al recalcular.
- Selector PER automático/manual visible y expandido en Resumen, Base y distancias relativas editables. Un PER manual exige justificación; no suple EPS, moneda, acciones ni cuentas insuficientes.
- La referencia automática ordinaria mantiene sus mínimos. Con **dos PER económicamente admisibles**, una opción explícita habilita una valoración **exploratoria de confianza Baja** con banda al menos ±20%, sin fingir cuartiles precisos. Con cero/uno requiere PER manual u otra referencia suficiente ya validada. No mezcla TTM con NTM ni altera filtros de extraordinarios/cambio de régimen.
- Capturas: valida esquema; distingue entradas de resultados; conserva ajustes; reconstruye referencias ausentes sólo si existen precios/splits y estados archivados suficientes, usando los controles originales. Sin evidencia deja el PER automático indisponible y explica el motivo.
- Caché identificada por firma de los módulos financieros. Datos y auditoría muestra commit y firma, también útil para detectar servidores/copias antiguas. Sin `.git`, el commit aparece como N/D y permanece disponible la firma.
- Exportación de consola: lectura del Excel conservando tipos de celda. Evita convertir CIK/tickers textuales con ceros iniciales en números en JSON. No altera importes ni EPS. Se corrigieron además dos inserciones redundantes del lanzador durante la revisión; éste utiliza los archivos del repositorio y no parchea descargas.

## Precios y controles antes/después

| Caso / moneda | Base V6 1 año → V7 | Base V6 3 años → V7 | Resultado |
|---|---:|---:|---|
| MSFT archivado, USD | 696,84 → 696,84 | 940,68 → 940,68 | Seis objetivos, tres escenarios |
| MSFT consulta 13/11, USD | 696,84 → 696,84 | 940,68 → 940,68 | Seis objetivos; cero errores bloqueantes compartidos |
| NVDA automático, USD | 496,90 → 496,90 | 1.159,41 → 1.159,41 | Normalización V6 conservada |
| MU automático, USD | 416,88 → 416,88 | 665,60 → 665,60 | Normalización V6 conservada |
| AMZN automático, USD | No disponible → igual | No disponible → igual | Insuficiente referencia PER limpia |
| SK Hynix automático, KRW | No disponible → igual | No disponible → igual | Insuficiente referencia PER ordinaria |

La comparación sin red de **los 13 tickers** (MSFT, NVDA, AMZN, NFLX, META, GOOGL, GOOG, MU, SNDK, SPCX, JNJ, JPM y 000660.KS) verifica igualdad de tablas de valoración, EPS proyectado, supuestos, controles por método, diagnósticos y disponibilidad de métricas frente a los resultados archivados de b50. Los resultados no disponibles de AMZN, SK Hynix, SNDK y SPCX siguen documentados; no se fabrican estimaciones.

Las sensibilidades manuales cambian los precios por una causa explícita, **el múltiplo elegido**, conservando el EPS. Ejemplo de prueba con PER Base 20× y bandas ±20% (no es una recomendación económica):

| Caso | Base 1 año | Base 3 años | Motivo |
|---|---:|---:|---|
| MSFT, USD | 396,16 | 534,79 | PER 20× frente al automático 35,18× |
| AMZN, USD | 85,17 | 101,83 | PER manual suple la referencia insuficiente; conserva recurrencia/Anthropic |
| SK Hynix, KRW | 1.812.025,40 | 2.971.894,95 | PER manual sobre EPS válido; conserva normalización, moneda y acciones |

Para EPS fijo, el precio cambia proporcionalmente al PER. Crecimiento, márgenes, resultado no operativo, fiscalidad y dilución siguen determinando el EPS mediante las fórmulas originales, con sus tablas de sensibilidad e hipótesis implícitas. NVDA conserva crecimiento Base 68,30% → 46,59% y margen 54,12%; MU 44,25% → 23,23% y margen 26,14%. Son hipótesis exigentes, no garantías; esta integración no las cambia para reproducir una cotización.

## Validación ejecutada

1. Primero capturas existentes y pruebas específicas; después batería completa: **160 passed**, dos advertencias esperadas de tests del fallback de identidad SEC. Últimas pruebas específicas (V7 + auditoría I/O): **44 passed**.
2. Suites heredadas `autoprueba_modelo.py`, `prueba_comparables_automaticos.py`, `test_v5.py`: PASS. No se repitieron tras cambios limitados a validación de entrada, preservación de tipos de exportación y limpieza del lanzador; la batería completa sí se volvió a ejecutar.
3. Streamlit AppTest: importación de ajustes, PER manual, crecimiento/política previos, recálculo sin cambios, persistencia, referencias antiguas/incompatibles y caché versionada.
4. Chromium/Playwright sobre Streamlit real: las **15 combinaciones** del gráfico, seis pestañas, seis descargas, persistencia tras el segundo formulario y móvil 390 px sin desbordamiento global ni errores de página. Los extremos del gráfico coinciden con los objetivos del motor. [Captura Resumen](resumen.png).
5. Validación de exportaciones automáticas/manuales descargadas del navegador y ejecución actualizada: **33 + 33 + 35 tablas no vacías**, **135.717 celdas** Excel/JSON comparadas; además replay de capturas y coincidencia de objetivos, supuestos, proyecciones, controles y registro. Tolerancia numérica relativa/absoluta 1e-10; fechas intermedias del gráfico hasta 1 ms por redondeo XLSX. Ceros iniciales y texto se conservan. El JSON de la consulta se reexportó desde su mismo Excel tras corregir tipos, sin otra descarga; se conserva también el JSON anterior en la evidencia.
6. Una consulta MSFT con red: corte 13/11/2026, cotización disponible 12/11/2026, 523,00 USD. Seis objetivos, salida 0, estado **ESTIMADO**, confianza Baja, `publicable=false`. Un comparable elegible entre 156 candidatos, ninguno con PER TTM/NTM homogéneo verificado: la referencia es el histórico propio (cinco FY/observaciones). La falta de disponibilidad de P/FCF, EV/EBITDA o DCF no bloquea EPS × PER.

Código financiero/interfaz de la primera validación y consulta: `c7ea5dfc49b395fa03a3f2f47f3cc2123b084ad0`. Corrección final de compatibilidad/tipos y 160 pruebas: `a3660034a4a9b5a86ce8fb5ac21181e6794a2557`. Los commits posteriores de documentación no cambian el motor. Los logs y exportaciones conservan sus respectivas procedencias; la captura de pantalla usa la captura archivada fechada, no presenta datos de hoy como si fueran en tiempo real.

## Evidencias y ejecución

- [Instrucciones Windows](../../WINDOWS.md): Python 3.12 x64, entorno `.venv`, dependencias fijadas y `python -m streamlit run dashboard_app.py`. No se publica otro instalador por parches.
- [Comparación y consistencia](consistencia_verificada.json), [casos manuales y normalizados](casos_adicionales.json), [pruebas completas](tests_full.log), [pruebas relacionadas](tests_v7.log), [comprobación de navegador](navegador.json).
- [Evidencias comprimidas](evidencias.zip): captura/Excel/JSON/log de la consulta MSFT; descargas auto/manual del navegador; logs de reproducción del defecto del instalador. [Manifiesto SHA-256](MANIFEST.json).
- Para verificar sin red: extraer `evidencias.zip` y ejecutar desde la raíz `python docs/v7_integrada_2026-11-13/validar_evidencias.py RUTA_EXTRAIDA`. Reutiliza también los ZIP de 13 tickers ya archivados en el repositorio; no descarga estados ni precios.

## Limitaciones pendientes

No se ha inspeccionado la instalación efectiva del ordenador Windows ni su sesión original; para cerrar esa atribución concreta serían necesarios sus archivos activos. Sí se ha reproducido y corregido la pérdida de PER/precios y verificado el caso MSFT completo. Las pruebas de aplicación/navegador se ejecutan en Linux; no se afirma una ejecución en un escritorio Windows real.

La confianza económica baja, los múltiplos/comparables insuficientes y los controles de los métodos opcionales siguen siendo limitaciones explícitas. Los precios a corto plazo del gráfico son ilustraciones entre anclas, no pronósticos adicionales. Persistir dentro de la sesión funciona al cambiar de pestaña; para conservar supuestos después de cerrar el servidor hay que exportar/importar la captura reproducible. No se ha fusionado ninguna rama.
