# Consolidación de V7 y compatibilidad Windows — 13/11/2026

Esta entrega continúa la V7 integrada `9f9eedac970712e2f01b56d119290daec62425e7`. Corrige infraestructura de ejecución sin cambiar el modelo económico. El usuario autoriza fusionar primero PR #2 en la rama V6 y después PR #1 en `main`, una vez aprobados todos los controles. No se usan fusiones forzadas, bypass de comprobaciones ni sobrescrituras de otras ramas.

## Correcciones

- `entorno_ejecucion.py` centraliza UTF-8 para el proceso actual y sus hijos. Dashboard, consola, motor y worker opcional configuran entradas/salidas y logs; los subprocesos declaran `encoding='utf-8'`. Capturas, configuraciones y supuestos se leen/escriben explícitamente en UTF-8.
- En Windows valida el PEM y sus autoridades CA. Respeta almacenes explícitos heredados; sin ellos utiliza `certifi`. Resuelve rutas Unicode mediante alias 8.3 si existe o una copia ASCII con permisos seguros si no existe.
- La carpeta de copia es nueva y aleatoria: se crea con una DACL protegida **en la misma operación nativa de creación**, sin una ventana con permisos públicos. Sólo el SID del usuario y SYSTEM reciben acceso; archivos hijos heredan esa ACL. No se reutilizan archivos/carpeta preexistentes. Se comprueba SHA-256 contra el PEM original y se elimina al terminar normalmente. No se instala ninguna CA en el sistema. Una terminación forzada puede dejar una carpeta privada residual que no se reutiliza.
- La verificación HTTPS permanece activa; no se usa `verify=False`. No se cambian versiones de dependencias. Linux y Streamlit Cloud conservan sus CA y proxy heredados.
- Diagnósticos diferenciados para CA local, SSL, conexión/timeout, límites Yahoo, denegación SEC 403 y respuestas incompletas. Un fallo de red no se transforma en dato financiero ni en permiso para saltar controles. Los JSON SEC de tipo incompatible fallan de forma explícita.
- `iniciar_dashboard.bat` identifica Python 3.12 x64, prepara/reutiliza `.venv`, verifica importaciones y versiones fijadas, completa dependencias y arranca el único Streamlit. Funciona desde el ZIP y no descarga/reescribe código. El PS1 antiguo delega en el mismo flujo. Los logs y el archivo del proceso usan UTF-8, incluido el cierre en PowerShell. No se reutiliza un servidor antiguo sin identificar su código.

## Validación local realizada

Primero pruebas relacionadas: **68 passed, 1 skipped**. Después toda la batería: **184 passed, 1 skipped**, dos advertencias esperadas de identidad SEC. Las tres suites heredadas también dan PASS. El único caso omitido localmente verifica la ACL nativa de Windows; Linux no permite acreditar esa API.

Las nuevas pruebas cubren subprocesos con stdin/stdout/stderr Unicode, ficheros y rutas con acentos/japonés/espacios/caracteres especiales, CA inválida, fallo de permisos, integridad de copia, alias, respeto de almacenes explícitos, errores SSL/conexión/403/429 simulados, SEC/Yahoo incompletos, arranque de Streamlit y persistencia de PER/crecimiento en una captura AMZN Unicode.

Una prueba HTTPS **real en localhost**, con curl_cffi y requests, utiliza la CA en una ruta Unicode y exige que una CA distinta sea rechazada. La clave/certificado de prueba son públicos, sólo se usan en el servidor temporal de localhost y no forman parte de la confianza de producción.

## Resultados financieros conservados

La comparación offline reutiliza las capturas ya archivadas, sin volver a descargar datos. Los **13 tickers** mantienen exactamente sus tablas de valoración EPS/PER, proyección, supuestos, controles por método, diagnósticos y disponibilidad de métricas respecto a las ejecuciones V6 archivadas. No se ajustan resultados contra la cotización.

| Ticker | Base 1 año antes → después | Base 3 años antes → después | Moneda |
|---|---:|---:|---|
| MSFT | 696,84 → 696,84 | 940,68 → 940,68 | USD |
| NVDA | 496,90 → 496,90 | 1.159,41 → 1.159,41 | USD |
| MU | 416,88 → 416,88 | 665,60 → 665,60 | USD |
| AMZN automático | No disponible → igual | No disponible → igual | USD |
| SK Hynix automático | No disponible → igual | No disponible → igual | KRW |

MSFT conserva seis objetivos. AMZN y SK Hynix mantienen PER manual y exploratorio cuando corresponda, con las advertencias y límites existentes. La prueba del PER manual conserva crecimiento y el resto de hipótesis; no elimina problemas de recurrencia, EPS, fuente, moneda o perímetro.

También se vuelve a comprobar el replay y la consistencia de las exportaciones Excel/JSON archivadas: **135.717 celdas** en los tres casos auto/manual/MSFT consultado previamente. Se conservan la tolerancia numérica 1e-10 y el redondeo XLSX de fechas hasta 1 ms ya documentados en V7. No se repite una descarga financiera que no es necesaria para estos cambios de infraestructura.

Evidencias: [pruebas relacionadas](pruebas_relacionadas.log), [batería completa](pruebas_completas.log), [comparación y exportaciones](comparacion_financiera.json), [hashes de módulos financieros](modulos_financieros.json). Las capturas y exportaciones completas continúan en [la auditoría V7 anterior](../v7_integrada_2026-11-13/INFORME.md).

## GitHub Actions y orden de consolidación

El workflow añade `pruebas_windows` a las pruebas Linux existentes. En Windows crea un ZIP desde el commit, lo extrae en una ruta `Álvaro 日本 V7` **sin `.git`**, instala Python 3.12/dependencias fijadas, ejecuta la batería completa y las suites heredadas y prueba el BAT real/health de Streamlit. Incluye la prueba nativa de DACL y el HTTPS local. No abre un navegador interactivo en el ejecutor.

El orden exigido es: validar [PR #2](https://github.com/AlvaroAlonsoLarre/valoracion-bursatil/pull/2/checks), fusionarla; validar de nuevo [PR #1](https://github.com/AlvaroAlonsoLarre/valoracion-bursatil/pull/1/checks), fusionarla; comprobar [el workflow en `main`](https://github.com/AlvaroAlonsoLarre/valoracion-bursatil/actions/workflows/main.yml). Los registros enlazados y el historial de ambas PR acreditan los commits/estados efectivos. Una comprobación fallida detiene la secuencia; no se fuerza su omisión.

## Ejecución y límites

[Instrucciones definitivas Windows sin Git](../../WINDOWS.md). El usuario ha confirmado que la V7 anterior funciona en su Windows 11 con Python 3.12; eso se distingue de las pruebas automatizadas de esta entrega. Las pruebas locales se hacen en Linux y la validación nativa corresponde al ejecutor Windows de Actions, no a una sesión interactiva de su ordenador.

Siguen vigentes las limitaciones económicas y de cobertura de la V7 verificada: confianza baja cuando falten comparables, datos Yahoo/SEC sujetos a disponibilidad, curvas intermedias ilustrativas y supuestos que requieren juicio económico. Redes corporativas con CA propias deben aportar un almacén aprobado; no se sortean sus certificados ni las denegaciones de acceso. Se conservan los controles financieros, seis pestañas, gráficos, exportaciones y escenarios de un único motor.
