Certificado y clave **sólo para pruebas de HTTPS en localhost**. Son públicos,
autofirmados y carecen de uso fuera del servidor local temporal de los tests.
No pertenecen al almacén CA de producción ni se instalan en Windows.
Permiten probar curl_cffi/requests con verificación activa y rechazo de una CA
distinta, sin depender de Yahoo ni de descargar datos.
