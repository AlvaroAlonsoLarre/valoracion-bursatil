# Revisión Netflix y diseño — 17 de noviembre de 2026

## Ejecución y alcance

Fuente del código: rama fix/comparables-cinco, base a140af80. Ejecución completa nueva con `ejecutar_analisis.py --ticker NFLX --num-quarters 24`. Corte 17/11/2026; cotización 16/11/2026. Se revisan los resultados de Netflix, no se extrapola esta validación a todas las empresas.

## Resultados y sentido económico

| Magnitud | Resultado |
|---|---:|
| Precio observado USD | 60,75 |
| EPS TTM | 3,46 |
| PER TTM | 17,56× |
| Mediana informativa PER comparables | 14,46× (5 ratios positivos) |
| Mediana PER histórico propio, 5 FY | 40,57× |
| EPS Base a un año | 2,31 |
| Objetivo Base a un año | 93,86 USD (+54,5%) |
| Objetivo Base a tres años | 121,78 USD (26,1% anual) |
| Valor descontado Base desde un año, 10% | 85,33 USD |

La aritmética es reproducible. El objetivo automático no es una estimación robusta del valor intrínseco: depende de recuperar un PER de 40,57× frente a 17,56× actual, aunque el EPS proyectado a un año es inferior al TTM. El escenario pesimista también supone un PER alto (37,06×) y un precio a un año de 65,14 USD; no representa un estrés severo frente al precio actual.

Manteniendo el EPS Base a un año fijo, un PER de 20× da 46,27 USD (-23,8%); el PER actual da aproximadamente 40,62 USD y la mediana informativa de peers, 33,45 USD. Son sensibilidades de un solo supuesto, no objetivos alternativos validados. La mediana histórica refleja otro periodo económico y no garantiza reversión.

Hay 10 peers informativos, pero sólo 5 PER TTM positivos para esa mediana. El grupo económico formal tiene una empresa elegible y cero PER TTM/NTM verificados; no debe confundirse disponibilidad Yahoo con comparabilidad económica. La mediana reduce el efecto de extremos, pero no corrige negocios distintos o definiciones incompatibles. Los objetivos conservan confianza Baja/ESTIMADO y no publicable en la auditoría. DCF y EV/EBITDA formal siguen no disponibles.

## Conciliación de fuentes

De 165 filas Yahoo–SEC: 108 coinciden con diferencia inferior al 1%, 17 están marcadas por diferencias de al menos el 1% y 40 no son comparables o carecen de dato. No son 17 errores independientes:

- Tres filas de EPS/acciones de 2022 muestran bases de split distintas (factor 10). Netflix realizó un split 10:1 y comenzó a cotizar ajustada el 17/11/2025. Esto exige mantener coherentes precio, EPS y acciones al comparar históricos.
- Doce filas están relacionadas con el perímetro de D&A, EBITDA y ratios derivados entre 2022 y 2025. El 10-K 2025 presenta amortización de contenidos de 16.422,166 millones USD y D&A de inmovilizado/intangibles de 333,389 millones. Su suma coincide con el total Yahoo, mientras que el campo SEC utilizado excluye contenidos. Es una diferencia de definición; no prueba por sí sola un error del proveedor. La inversión en contenido tampoco equivale al CAPEX de inmovilizado.
- La deuda Yahoo 2021 sólo recoge 699,823 millones frente a 15.392,895 millones SEC: año histórico incompleto.
- El gasto de intereses 2023 difiere aproximadamente un 6,5%; no se ha conciliado.

Fuentes oficiales:
- https://ir.netflix.net/investor-news-and-events/financial-releases/press-release-details/2025/Netflix-Announces-Ten-For-One-Stock-Split/
- https://www.sec.gov/Archives/edgar/data/1065280/000106528026000034/nflx-20251231.htm

Conclusión: útil para explorar datos y sensibilidades con fechas y cobertura visibles. Confianza limitada en comparables y baja en objetivos automáticos. El +54,5% no es una rentabilidad esperada ni una probabilidad. Las curvas entre los objetivos a uno y tres años son interpolaciones, no previsiones mensuales independientes.

## Cambios de interfaz

Mi seguimiento: tabla → selector de empresa → gráfico → controles PER automático/manual. Resumen incluye el mismo gráfico y controles. Las hipótesis se guardan por empresa y se comparten entre vistas. Seleccionar fila conserva Mi seguimiento y actualiza el gráfico. Se muestra PER actual y PER Base supuesto para hacer visible la dependencia del múltiplo. Las fórmulas del motor no se han cambiado.

## Validación

Prueba AppTest con captura real nueva NFLX: orden tabla/gráfico/PER, claves de controles independientes, persistencia manual, sincronización entre vistas y retorno al objetivo automático sin red. Comprobación en navegador del cambio a 20× y restauración automática. Capturas y pruebas ampliadas disponibles junto al cambio.
