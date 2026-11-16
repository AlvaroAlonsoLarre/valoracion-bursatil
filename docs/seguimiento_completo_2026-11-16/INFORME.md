# Mi seguimiento completo — 16/11/2026

Continuación de `feat/mi-seguimiento` desde `a1859325c5f8e29e7a31591f92e9cb2435d1427e`, conservando su lista/caché y las seis pestañas V7. `main` permanece en `40e1a0575da0de75231db8d8eed62a1a12b79343`. **PR #3 abierta, sin fusión ni auto-merge; pendiente de comprobación visual en el ordenador del usuario.**

## Cambios y límites financieros

- Un único gráfico principal en Mi seguimiento, antes de la tabla, reutilizando `grafico_cotizacion.py`. Selector de empresas guardadas sin red, tres ventanas históricas y cinco horizontes; interpolaciones intermedias explícitas. Resumen conserva todos sus controles y valoraciones. Se restauran captura, moneda y supuestos por empresa; aplicar ajustes los persiste sin sustituir otros datos.
- EV/EBITDA Yahoo separado de FY y de NTM. La fórmula EV histórica de `valoracion_engine.py` se extrae a una función compartida sin cambiar la aritmética del motor heredado. El seguimiento valida fecha, acciones/splits, moneda, deuda, efectivo y D&A. Prefiere acciones instantáneas oficiales SEC; las guarda con su evidencia en la captura para reproducir importación/edición sin red. Medias diluidas, deuda parcial y D&A reportada no conciliada quedan como aproximación de confianza baja. Sin deuda/efectivo, FX histórico, puente ADR/clases o EBITDA positivo suficiente, sigue mostrando ausencia. La mediana no mezcla perímetros de leases distintos. Ningún cálculo se presenta como auditado.
- Comparables **A**: controles estrictos V7 sin relajarlos. **B**: hasta seis relacionados, ratios brutos Yahoo y medias/medianas/N descriptivos, incluso N=1, con confianza baja. PER TTM y forward separados; forward no se declara NTM verificado. Monedas incompatibles y múltiplos no positivos quedan fuera de las medias. Se muestran candidatos, fechas consultadas/cierre reportado cuando existen y motivos de insuficiencia A. B no entra en objetivos.
- La incorporación confirmada ejecuta V7 completo y guarda lo utilizable. Actualización incremental por componentes: cotización según sesión, cierres recientes reutilizados o tramo faltante con solape, correcciones/deduplicación y serie completa ante splits. SEC comprueba accession/formulario/fecha cada hora; CompanyFacts conserva caducidad diaria, renovándose ante nueva presentación. Se comparan contenidos, también para estados Yahoo anuales y trimestrales sin SEC. No se confunde revisión del mismo FY con datos idénticos. Los candidatos/evaluación económica de comparables se reutilizan; sus evidencias/ratios caducan por separado. Forzar completo permanece disponible.
- Encabezado con hora local del navegador (UTC persistido), consulta de precios y estado de antigüedad. Fechas individuales del precio/resultados. Errores por componente conservan datos previos; los parciales válidos pueden guardarse y permiten descargar la captura anterior sin incidencias. Un fallo terminal no la sustituye.
- Tabla ordenable numéricamente, ausencias `—`, colores PER, importación/exportación de lista + capturas + ajustes + columnas, progreso y persistencia SQLite existente. Hasta 21 cierres almacenados para reproducir 20 QoQ sin red. Sin dependencias nuevas ni otro motor, aplicación, base de datos o instalador por parches.

## Resultados observados

Consultas Yahoo/SEC realizadas el **16/11/2026**; precios fechados, no garantía de tiempo real. [Evidencia detallada](consultas_reales.json) y [capturas reproducibles](capturas_msft_nvda.zip).

| Empresa | Precio USD | EV/EBITDA Yahoo | Último FY calculado | Mediana 5 FY | Cobertura FY | QoQ |
|---|---:|---:|---:|---:|---:|---:|
| MSFT | 522,56 | 19,251× | 14,3628× | 23,7060× | 5/5 | 20/20 |
| NVDA | 156,94 | 19,383× | 34,2190× | 43,6896× | 5/5 | 20/20 |

**Ambos FY son aproximados, confianza baja.** MSFT: deuda de la captura etiquetada como potencialmente parcial; EV podría infravalorarse. NVDA: además, D&A consolidada reportada sin conciliación completa. Se muestran componentes y advertencias por ejercicio, no se llaman datos auditados ni se incorporan al EPS/PER. Las diferencias frente al ratio Yahoo responden, entre otros factores, a FY frente a LTM y a definiciones/componentes distintos.

Las capturas anteriores de AMZN y SK Hynix también producen FY aproximado: último **17,0254× / 7,6891×**, mediana **18,5666× (5 FY) / 5,6833× (4 FY)**. Son datos archivados, no consultas nuevas de esas empresas. MU mantiene **—** por falta de deuda FY; no se supone deuda cero. ADR, financieras/REIT y perímetros insuficientes mantienen sus limitaciones.

