# Netflix, diez comparables y medianas — 17-11-2026

## Problemas corregidos
- La clasificación económica no reconocía vídeo/televisión/streaming, por lo que Netflix podía quedar sin pares aun teniendo candidatos de Yahoo.
- Mi seguimiento mostraba la media de pares estrictamente verificados. Esa columna podía quedar vacía mientras existían ratios informativos en otras columnas.
- El máximo de cinco podía dejar muy pocas observaciones de PER si algunos emisores tenían pérdidas o datos ausentes.

## Comportamiento
- Hasta diez emisores económicos únicos. Se excluyen empresas incompatibles; cada múltiplo conserva sus ausencias.
- La columna principal muestra la mediana de PER TTM verificados homogéneos; si no existe una referencia válida, muestra la mediana TTM Yahoo informativa con origen y N explícitos. No usa forward para rellenar TTM.
- Las columnas de comparables TTM, forward y EV/EBITDA de Mi seguimiento usan mediana. No se trasladan ratios informativos automáticamente a precios objetivo.
- Vídeo/entretenimiento tiene una categoría propia y un catálogo de respaldo Netflix revisable, con comparación parcial documentada. La búsqueda sigue descargando y filtrando perfiles; no garantiza diez pares con ratios completos.
- Las métricas guardadas migran de esquema 3 a 4 al abrir, sin red ni borrar supuestos ni fechas. La configuración de columnas incorpora N y origen.
- Una búsqueda antigua puede requerir Forzar actualización completa para consultar más candidatos. La lista local y los ajustes se conservan.

## Validación
Se añaden pruebas de diez emisores, exclusión de música sin vídeo, medianas ante valores ausentes/atípicos, separación TTM/forward y migración de capturas sin red.
GitHub Actions ejecuta las pruebas Linux/Windows y una comprobación con perfiles actuales de NFLX que exige al menos tres empresas y tres PER TTM positivos. La cobertura exacta y sus fuentes se guardan como artifact comparables-netflix del run; una cobertura insuficiente falla, no se presenta como éxito.

Los pares de estudios/TV, plataformas de publicidad, conglomerados y emisores de otros países son parciales: no reproducen todos los márgenes, costes de contenido, apalancamiento y mercados de Netflix.

## Consulta observada del 17-11-2026
La prueba local descargó perfiles actuales de Netflix y sus candidatos. La selección final obtuvo 8 emisores relacionados: DIS, WBD, CMCSA, FOXA, ROKU, VSNT, IQ y 035760.KQ. En la política de moneda vigente, 5 PER TTM positivos aportan una mediana de 14,457447×; la media era 20,10434312×. No se sustituyen los TTM ausentes de WBD/IQ/CJ ENM por forward, ni se mezclan en el resumen las monedas discrepantes. Se excluyó Formula One por predominio de derechos/eventos deportivos.

Yahoo limitó parte de las consultas y no hubo cobertura suficiente para diez emisores: se conserva la advertencia 8/10, sin añadir empresas incompatibles. Las fuentes originales, fechas y errores están en evidencia_NFLX.zip; la tabla está en NFLX.csv. Son ratios descriptivos de proveedor, sin validación para objetivos. Las dos primeras pruebas nuevas (vídeo y mediana con ausencias) pasaron localmente; las pruebas con capturas completas y Windows se comprueban en GitHub Actions.
