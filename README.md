# Consulta de Carné del Deportista (SND Uruguay)

Herramienta en Python e interfaz web para consultar cédulas uruguayas en
https://aps.deporte.gub.uy/ConsultaCarneDeportista/ y mostrar nombre, deporte,
fechas, días restantes y estado del carné. Una persona puede tener varios carnés.

## Uso sin almacenamiento

- No utiliza base de datos ni escribe resultados en archivos.
- No ofrece exportaciones CSV o JSON, tampoco desde la consola.
- La web no guarda cédulas, resultados, preferencias ni aceptación en el almacenamiento del navegador.
- Elimina las claves locales de preferencias y cédulas utilizadas por versiones anteriores.
- Los datos permanecen temporalmente en memoria para realizar la consulta y mostrarla.
- Tras una consulta correcta, vacía el campo de cédulas; los resultados se mantienen visibles hasta limpiar, salir o recargar.
- “Limpiar” borra el formulario y los resultados y cancela la espera de una respuesta pendiente en el navegador.
- Al salir se limpia la vista; al regresar mediante el historial se vuelven a exigir las condiciones.
- El servidor desactiva sus logs de acceso y envía `Cache-Control: no-store`.
- La consola muestra resultados por salida estándar; evita redirigirla a archivos si deseas mantener el uso sin almacenamiento.

Las cédulas se transmiten al servicio oficial. La infraestructura de alojamiento y
el servicio oficial pueden procesar información conforme a sus propias políticas.
Esta aplicación no puede borrar archivos exportados anteriormente ni controlar
el historial del terminal, capturas de pantalla o registros de terceros.

## Interfaz web

```bash
pip install -r requirements.txt
python servidor.py
```

Abre http://127.0.0.1:8000/. Antes de usar el sistema aparece una ventana modal:
es obligatorio marcar la casilla y pulsar “Confirmar y continuar”. Escape y los
clics fuera de la ventana no la cierran. La aceptación solo vale para esa visita.
El delegado debe contar con autorización y una finalidad legítima para consultar.

Se admiten hasta 100 cédulas por solicitud, separadas por líneas, espacios, comas
o punto y coma. Se limpian puntos y guiones y se eliminan duplicados. La validación
comprueba longitud de 6 a 8 dígitos, no el dígito de control.

Opciones del servidor: `--puerto 8080`, `--host 127.0.0.1`, `--no-abrir`.
Ctrl+Enter en el cuadro de cédulas envía la consulta.

## Consola

```bash
python carnes_deportista.py CEDULA
python carnes_deportista.py --archivo cedulas.txt
python carnes_deportista.py CEDULA --dias-aviso 60 --hoy 01/07/2026
```

Sin argumentos ofrece entrada interactiva. También acepta entrada estándar.
`--archivo` lee un archivo existente: no escribe ni modifica ese archivo.
Otras opciones: `--espera`, `--timeout`, `--reintentos`, `--sin-tabla`,
`--sin-color` y `--verbose`. El modo verbose imprime cédulas en el terminal.

## Clasificación

Se calcula localmente comparando la fecha de vencimiento con la fecha actual:

| Días restantes | Estado |
| --- | --- |
| Menos de 0 | Vencido |
| De 0 al umbral de aviso, inclusive | Pronto a vencer |
| Más que el umbral | En fecha |
| Sin vencimiento | Sin fecha |

El umbral predeterminado es de 30 días.

## Arquitectura

- `carnes_deportista.py`: consultas HTTP con requests, parseo HTML con BeautifulSoup y consola.
- `servidor.py`: servidor HTTP estándar de Python, `POST /api/consulta` y `GET /api/salud`.
- `static/`: HTML, CSS y JavaScript de la interfaz.
- `api/index.py` y `vercel.json`: adaptación para Vercel, con duración máxima configurada de 300 segundos.

No usa Selenium ni una API oficial documentada. Si cambia el HTML del sitio oficial,
puede requerir ajustes en `parsear_resultados()`. Las consultas son secuenciales,
con pausas y reintentos. El bloqueo del servidor es por proceso, no global entre
instancias de Vercel. Los lotes grandes pueden superar el tiempo de ejecución.
