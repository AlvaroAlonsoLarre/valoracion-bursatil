# V7 integrada · dashboard fundamental de acciones

Análisis del negocio y escenarios de precio a **1 y 3 años**, con foco en acciones de Estados Unidos y soporte multiempresa/multibolsa. SEC es la fuente anual principal; Yahoo aporta cotizaciones, trimestres, acciones corporativas y datos complementarios. Las fuentes oficiales específicas conservan su auditoría.

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.lock
.venv/bin/streamlit run dashboard_app.py
```

En Windows consulta las [instrucciones de ejecución directa](WINDOWS.md); siguen disponibles `iniciar_dashboard.bat` y `iniciar_dashboard.ps1`. El dashboard contiene seis pestañas: **Resumen, Histórico, Trimestrales, Comparables, Valoración y Datos y auditoría**. Puede consultar un ticker o abrir una captura auditada JSON sin red. La captura de ejemplo tiene fecha explícita; no representa una cotización en tiempo real. [Informe V7, pruebas y captura de pantalla](docs/v7_integrada_2026-11-13/INFORME.md).

## Modelo principal

Se proyectan ingresos TTM, crecimiento previsto, margen normalizado, resultado no operativo, impuestos y acciones diluidas. `growth_terminal` y `margin_terminal` permiten una transición lineal desde el año 1 hasta el año 3. En ciclos y crecimientos excepcionales se usan CAGR compuestos de hasta 5 FY, con desaceleración al menor CAGR de hasta 5/10 FY al año 3. El margen parte de la mediana normalizada de hasta 5 FY; el TTM de pico no se extrapola de nuevo sobre ventas TTM ya elevadas. Las acciones históricas se llevan a la base de splits vigente antes de medir dilución. Los tres escenarios son hipótesis editables, no probabilidades. **EPS proyectado × PER razonable** produce los precios; el precio actual no recalibra sus parámetros. Los impuestos no generan un crédito automático si el PBT es negativo.

El margen se normaliza con la mediana de hasta cinco FY; el resultado no operativo se obtiene de PBT−EBIT y no se presenta como interés puro. Si el emisor no publica una serie EBIT suficiente, se identifica un modelo PBT directo, con financiero ya incluido. No se inventa EBIT. Para bancos y aseguradoras se usa PBT directo y se advierte sobre capital regulatorio/provisiones; FCF/FCFF/EV genéricos no se aplican. Los REIT requieren FFO/AFFO/NAV documentados. EPS negativo exige un caso de recuperación justificado; no se valoran pérdidas con PER positivo.

El PER se obtiene de comparables con evidencia suficiente o del histórico propio (mediana y cuartiles de cinco FY, mínimo tres observaciones; alternativa diez FY, mínimo cinco). El histórico propio se marca con menor confianza. Se conserva cobertura y estadística a **5 y 10 ejercicios**. Se concilian acciones, EPS, splits y beneficio común/continuado. Sin FX histórico o base ADR histórica no se calculan múltiplos incompatibles. Los cierres de primera semana de enero se identifican como el FY de diciembre, manteniendo siempre la fecha real de 52/53 semanas.

Los comparables se descubren por actividad; se prefieren **3–6**, sin forzar el mínimo. PER TTM y NTM tienen evidencia y filtros separados. Un PER TTM valora el EPS de los doce meses hasta el horizonte; NTM requiere EPS de los doce meses posteriores. FY1 o `normalized` del proveedor no se renombra como GAAP NTM. Se conservan candidatos descartados y motivos.

**Precio/FCF** sirve de contraste actual cuando OCF−CAPEX es completo, positivo y representativo (mínimo tres FY positivos y conversión FCF/neto entre 0,5 y 2). No se confunde con EV/FCF ni se extrapola automáticamente. EV/EBITDA y DCF se calculan sólo si se solicitan; sus controles no bloquean el EPS/PER que disponga de sus propios datos. La implementación anterior se conserva para estos análisis y para reproducir auditorías antiguas.

## Escenarios, criterios y exportación

En Valoración se editan crecimiento, margen EBIT/PBT, fiscalidad, resultado no operativo y variación de acciones. En Resumen se elige PER automático o manual: Base, distancia pesimista/optimista y justificación. Con dos referencias históricas económicamente válidas puede activarse explícitamente una valoración exploratoria de confianza Baja; con cero/una, un PER manual justificado requiere igualmente EPS válido y todos sus controles contables. Aplicar PER conserva los demás ajustes. Para ADR se exige ratio ordinarias/ADR, fuente y fecha. WACC y g terminal opcionales no cambian el motor principal.

Resumen muestra cotización archivada de 1 semana, 4 meses o 1 año y tres líneas discontinuas opcionales a 1 mes, 4 meses, 1 año o 3 años. Los extremos a 1/3 años proceden del motor EPS × PER; los intermedios son interpolaciones ilustrativas. Se mantienen horizontes disponibles si falta otro, sin extrapolar objetivos ausentes.

La referencia razonable hoy es el precio Base a un año descontado al retorno exigido editable; no se promedian métodos. Los potenciales son retornos de precio, sin dividendos, costes ni impuestos personales. La clasificación de atractivo exige más descuento cuanto menor sea la confianza y mayor sea la dispersión. Los umbrales de retorno, margen, prima de reducción, caída tolerada y peso máximo son transparentes y editables. La posición es opcional y debe estar en la moneda de cotización. Los datos de coste no cambian el valor del negocio. Las señales son orientativas y no envían órdenes.

Excel, resultados JSON y captura reproducible JSON exportan el mismo análisis visible y sus supuestos. Los cinco estados son `DISPONIBLE`, `ESTIMADO`, `ADVERTENCIA`, `NO DISPONIBLE` y `BLOQUEADO`. La tabla de disponibilidad explica cada indicador; una falta de PER no impide proyectar EPS, ni una discrepancia de capitalización invalida resultados por acción. La capitalización y las clases mantienen controles propios para EV. Nunca se rellenan huecos con cero para obtener un precio.

## Terminal y verificación

```bash
python ejecutar_analisis.py --ticker MSFT --outdir Resultados/MSFT
python ejecutar_analisis.py --ticker 000660.KS --outdir Resultados/SK
python ejecutar_analisis.py --ticker JNJ --outdir Resultados/JNJ
python ejecutar_analisis.py --ticker JPM --outdir Resultados/JPM
python ejecutar_analisis.py --ticker MSFT --advanced --outdir Resultados/MSFT_opcionales
python ejecutar_analisis.py --snapshot Resultados/MSFT/MSFT_inputs.json --outdir Resultados/replay
python ejecutar_analisis.py --snapshot Resultados/MSFT/MSFT_inputs.json --assumptions mis_supuestos.json --outdir Resultados/editado
python -m pytest -q tests
python autoprueba_modelo.py
python prueba_comparables_automaticos.py
python test_v5.py
```

Ejemplo de supuestos parciales; tasas decimales, no porcentajes:

```json
{"scenarios":{"Base":{"growth":0.08,"margin":0.30}},"policy":{"required_return":0.10},"advanced":false}
```

Sólo se aceptan claves reconocidas y números finitos. Un PER manual exige `per_reason`; al cambiar a NTM se deben especificar los tres PER. `optional_assumptions` admite `wacc` y `terminal_growth`. Las hipótesis no son datos reportados. Los snapshots antiguos mantienen su replay V7 y no reciben referencias históricas inventadas.

Cada ejecución conserva entradas, Excel, resumen y log. Código **0**: algún método condicional disponible; **2**: insuficiencia financiera; **1**: fallo técnico. Un contraste FCF no equivale a un objetivo futuro. Los estados por método y el número de objetivos principales evitan confundir ambos casos. `publicable=false` conserva el carácter condicional del análisis.

Si el índice ticker–CIK de SEC devuelve 403, se obtiene una pista de CIK de los enlaces de filings y se exige ticker exacto en submissions oficial antes de descargar CompanyFacts. La pista no sustituye la validación de identidad ni las cuentas SEC.

El workflow `.github/workflows/main.yml` ejecuta pruebas rápidas sin descargas financieras en cada PR. La matriz completa de **13 tickers** se ejecuta manualmente (`workflow_dispatch`, vacío = muestra completa) o semanalmente; admite también un ticker nuevo. Una insuficiencia financiera documentada (salida 2) conserva artefactos y no equivale a error técnico. La matriz incluye MSFT, NVDA, AMZN, NFLX, META, GOOGL, GOOG, MU, SNDK, SPCX, JNJ, JPM y 000660.KS. No escribe resultados en `main` ni fusiona PRs. Usa un contacto SEC real mediante `SEC_CONTACT_EMAIL` si dispones de él; el identificador por defecto es el nombre del software, sin correo ficticio.

Los informes de [11/11](docs/auditoria_2026-11-11/INFORME.md) y [12/11](docs/auditoria_2026-11-12/INFORME.md) documentan las etapas anteriores. No se modifican sus cifras históricas para presentarlas como resultados del nuevo modelo. La nueva comparación y sus límites se documentan en `docs/v6_simplificada_2026-11-12/INFORME.md`.

La conciliación `Conciliacion SEC Yahoo` conserva ambos importes, unidades, conceptos, componentes YTD, URL y hash. Una fecha fiscal semanal sólo sustituye a la de calendario si al menos dos flujos concilian a menos del 1%. Los prospectos SEC sin CompanyFacts anual tienen un extractor limitado a tablas consolidadas con periodo anual y escala expresa; no se inventan conceptos XBRL ni cotizaciones anteriores a una IPO. Los registros de separación excluyen el periodo anterior a cotizar de los supuestos automáticos mientras no se acredite continuidad económica.

Validación ampliada con trece tickers, tablas de cobertura, estados oficiales de IPO y artefactos completos: [informe de generalización V6](docs/v6_generalizada_2026-11-12/INFORME.md).


La revisión económica conserva PER y beneficios reportados, pero califica qué ejercicios sirven para la referencia: ganancias financieras identificadas u otros no operativos sin recurrencia acreditada >10% del PBT, fiscalidad atípica (>10 puntos respecto a la mediana), beneficios cíclicos de pico/valle y cambios de régimen de margen. No se reducen los mínimos de observaciones ni se rellena el histórico con periodos anteriores a un cambio material de régimen. Si faltan referencias limpias, el PER manual debe justificarse.

Cuando hay resultados financieros materiales, se proyecta el puente de intereses identificados (ingreso menos gasto puro) si hay evidencia suficiente; otros resultados no se suponen recurrentes. El desglose oficial conserva ganancias de inversiones, periodos, unidades, URL y hash; no se inventa un impuesto ni un EPS ajustado. Las financieras mantienen tratamiento propio.

Valoración incorpora dos tablas compactas: sensibilidad aislada a crecimiento, margen y PER, y expectativas implícitas en la cotización manteniendo el resto de supuestos Base. Esta inversión de las ecuaciones es un contraste, no recalibra el modelo. Resumen muestra los extremos de crecimiento/margen y el PER junto a los precios.

La [revisión económica final](docs/economia_final_2026-11-12/INFORME.md) compara precios antes/después, normalización de ciclos, extraordinarios de inversiones y calidad del PER. Incluye sensibilidad, validación de los trece tickers y paridad de exportaciones.


La V7 integrada parte de la V6 verificada `b50a51d` y utiliza los mismos módulos financieros. [Ejecución Windows](WINDOWS.md). El gráfico utiliza cierres archivados a una semana/cuatro meses/un año y permite ocultar o mostrar escenarios a uno/cuatro meses/un año/tres años; los puntos intermedios son interpolaciones ilustrativas, nunca un motor mensual alternativo. Los objetivos de uno/tres años son exclusivamente los del motor EPS × PER.

El PER manual se configura en Resumen, con distancias pesimista/optimista y justificación. Sus cambios conservan todos los demás supuestos. La referencia de dos PER limpios es una opción exploratoria explícita de confianza Baja; con cero o uno se necesita un PER manual justificado. Nunca evita requisitos de EPS, divisas, acciones o contabilidad.
