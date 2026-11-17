# Mi seguimiento

La primera pestaña guarda una lista de empresas y sus capturas completas del **mismo motor V7**. Las seis pestañas del análisis individual siguen disponibles. El gráfico principal de cotización y escenarios se encuentra aquí, encima de la tabla; Resumen conserva valoraciones y controles.

## Uso

1. Busca por nombre, parte del nombre o ticker; Yahoo admite búsqueda aproximada. Confirma **nombre, ticker y bolsa** antes de añadir. No se agregan ETF ni duplicados.
2. **Añadir empresa confirmada** ejecuta automáticamente el análisis V7 completo, con progreso, fuentes, históricos, comparables y escenarios. Puede tardar. Las insuficiencias financieras mantienen sus controles y permiten conservar los datos parciales utilizables.
3. También puedes **Guardar empresa y ajustes del análisis abierto** para incorporar una captura sin red. Guardarla no convierte sus datos antiguos en datos de hoy.
4. Selecciona la **Empresa del gráfico** o la **Empresa guardada** de la barra lateral para recuperar captura y supuestos inmediatamente. Elegir una fila de la tabla abre Resumen con esa empresa, también después de ordenar. Los cambios de PER, crecimiento y márgenes de empresas guardadas se conservan al aplicar el formulario.
5. El gráfico reutiliza `grafico_cotizacion.py`: histórico de 1 semana/4 meses/1 año, previsión ninguna/1 mes/4 meses/1 año/3 años. Los extremos anuales proceden de EPS × PER; las trayectorias intermedias son interpolaciones ilustrativas. Sin objetivos válidos sólo muestra el histórico y su limitación. Cada empresa conserva su moneda y controles de gráfico.
6. Ordena numéricamente por las cabeceras, desplázate horizontalmente y elige columnas. Las ausencias se muestran como **—**. Verde/+ significa PER TTM inferior a la mediana FY; rojo/−, superior. No es una señal de compra.
7. **Actualizar empresa/todas** utiliza la actualización incremental. **Forzar actualización completa** reconsulta todas las fuentes de la empresa elegida, conservando los supuestos. **Eliminar empresa** borra su fila/captura, sin borrar la caché pública de fuentes.
8. **Importar / exportar copia de seguimiento** guarda lista, capturas, ajustes y columnas en JSON. Importar no descarga; valida antes de guardar y reemplaza las capturas de los mismos tickers. Exporta antes si quieres conservar ambas versiones. Admite las exportaciones antiguas de la lista.

Seleccionar empresas, pestañas, periodos gráficos, columnas u ordenación no realiza consultas de red. Excel, JSON de resultados y captura reproducible del análisis activo siguen en Datos y auditoría.

## Métricas y periodos

- **PER actual TTM**: EPS diluido reportado y base de cotización/acciones/ADR/FX admitida por V7; no se sustituye por `trailingPE` sin validar. Los resultados extraordinarios detectados, incluidas inversiones, siguen advertidos.
- **PER mediana 5 FY**: referencia depurada existente de V7. Excluye observaciones rechazadas por beneficios atípicos, pérdidas, fiscalidad, ciclo, régimen y base por acción. Menos de tres FY limpios no se convierte en referencia automática suficiente.
- **Descuento PER (%)**: `(mediana FY − PER TTM) / mediana FY × 100`, con ambos positivos. Contrasta explícitamente periodos diferentes; no equivale a rentabilidad prevista.
- **QoQ neto**: beneficio reportado de trimestres fiscales contiguos de 70–105 días. Sin porcentajes con denominador nulo/negativo, sin puentear ausencias o conflictos SEC–captura. Una caída desde beneficio a pérdida sí conserva el porcentaje y contexto.
- **Histórico QoQ 5 años**: hasta 20 variaciones, con un cierre predecesor adicional cuando está disponible. Se reutiliza el reconstructor SEC YTD: Q2 = 6m−3m, Q3 = 9m−6m, Q4 = FY−9m, con mismo inicio, concepto/unidad y fecha de publicación admisible. Se guardan componentes y evidencias para recuperar la cobertura sin red. Las capturas antiguas sin el predecesor pueden recuperar sólo 19 variaciones de 20 cierres. Media, mediana y cobertura no son una previsión recurrente: influyen estacionalidad y extraordinarios.
- **EV/EBITDA Yahoo**: `enterpriseToEbitda` sin reconciliar, separado del FY, con cierre `mostRecentQuarter` si el proveedor lo aporta. Si no lo aporta, el periodo se declara desconocido; nunca se rebautiza como NTM.
- **EV/EBITDA último FY / mediana 5 FY**: usa la fórmula compartida V7 `EV = capitalización + deuda − efectivo`, dividida por EBIT + D&A del FY. Precio observado al cierre (hasta 7 días anteriores), acciones en base split coherente, deuda/efectivo del ejercicio. Prefiere acciones instantáneas SEC; si sólo hay medias diluidas las identifica como aproximación. Conserva ese subconjunto oficial en la captura para importación y edición de ajustes. Usa D&A pura validada cuando existe; D&A consolidada reportada sin conciliación completa reduce la confianza. No utiliza D&A que mezcle otros ajustes. La mediana no mezcla perímetros de arrendamientos distintos. Sin FX histórico, puente ADR/clases, deuda, efectivo o EBITDA positivo admisible, muestra ausencia y motivo. No sustituye deuda ausente por cero. Los cálculos son **aproximados, confianza baja**, o **contrastados, confianza media y no auditados**, según componentes; no se usan para modificar objetivos.

