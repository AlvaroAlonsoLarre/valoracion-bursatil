# Cambios del documento «Modificaciones a realizar en el dashboard»

Se aplica la presentación solicitada en Mi seguimiento, Resumen, Histórico, Trimestrales y Comparables. Los textos explicativos pasan a botones ⓘ alineados a la izquierda del bloque. Las fechas de mercado/actualización y las incidencias que necesitan una acción siguen visibles. Las exportaciones conservan las cifras originales y los campos de auditoría.

- Diferencia PER con histórico = (PER actual / mediana histórica 5 FY − 1) × 100. Negativo verde y positivo rojo. No mide directamente infravaloración.
- Agregar, eliminar e importar empresas queda encima de la tabla; los nombres QoQ pasan a Benef. neto en sus encabezados. Las columnas técnicas indicadas pasan a ser opcionales. Las preferencias personalizadas se conservan; el antiguo conjunto completo predeterminado migra al nuevo compacto.
- Se añade mediana EV/EBITDA comparables TTM Yahoo informativa. No sustituye el dato NTM verificado ni alimenta precios objetivo. Sólo usa valores positivos disponibles según la política de moneda existente; el N se conserva como columna opcional.
- Resumen añade diez métricas únicas (los campos duplicados en el documento no se repiten). Los múltiplos se etiquetan TTM/LTM y aproximados cuando corresponde; no se anualiza un único trimestre. El BPA es diluido TTM.
- Histórico muestra pares Media 5/10 años, Mediana 5/10 años y CAGR 5/10, con disponibilidad n/5 y n/10 al final. Cobertura completa y ejercicios disponibles son opcionales. Cada indicador comparte escala entre las ventanas de 5 y 10 años.
- Se aplican las listas de columnas eliminadas de la vista y ocultas por defecto en cuentas anuales y trimestrales. No se borran de los datos originales. Fechas YYYY/MM/DD sin hora.
- Comparación SEC-Yahoo agrupada en desplegables por cierre trimestral; sin fuente, hash o componentes en esa vista.
- Barras trimestrales más estrechas y eje categórico sólo con fechas presentes. El eje usa fechas del calendario Yahoo cuando están completas, entre 1 y 90 días después de cada cierre y no son futuras; se identifican como registradas/estimadas. Si no existe esa cobertura, muestra cierres fiscales y explica el motivo, sin inventar fechas de presentación.
- Comparables informativos sin columnas técnicas indicadas ni segunda tabla de controles de valoración. El universo y las fuentes completos siguen disponibles en sus desplegables y exportaciones.
- Formato español: punto de millares y coma decimal. K = miles, M = millones, MM = miles de millones, con símbolo de moneda cuando la columna tiene moneda única. Las tablas con magnitudes mixtas muestran la unidad por fila para no expresar un BPA como millones ni un ratio como dinero. Las columnas de monedas múltiples conservan las monedas por empresa y no se convierten implícitamente.

## Respuestas a las preguntas del documento

**EV/EBITDA Yahoo:** dato enterpriseToEbitda del proveedor, normalmente TTM/LTM. No es el múltiplo al cierre fiscal ni un NTM verificado. Su ventana exacta no está acreditada por el mero campo.

**EV/EBITDA último FY:** cálculo histórico con precio cercano al cierre fiscal, capitalización histórica, deuda y efectivo del mismo FY y EBITDA anual de ese FY. Cuando utiliza acciones medias o D&A no completamente reconciliada se identifica como aproximado. Puede faltar cuando falla un componente; no se sustituye una ausencia por cero.

**Calidad EV FY:** indica el tipo del cálculo y la confianza en sus componentes (por ejemplo, histórico aproximado/confianza Baja). No acredita una auditoría externa.

**Comparables B:** ratios descriptivos de empresas relacionadas, no aceptados automáticamente por los controles de valoración. Tener precio y PER no acredita igual negocio, periodo, perímetro contable o recurrencia de beneficios. La mediana reduce extremos pero no elimina esas diferencias.

**Acciones diluidas medias:** media ponderada del periodo que utiliza el BPA diluido. Incluye la dilución que procede por opciones, RSU o convertibles y excluye instrumentos antidilutivos; no son las acciones exactas al cierre ni todas las opciones existentes.

**Referencia de precio y base de acción de cada ejercicio:** enlaza ejercicio, fecha fiscal, precio, BPA, acciones y factores de split para evitar mezclar bases incompatibles al calcular PER histórico. Es retrospectiva, no un backtest point-in-time.

**Disponibilidad de métricas:** tabla de estado por indicador, valor, periodo y motivo de ausencia o advertencia. **Base TTM y balance:** desglose de los flujos sumados de cuatro trimestres y magnitudes del último balance. La primera explica la suficiencia; la segunda muestra la base numérica. Un EBITDA aproximado disponible no implica que un EV/EBITDA formal esté validado.

Las comprobaciones de esta modificación se ejecutan en Windows; no se añade ninguna batería Linux.
