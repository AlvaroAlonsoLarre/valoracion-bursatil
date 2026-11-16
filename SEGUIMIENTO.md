# Mi seguimiento

La primera pestaña del dashboard conserva una lista de acciones y sus últimas capturas V7. Las seis pestañas anteriores y sus exportaciones siguen disponibles.

## Uso

1. Escribe parte del nombre o el ticker en **Buscar empresa o ticker**. La búsqueda Yahoo admite coincidencia aproximada y ordena las coincidencias por nombre/ticker. Selecciona la compañía y comprueba su bolsa antes de **Añadir empresa confirmada**. No se agregan ETF ni duplicados.
2. La primera consulta puede tardar porque ejecuta el mismo motor V7. Desmarca **Descargar datos al añadir** si sólo quieres preparar la lista.
3. También puedes **Guardar empresa y ajustes del análisis abierto** para añadir una captura sin red, incluidos PER manual y supuestos personalizados. Se conserva la fecha original de sus datos; guardar no los convierte en datos de hoy.
4. Ordena por las cabeceras, desplázate horizontalmente y elige las columnas que quieres ver. La selección de columnas se guarda automáticamente. Seleccionar una fila abre su captura en **Resumen**, restaurando sus ajustes.
5. Usa **Actualizar empresa** o **Actualizar todas**. Los datos con caché vigente se reutilizan. **Forzar todas las fuentes** ignora las caducidades y puede realizar muchas consultas: úsalo sólo cuando sea necesario confirmar una publicación o revisar un fallo.
6. Consulta los desplegables de detalle para ver periodos, fuentes, componentes SEC, cobertura, mediana/N de comparables y motivos de exclusión. **Eliminar empresa** la retira de la lista y elimina su captura guardada; la caché pública de fuentes puede permanecer.

Cambiar pestañas, ordenar o modificar las columnas no descarga estados. Si falla una actualización se conserva la última captura y aparece **Desactualizado**, con el error y la fecha de la última actualización válida. Una empresa sin ninguna captura conserva también el diagnóstico del primer fallo.

## Qué significan las columnas

- **PER actual TTM**: el que ya calcula la tabla de disponibilidad de V7 sobre EPS diluido TTM y la base de cotización/ADR/FX admitida. No se sustituye por PER forward ni por el `trailingPE` sin validar de Yahoo. Es EPS reportado, no necesariamente recurrente; las ganancias de inversiones identificadas se advierten.
- **PER mediana 5 FY**: estadística de V7, excluyendo observaciones rechazadas por su auditoría de base por acción, extraordinarios, pérdidas, fiscalidad, ciclo o cambio de régimen. Se muestra su cobertura; menos de tres FY limpios no se convierte en referencia automática suficiente.
- **Descuento PER (%)**: `(mediana FY − PER TTM) / mediana FY × 100`, sólo con ambos múltiplos positivos disponibles. Verde y signo `+` si el TTM es menor; rojo y signo `−` si es mayor. Contrasta FY con TTM de forma explícita: no es una rentabilidad esperada ni una señal de compra. Los extraordinarios del TTM pueden distorsionarlo.
- **PER comparables TTM**: media sobre al menos tres emisores únicos económicamente elegibles, con TTM y moneda compatibles y evidencia aprobada por V7. No se completa el número con empresas rechazadas ni con NTM. El detalle presenta por separado el PER NTM, la mediana, N y advertencias. Se rechazan cohortes/perímetros mezclados y dispersión excesiva.
- **QoQ neto**: neto reportado de un trimestre fiscal frente al inmediatamente anterior. Se exige cadencia de 70–105 días y continuidad de los componentes oficiales, sin periodos artificiales de cuatro meses. No hay porcentaje si falta un dato, existe conflicto o el denominador es cero/negativo. Una caída desde beneficio a pérdida sí conserva su porcentaje y contexto.
- **Histórico QoQ 5 años**: hasta 20 variaciones de los cinco años que terminan en el último cierre disponible. Puede necesitar un cierre anterior adicional. Se intenta completar con CompanyFacts SEC y el reconstructor YTD aditivo existente: Q2 = 6m−3m, Q3 = 9m−6m y Q4 = FY−9m, con mismo inicio fiscal, unidad/concepto y componentes publicados antes del corte. No se diferencia EPS ni medias de acciones. Las discrepancias SEC–captura invalidan ese dato. Se muestran media, mediana y variaciones válidas/20; no se inventan trimestres si Yahoo/SEC no los aportan. Son cambios del beneficio reportado, sensibles a estacionalidad y extraordinarios, no una previsión recurrente.
- **EV/EBITDA FY**: las columnas de último FY y mediana 5 FY permanecen no disponibles cuando V7 no acredita el puente EV al cierre, D&A consolidada pura y el perímetro histórico. Actualmente las capturas V7 no exportan ese múltiplo FY auditado: esta extensión no fabrica un cálculo nuevo ni convierte el EV/EBITDA aproximado del Excel heredado en dato validado.
- **EV/EBITDA comparables NTM**: sólo referencias que V7 ya considera admisibles, en una cohorte homogénea. Nunca se presenta esa media NTM como si fuese FY o TTM. Se detallan mediana, N, fechas y perímetro; puede no haber suficientes comparables.

Una celda ausente no es cero. Precio, moneda, fecha de cotización, último cierre financiero, origen, estado y advertencias acompañan a las métricas.

## Persistencia y rendimiento

La lista, preferencias, últimas capturas válidas, diagnósticos y caché se guardan en una base SQLite local con transacciones y JSON, sin `pickle`. Por defecto se usa la carpeta de datos del usuario `ValoracionBursatil/seguimiento` (Windows: dentro de `%LOCALAPPDATA%`). La pestaña muestra la ruta exacta. Sobrevive al cierre de Streamlit y a las actualizaciones del código. La lista está vacía al instalar; las empresas de las capturas de documentación son ejemplos, no se incorporan automáticamente.

Caducidades:

| Fuente/componente | Caducidad |
|---|---:|
| Cotizaciones y fast_info | 15 minutos |
| Búsquedas y submissions SEC | 1 hora |
| Estados del objetivo y CompanyFacts SEC | 24 horas |
| Estados/información de comparables | 72 horas |
| Histórico de precios y directorio de tickers SEC | 7 días |

Los fallos y respuestas financieras vacías no se guardan como descargas válidas. La actualización completa sólo se ejecuta si no hay captura, caducan los estados o se fuerza; en otro caso se actualiza la cotización y se reutilizan estados y referencias. El adaptador de fuentes sólo se activa en esta ruta; los análisis V7 habituales conservan su comportamiento. Los logs de consultas están en `logs/TICKER.log` dentro de la carpeta de seguimiento.

Para una copia de seguridad cierra el servidor y copia la carpeta completa; también puedes descargar **Exportar lista y capturas de seguimiento** para inspección/archivo JSON. Para elegir otra ubicación configura `VALUACION_WATCHLIST_DIR` antes de arrancar (opcional, no necesario para el uso normal).

La lista es local al usuario del sistema que ejecuta Streamlit. En un servidor compartido se comparte la lista de esa instalación: utiliza una instancia propia para datos personales; no se añade un sistema de usuarios/autenticación. En Streamlit Cloud la durabilidad del disco depende del alojamiento: exporta tu copia antes de reinicios/recreaciones del contenedor.

Se conservan las correcciones [Windows UTF-8 y HTTPS](WINDOWS.md). No hay dependencias nuevas ni instaladores por parches.