B de MSFT: PER TTM media **75,49×**, mediana **24,16×**, N=5; EV/EBITDA media **25,98×**, mediana **17,49×**, N=5. La divergencia media/mediana evidencia valores extremos: estas medias descriptivas no son un PER razonable automático. El candidato KRW queda fuera de la media USD. B de NVDA: PER TTM media **102,75×**, mediana **95,20×**, N=4; EV media **50,63×**, mediana **34,79×**, N=5. Se conservan las mismas advertencias de periodos/perímetros no reconciliados.

En la traza real MSFT reutiliza estados vigentes y los cinco cierres de la consulta de precio; renueva evidencia A sin redescubrir candidatos y consulta ratios B. NVDA necesita una primera ejecución completa para disponer de firma de revisión de esta ampliación, utilizando las cachés de fuentes. Ninguna consulta busca calibrar las previsiones a la cotización.

## Comparación con V7 y exportaciones

| Empresa | Base 1 año antes → después | Base 3 años antes → después |
|---|---:|---:|
| MSFT | 696,840627 → 696,840627 USD | 940,681442 → 940,681442 USD |
| NVDA | 496,897950 → 496,897950 USD | 1.159,411097 → 1.159,411097 USD |

Los **13 tickers archivados** conservan valoración, EPS, supuestos, controles, diagnósticos y disponibilidad: MSFT, NVDA, MU, AMZN, META, GOOG, GOOGL, NFLX, JNJ, JPM, SK Hynix, SNDK y SPCX. No se rellena artificialmente la valoración de emisores con insuficiencia. [Comparación y exportaciones anteriores](comparacion_financiera.json): **135.717 celdas** Excel/JSON comprobadas.

Las capturas de las dos consultas actuales reproducen seis precios EPS/PER por empresa, sus extremos gráficos, FY y comparables B, y cobertura 20/20 tras importar sin red. Se comprueban **35.906 celdas adicionales** Excel/JSON. [Resultados](consistencia_actual.json). Reproducir sin descargas:

```text
python docs/seguimiento_completo_2026-11-16/validar_capturas.py
```

Las capturas conservan su procedencia original de ejecución sobre el árbol basado en a185932; no se reemplaza su commit histórico por el commit de entrega. [MANIFEST.json](MANIFEST.json) registra hashes del código/evidencias de esta entrega. El informe anterior y su manifiesto se conservan como historial, no como descripción de la ampliación actual.

## Pruebas

**243 pruebas pasadas y una omitida por ser exclusiva de Windows** en la [suite completa local](pruebas_completas.log); **59 pruebas de seguimiento** en el [pase focalizado](pruebas_seguimiento.log) y tres suites heredadas PASS. Casos nuevos: componentes FY, splits, GBP/GBp, FX/ADR, leases, deuda/efectivo ausentes, acciones SEC, ratios del proveedor, B separado de A, fechas, accession/revisiones de CompanyFacts y cashflow trimestral, reutilización de consultas, actualización parcial/fallos, importación transaccional Unicode, cobertura conservada, supuestos, gráfico único y selección sin descargas. Los tests V7 incluyen las **15 combinaciones** de ventanas gráficas y ausencia de objetivos.

Chromium/Streamlit real en la nube: hora Europe/Madrid, selector NVDA y gráfico a tres años, ausencia de duplicación en Resumen, ordenación numérica por precio y selección de NVDA correcta, descarga/importación de cinco capturas, viewport de 390 px sin desbordamiento global ni errores de página. [Registro](navegador.json), [captura](mi_seguimiento.png), [tabla ordenada](tabla_ordenada.png), [móvil](movil.png). La imagen combina MSFT/NVDA de las consultas descritas con MU/AMZN/SK de archivo, cada una con sus fechas.

La comprobación final **Linux y Windows/Python 3.12** se ejecuta en el workflow existente de la PR, incluyendo ZIP sin Git en ruta Unicode, HTTPS local, ACL de certificados y arranque real del BAT con respuesta HTTP. Sus resultados/enlace del commit final figuran en [los checks de PR #3](https://github.com/AlvaroAlonsoLarre/valoracion-bursatil/pull/3/checks), sin atribuirlos al PC personal del usuario.

## Instalación y pendientes

[Descargar ZIP de esta rama](https://github.com/AlvaroAlonsoLarre/valoracion-bursatil/archive/refs/heads/feat/mi-seguimiento.zip). Extraer **todo** en una carpeta nueva y hacer doble clic en `iniciar_dashboard.bat` con Python 3.12. Instala las dependencias fijadas y abre el navegador; no requiere Git. [Guía de uso](../../SEGUIMIENTO.md) y [Windows](../../WINDOWS.md). No se modifica ni borra la instalación anterior; la lista del mismo perfil se reutiliza.

**Pendiente:** comprobación visual en tu Windows 11 antes de fusionar. Esta entrega se ha ejecutado en la nube, sin acceso a tu escritorio. Permanecen la calidad aproximada FY indicada, posibles ausencias por fuentes/FX/ADR, periodicidad forward no acreditada de B, estacionalidad/extraordinarios del neto QoQ y los controles originales de valoración. El horario de caché no usa un calendario de festivos; una captura antigua con sólo 20 cierres y sin predecesor puede restaurar 19 QoQ. SQLite es local a la instalación/perfil; un servidor compartido no aísla usuarios web y el alojamiento efímero requiere exportar respaldo.
