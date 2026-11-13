# V7 en Windows 11, sin Git

1. Instala **Python 3.12 de 64 bits** desde [python.org](https://www.python.org/downloads/windows/), incluyendo el lanzador `py`.
2. [Descarga el ZIP de `main`](https://github.com/AlvaroAlonsoLarre/valoracion-bursatil/archive/refs/heads/main.zip). Extrae **todo** el contenido en una carpeta corta, por ejemplo `C:\Bolsa`. También se admiten espacios, acentos y nombres Unicode; la ruta corta evita los límites de longitud de Windows.
3. Cierra el servidor anterior con `cerrar_dashboard.bat` antes de sustituir una copia. Conserva tus capturas `*_inputs.json` fuera de la carpeta que vayas a reemplazar.
4. Haz doble clic en **`iniciar_dashboard.bat`**. No hacen falta Git, Anaconda, privilegios de administrador ni configurar PowerShell.
5. La primera ejecución crea `.venv`, instala las versiones de `requirements.lock`, comprueba dependencias y certificados y abre el navegador. Las siguientes reutilizan el entorno. La instalación inicial y **Consultar fuentes** necesitan Internet; recalcular una captura no descarga datos.

El lanzador no descarga versiones del proyecto ni aplica parches. Ejecuta el único `dashboard_app.py` de esta carpeta. No sobrescribe un `.venv` incompleto o de otra versión: informa de que debes renombrarlo para conservarlo y crear uno correcto. El `.ps1` antiguo sólo delega en el mismo BAT.

## UTF-8 y HTTPS

Los procesos configuran UTF-8 automáticamente, incluidas entradas/salidas, subprocesos, JSON y logs. No tienes que establecer `PYTHONUTF8` o `PYTHONIOENCODING` manualmente.

Se valida el almacén CA de `certifi` o el almacén explícito heredado del entorno. Cuando la ruta contiene Unicode, Windows utiliza un alias ASCII si existe; de lo contrario se copia el mismo PEM a una carpeta ASCII nueva creada atómicamente con permisos exclusivos del usuario y SYSTEM. Se comprueba el hash de la copia y el contenido CA; la carpeta se elimina al terminar normalmente. No se reutilizan archivos de otros usuarios, no se instala una CA en el sistema y no se desactiva la verificación HTTPS. Linux y Streamlit Cloud conservan sus certificados y proxy heredados.

Si cierras el servidor a la fuerza, puede quedar una carpeta privada `vb-ca-*` residual en ProgramData/Windows Temp. Contiene únicamente el PEM público; no se reutiliza en el siguiente arranque. No es necesario borrarla para ejecutar la aplicación.

Los diagnósticos distinguen `CA_LOCAL`, `SSL`, `RED_CONEXION`, `RED_TIMEOUT`, `LIMITE_YAHOO`, `SEC_HTTP_403` y `DATOS_INCOMPLETOS`. Una denegación SEC 403 no se corrige desactivando SSL. Si una red corporativa requiere una CA específica, utiliza el almacén aprobado por su administrador; la aplicación no sustituye un almacén explícito inválido por otro ni evita sus controles.

## Uso y soporte

La aplicación abre una captura MSFT archivada y fechada con seis escenarios. Para datos recientes pulsa **Consultar fuentes**. Para recuperar ajustes importa la **captura reproducible `*_inputs.json`**, no el JSON de resultados. En Resumen están PER automático/manual y bandas; las exportaciones Excel/JSON conservan los supuestos activos. En **Datos y auditoría** puedes consultar firma del motor y commit; desde un ZIP sin `.git`, el commit se muestra como `N/D`, sin impedir los cálculos.

Los errores de arranque indican el paso fallido. El servidor escribe `logs/servidor_salida.log` y `logs/servidor_errores.log` en UTF-8. Se abre un servidor nuevo de esta copia para evitar reutilizar una aplicación antigua; ciérralo con `cerrar_dashboard.bat` antes de volver a arrancar.

Alternativa desde PowerShell, una vez preparado el entorno:

```powershell
.\.venv\Scripts\python.exe -m streamlit run dashboard_app.py
```

Esta ejecución directa también configura UTF-8/certificados. No uses los instaladores antiguos que crean `PROYECTO_V7` y parchean descargas.

La validación diferencia las pruebas automatizadas de Linux/Windows en GitHub Actions de una sesión interactiva en un ordenador Windows. El informe indica exactamente qué se ha ejecutado; no se atribuyen pruebas de escritorio que no se hayan realizado.