## Dos niveles de comparables

**A — Validados:** controles económicos y financieros originales V7 para valoración. PER TTM y NTM separados; EV/EBITDA NTM con cohorte, periodo, divisa y perímetro homogéneos. Medias sólo con al menos tres emisores únicos admisibles, sin dispersión excesiva; detalle con mediana, N, fuentes y exclusiones.

**B — Informativos:** hasta seis candidatos relacionados por actividad/industria/sector del universo económico ya descubierto. Muestra `trailingPE`, `forwardPE` y `enterpriseToEbitda` Yahoo en series distintas. Forward Yahoo no acredita por sí solo NTM. Medias y medianas descriptivas con N visible, incluso N=1, sólo valores positivos de misma moneda de cotización y financiera. Las discrepancias de divisa se excluyen de las medias, aunque el candidato siga visible. Sus periodos/beneficios/perímetros **no están conciliados** y la confianza es baja. Nunca entran en precios objetivo. Consulta candidatos y motivo por el que no cumplen A.

## Actualización, fallos y persistencia

El encabezado muestra la actualización de la tabla y la última **consulta** de cotización en la zona del navegador, manteniendo timestamps UTC. Cada fila conserva la fecha del precio y de resultados. Una consulta reciente no convierte un último cierre en tiempo real. Hay un contador visible de datos pendientes, antiguos o parciales.

| Componente | Política |
|---|---|
| Cotización | 15 min en sesión conocida; 1 h fuera de sesión; hasta 6 h en fin de semana; caducidad recortada ante próxima apertura |
| Búsqueda y submissions SEC | 1 h |
| Estados y CompanyFacts SEC | 24 h |
| Evidencia financiera de comparables A | 72 h |
| Perfil/ratios Yahoo del objetivo y comparables B | 1 h |
| Histórico completo/directorio SEC | 7 días; cierres recientes incorporados incrementalmente |

Los horarios de sesión son orientativos (Nueva York, Seúl, Londres); no se incorpora un calendario de festivos. Otros mercados usan 15 min.

Se compara accession/fecha/formulario y contenido de CompanyFacts; sin SEC, contenido de los estados Yahoo. Una revisión del mismo FY puede renovar el análisis. Sin cambios se reutilizan estados y evaluación económica de candidatos. El histórico incorpora los cierres recientes ya consultados con el precio o descarga sólo el tramo faltante con solape; elimina duplicados y aplica correcciones. Un split detectado exige serie completa coherente y revalidación. Forzar evita las cachés de fuentes.

La sección **Actualización incremental** muestra componentes consultados/reutilizados y errores. Si falla una fuente se conserva el dato anterior con advertencia; un análisis parcial puede actualizar componentes válidos, conservando también la captura previa sin incidencias para descarga. Un fallo terminal no sustituye la última captura. Las respuestas financieras vacías no se almacenan como descargas válidas. Una empresa sin datos no impide abrir el resto.

Una sola base SQLite transaccional guarda lista, preferencias, capturas y caché en el perfil del sistema (`%LOCALAPPDATA%\ValoracionBursatil\seguimiento` en Windows). La pestaña muestra la ruta. Sobrevive a reinicios y cambios de carpeta del código. La lista inicial está vacía; las capturas documentadas son ejemplos. Puede configurarse `VALUACION_WATCHLIST_DIR` opcionalmente. Para respaldo completo, cierra Streamlit y copia esa carpeta, o exporta la lista con capturas.

En servidores compartidos la lista es de la instalación, sin aislamiento por usuario web. En alojamientos con disco efímero exporta antes de recrear el contenedor.

## Windows 11 sin Git

Mientras la PR #3 esté pendiente de tu revisión, [descarga el ZIP de esta rama](https://github.com/AlvaroAlonsoLarre/valoracion-bursatil/archive/refs/heads/feat/mi-seguimiento.zip), extrae **todo** en una carpeta nueva y haz doble clic en `iniciar_dashboard.bat` (Python 3.12). Se abre el navegador y se reutiliza la lista guardada del perfil. No hace falta modificar ni borrar la instalación anterior. La primera ejecución instala dependencias fijadas y necesita Internet. [Detalles UTF-8, HTTPS y rutas Unicode](WINDOWS.md).

[Informe, pruebas, captura y limitaciones de esta ampliación](docs/seguimiento_completo_2026-11-16/INFORME.md). La ejecución interactiva documentada es en la nube, no en el ordenador personal del usuario; la PR queda abierta para su comprobación.
