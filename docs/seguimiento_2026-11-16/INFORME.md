# Mi seguimiento — 16/11/2026

Base: `main` verificado `40e1a0575da0de75231db8d8eed62a1a12b79343`. Rama nueva: `feat/mi-seguimiento`. Entrega mediante PR, **sin fusión automática ni cambios directos en main**.

## Implementación

Primera pestaña **Mi seguimiento** y las seis pestañas V7 existentes. Lista y preferencias en SQLite del perfil del usuario, con consultas parametrizadas, transacciones, JSON UTF-8 y sin pickle. Búsqueda `yfinance.Search` con fuzzy habilitado y ranking aproximado; presenta nombre, ticker y bolsa y exige confirmación. Permite añadir sin duplicar, eliminar, elegir columnas, ordenar, actualizar una/todas y abrir Resumen al seleccionar una fila, conservando supuestos de la captura.

Reutiliza el análisis, estadísticas, PER TTM y comparables auditados de V7. No cambia fórmulas ni parámetros financieros. El adaptador de fuentes/caché se activa sólo para seguimiento: cotizaciones 15 min, búsquedas/submissions 1 h, estados/CompanyFacts 24 h, comparables 72 h e históricos 7 días. No descarga datos al ordenar o cambiar pestañas. Conserva la última captura si falla una consulta y muestra estado desactualizado/error. No almacena respuestas financieras vacías como descargas válidas. Las fechas de índices bursátiles con DST conservan zona y frecuencia al pasar por la caché.

El histórico de beneficio neto usa trimestres fiscales reales de 70–105 días, el reconstructor SEC YTD ya existente y componentes auditables. Hasta 20 variaciones/5 años, sin anualizar, sin crear periodos de cuatro meses, sin dividir por bases nulas/negativas y sin puentear ausencias o divergencias SEC–Yahoo. No cambia el TTM ni los escenarios originales: la serie extendida es un dato de seguimiento separado. Las cifras son neto reportado, con advertencias de extraordinarios/estacionalidad.

## Validación

- Pruebas específicas: **22 passed**. Batería completa Linux: **206 passed, 1 skipped**, dos advertencias esperadas SEC. El caso omitido es la prueba nativa de permisos Windows; se ejecuta en Actions Windows. Tres suites heredadas: PASS.
- Pruebas de persistencia y duplicados, rutas Unicode, recuperación del último análisis ante errores, caducidades, frames/fechas DST, rechazo de cachés vacías, buscador y confirmación, cohortes/monedas/perímetros, colores, reconstrucción YTD, 20 trimestres, pérdidas/ceros/gaps, captura V7 y apertura de Resumen.
- Chromium/Streamlit real: siete pestañas, cinco empresas, selección de fila abre Resumen, lista restaurada tras recarga, exportación JSON y viewport móvil de 390 px sin desbordamiento global ni errores de página. [Captura de la pestaña](mi_seguimiento.png), [registro](navegador.json).
- Se repite la comparación offline de los **13 tickers** archivados. Valoración, EPS, supuestos, controles, diagnósticos y disponibilidad no cambian; incluye MSFT, NVDA, MU, AMZN y SK Hynix. Se verifica también la coherencia de las exportaciones anteriores, 135.717 celdas. [Resultados](comparacion_financiera.json).
- Prueba con Yahoo/SEC reales de MSFT el 16/11/2026: precio fechado **524,695007 USD**, PER TTM **27,384917**, mediana PER 5 FY **35,179753** y cobertura QoQ **20/20**. Conserva seis objetivos, Base **696,84 / 940,68 USD** a 1/3 años. [Evidencia y componentes oficiales](msft_actual.json), [captura reproducible comprimida](evidencias_msft.zip). No se ajustan parámetros contra la cotización.
- Búsqueda real parcial `Microsof`: devuelve Microsoft y su mercado, con confirmación del usuario antes de añadir. Las múltiples coincidencias se prueban además con respuestas controladas. [Respuesta archivada](busqueda.json).

La consulta real se realizó sobre el árbol de trabajo basado en 40e1a05; su captura conserva esa procedencia original. Los hashes del código entregado se registran en el manifiesto. La imagen combina MSFT consultado con cuatro capturas archivadas, todas con sus fechas visibles: no se presentan como cotizaciones en tiempo real de hoy.

## Corrección de un caso límite detectado

Yahoo devolvió un histórico vacío. `historical_multiples` intentaba comparar un RangeIndex vacío con un Timestamp y fallaba antes de explicar la ausencia. Se añade únicamente una guarda para ese caso: conserva el histórico no disponible, no crea múltiplos ni elimina controles. Prueba específica reproduce el fallo. También se corrigió el codec de caché para series de precios que atraviesan cambios DST. Los mismos datos válidos conservan sus cálculos V7 anteriores.

## Límites explícitos

Las dos columnas **EV/EBITDA FY** están presentes, pero V7 no exporta una serie FY acreditada en sus capturas; se muestran ausencias con motivo, sin reinterpretar el EV/EBITDA aproximado heredado ni mezclarlo con el NTM de comparables. Las medias de comparables pueden no estar disponibles si no hay tres emisores con evidencia homogénea. Esto es insuficiencia de datos/validación, no un bloqueo nuevo del EPS/PER.

Los QoQ de AMZN y otras empresas pueden contener extraordinarios identificados; no equivalen a crecimiento recurrente. La diferencia PER TTM frente a FY depurados es un contraste explícito entre periodos, no una señal de compra. No se inventa un histórico de veinte trimestres donde no haya fuentes oficiales/Yahoo suficientes.

Persistencia por perfil del sistema/instalación; no hay autenticación multiusuario. En servidores compartidos se comparte la lista y en Streamlit Cloud el disco puede ser efímero; se indica en pantalla y documentación. Windows mantiene UTF-8/CA segura; las pruebas de escritorio de esta entrega se hacen en Linux y los tests nativos Windows corresponden a Actions, no al equipo personal del usuario.

[Instrucciones completas](../../SEGUIMIENTO.md). Logs de [pruebas específicas](pruebas_seguimiento.log) y [suite completa](pruebas_completas.log). La PR debe superar los jobs Linux/Windows y quedar abierta para revisión.
