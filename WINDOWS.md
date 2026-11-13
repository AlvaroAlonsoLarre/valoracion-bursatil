# Ejecutar V7 integrada en Windows

Hay una sola aplicación (`dashboard_app.py`) y el motor financiero original del repositorio. No utilices los instaladores que crean `PROYECTO_V7` y aplican parches a otra descarga.

1. Instala Python **3.12 de 64 bits** y Git, o descarga el ZIP de la rama `feat/v7-integrada` desde GitHub y extráelo completo.
2. Abre PowerShell en la carpeta del repositorio. Si usas Git:

```powershell
git clone --branch feat/v7-integrada https://github.com/AlvaroAlonsoLarre/valoracion-bursatil.git
cd valoracion-bursatil
```

3. Crea el entorno de esta copia e instala las dependencias fijadas:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe -c "import streamlit; from streamlit.proto import RootContainer_pb2"
.\.venv\Scripts\python.exe -m streamlit run dashboard_app.py
```

No es necesario activar PowerShell ni modificar su política de ejecución. También puedes abrir `iniciar_dashboard.bat`: utiliza esta misma aplicación, prefiere `.venv` y verifica Streamlit/proto. Sólo instala bibliotecas si faltan; no descarga ni parchea el proyecto.

Cierra servidores de la instalación anterior con Ctrl+C antes de abrir la nueva copia. Usa la URL que indique la consola; un marcador del navegador puede seguir apuntando al servidor antiguo. En **Datos y auditoría** aparecen el commit y la firma de los módulos financieros; funcionan también como identificación si descargaste un ZIP sin `.git`.

La aplicación abre una captura MSFT archivada y fechada, con seis escenarios. Para obtener datos actuales pulsa **Consultar fuentes**. Para trabajar sin red importa la **captura reproducible `*_inputs.json`**, no el JSON de resultados. Cambiar periodos o supuestos no descarga datos.

En Resumen elige PER automático, exploratorio con dos referencias o manual justificado. Aplicar un PER conserva crecimiento, márgenes, fiscalidad, ADR, política y ajustes opcionales. Las exportaciones Excel/JSON corresponden al análisis visible; las interpolaciones del gráfico se identifican por separado.

La validación automática se ejecuta con Python 3.12. Los lanzadores Windows se revisan, pero las pruebas del repositorio y del navegador se ejecutan en Linux; no se afirma una prueba en un escritorio Windows real.
