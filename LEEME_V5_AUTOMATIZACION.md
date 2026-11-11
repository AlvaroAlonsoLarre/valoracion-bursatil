# Dashboard V5 — comparables y control de actualidad

## Qué cambia

- **Una sola puntuación del universo completo** de candidatos de Yahoo. No se recorta a diez antes de valorar el negocio.
- La clasificación utiliza perfiles textuales, actividad (memoria, fundición, software empresarial, ciberseguridad, etc.), industria, márgenes y crecimiento. No depende de catálogos de tickers.
- Solo los candidatos **Media/Alta** participan en múltiplos; no se fuerza un número de pares y se exige **mínimo 3 por múltiplo**.
- PER y EV/EBITDA se validan independientemente; la mediana robusta se acompaña de recuento y dispersión.
- Si no existen referencias económicas, la valoración por múltiplos muestra N/D. El PER de la propia empresa se conserva **solo para referencia**, no como sustituto de sus comparables.
- Nueva hoja **Actualidad resultados**: con SEC identifica 10-Q/10-K más recientes que el trimestre Yahoo y bloquea la valoración fundamental. Los 8-K de resultados y el calendario de Yahoo solo generan **REVISAR** (no demuestran por sí solos un trimestre nuevo).
- El dashboard conserva SEC 10 años, controles Yahoo/SEC, histórico, TTM, proyecciones, DCF, riesgos y Excel.

## Windows, sin GitHub

1. Extrae el ZIP en una carpeta nueva, sin cambiar la distribución interna de archivos.
2. Abre `dashboard_valoracion_yahoo` y haz doble clic en `iniciar_dashboard.bat`.
3. Introduce el ticker (`MSFT`, `000660.KS`, etc.), 12 trimestres y correo SEC.
4. Se guardará un Excel en `Resultados` (carpeta de la app).
5. Alternativa terminal desde la carpeta: `python ejecutar_analisis.py --ticker MSFT --num-quarters 12 --outdir Resultados`.

## Sin volver a subir Excel: GitHub Actions + ChatGPT

1. Crea un **repositorio privado** de GitHub. Sube el CONTENIDO de `dashboard_valoracion_yahoo` a su raíz. Es importante incluir la carpeta **`.github/workflows`**.
2. En GitHub, ve a Settings > Secrets and variables > Actions > New repository secret. Crea `SEC_CONTACT_EMAIL` con tu correo de contacto. No guardes credenciales ni ese correo en código publicado.
3. En GitHub, abre **Actions > Valoración bursátil V5 > Run workflow**. Escribe el ticker, el número de trimestres, y decide si quieres activar **publicar_resumen**.
4. Cada ejecución descarga datos online mediante GitHub Actions y crea Excel, JSON y registro como artefacto descargable (retención solicitada: 30 días).
5. Si seleccionas **publicar_resumen=true**, el archivo `Resultados_publicados/MSFT.json` (o ticker equivalente) se guarda en el repositorio. Desde ChatGPT con acceso autorizado a GitHub podrás pedir revisión de ese JSON y del código, sin copiar Excel. **No publica el Excel**. En un repositorio público el JSON también sería público: recomendamos uno **privado**.
6. Conecta GitHub en ChatGPT; solicita analizar código del repositorio, resultados JSON y registros de GitHub Actions. Si las acciones disponibles no permiten recuperar el artefacto, usa ChatGPT **Work** o **Codex** con permisos de código/Internet, o el navegador de Work para abrir GitHub y descargarlo. La conexión GitHub no garantiza poder ejecutar Python automáticamente en este mismo chat.

**Nota**: puede que sea necesario habilitar escritura de GitHub Actions en Settings > Actions > General > Workflow permissions. Si la rama principal tiene protección, el commit de JSON podría fallar. Puedes mantener `publicar_resumen=false` y usar el artefacto.

## Límites reales

- En este chat, el entorno Python de análisis no tiene acceso directo a Yahoo/SEC. La búsqueda web consulta páginas públicas, pero no equivale a ejecutar arbitrariamente el motor con `requests` y `yfinance`.
- **Work/Codex** pueden ejecutar el repositorio en un entorno adecuado, y GitHub Actions lo hace bajo tu cuenta. La posibilidad de acceder a Internet depende de permisos/plan. Yahoo puede limitar tráfico de datacenters, y SEC requiere User-Agent identificable.
- La clasificación de actividad es heurística y no conoce porcentajes auditados por segmento. En empresas diversificadas debe revisarse. Ningún precio objetivo es una predicción garantizada.
- Las tasas WACC, CAGR, CAPEX, impuestos y múltiplos requieren revisión económica; no se incorporan automáticamente consenso ni guidance. Si no se puede verificar vigencia, el sistema indica REVISAR/NO_VERIFICADO.

## Pruebas locales (sin Internet)

`python autoprueba_modelo.py`

`python prueba_comparables_automaticos.py`

`python test_v5.py`

La ejecución real requiere Yahoo/SEC online; no se validó desde el entorno de preparación de este paquete.
