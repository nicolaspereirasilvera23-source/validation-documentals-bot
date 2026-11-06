# Consulta de Carné del Deportista (SND Uruguay)

Script en Python que consulta una o varias cédulas de identidad uruguayas en
<https://aps.deporte.gub.uy/ConsultaCarneDeportista/> y devuelve, por cada carné:

| Dato | Descripción |
| --- | --- |
| Nombre y apellido | Tal como figura en el registro |
| Deporte | Disciplina del carné |
| Desde | Fecha de realización del trámite |
| Hasta | Fecha de vencimiento |
| Estado | `En fecha`, `Pronto a vencer` o `Vencido` (calculado localmente) |

No usa navegador ni Selenium: replica el `POST` del formulario oficial y parsea el HTML
de respuesta.

## Requisitos

- Python 3.9 o superior
- `requests` y `beautifulsoup4`

```bash
pip install -r requirements.txt
```

## Interfaz web (recomendada)

```bash
python servidor.py
```

Abre automáticamente <http://127.0.0.1:8000/> con un formulario para pegar una o varias
cédulas, ver el resultado en tarjetas con el estado de cada carné y descargar un CSV.

- `Ctrl+Enter` dentro del cuadro de texto consulta sin usar el mouse.
- El umbral de "pronto a vencer" se ajusta desde la misma pantalla.
- Las cédulas se mantienen solo en memoria en la página y no se guardan en `localStorage` ni en logs propios. El umbral sí se recuerda en el navegador.
- No requiere dependencias extra: usa el servidor HTTP estándar de Python.

Opciones del servidor:

| Opción | Descripción |
| --- | --- |
| `--puerto 8000` | Puerto local (default: 8000) |
| `--host 127.0.0.1` | Interfaz de escucha (usar `0.0.0.0` para acceder desde la red local) |
| `--no-abrir` | No abrir el navegador automáticamente |

## Uso por consola

```bash
# Una cédula
python carnes_deportista.py 55541330

# Varias cédulas a la vez
python carnes_deportista.py 55541330 12345678 41234567

# Se aceptan puntos y guiones: se limpian automáticamente
python carnes_deportista.py 4.123.456-7

# Desde un archivo (una o varias por línea, admite comentarios con #)
python carnes_deportista.py --archivo cedulas_ejemplo.txt

# Exportar resultados
python carnes_deportista.py --archivo cedulas_ejemplo.txt --csv carnes.csv --json carnes.json

# Sin salida por pantalla (solo archivos)
python carnes_deportista.py --archivo cedulas_ejemplo.txt --csv carnes.csv --sin-tabla

# Cambiar el criterio de "pronto a vencer" (por defecto 30 días)
python carnes_deportista.py 55541330 --dias-aviso 60

# Simular otra fecha de referencia
python carnes_deportista.py 55541330 --hoy 01/07/2026
```

Sin argumentos abre un modo interactivo:

```text
Consulta de Carné del Deportista
Ingresá cédulas (sin puntos ni guiones). Enter vacío para consultar.

Cédula 1: 55541330
Cédula 2:
```

También se puede usar por pipe:

```bash
type cedulas.txt | python carnes_deportista.py
```

### Salida de ejemplo

```text
CÉDULA    NOMBRE Y APELLIDO        DEPORTE   DESDE       HASTA       DÍAS  ESTADO
────────  ───────────────────────  ────────  ──────────  ──────────  ────  ───────
12345678  NOMBRE DE EJEMPLO         VÓLEIBOL  12/08/2024  16/07/2026  -103  Vencido

Consultado: 27/10/2026 17:01 · criterio 'pronto a vencer': ≤ 30 días
1 carné(s) · 0 en fecha · 0 pronto a vencer · 1 vencido(s) · 0 sin resultados · 0 error(es)
```

## Reglas de clasificación

Se comparan los días restantes entre la fecha `hasta` y hoy:

| Días restantes | Estado |
| --- | --- |
| `< 0` | **Vencido** |
| `0 … --dias-aviso` (30 por defecto) | **Pronto a vencer** |
| `> --dias-aviso` | **En fecha** |
| Sin fecha `hasta` | **Sin fecha** |

El estado se calcula localmente y no se copia de la etiqueta del sitio, para poder
ajustar el umbral de aviso.

## Opciones

| Opción | Descripción |
| --- | --- |
| `cedulas...` | Cédulas a consultar (posicional, admite varias) |
| `-a`, `--archivo` | Archivo de texto con cédulas |
| `--dias-aviso N` | Días para considerar "pronto a vencer" (default: 30) |
| `--hoy DD/MM/AAAA` | Fecha de referencia para el cálculo (default: hoy) |
| `--espera S` | Pausa entre consultas en segundos (default: 0.6) |
| `-t`, `--timeout` | Timeout HTTP en segundos (default: 30) |
| `--reintentos N` | Reintentos ante errores de red/HTTP (default: 3) |
| `-c`, `--csv` | Guardar CSV (UTF-8 con BOM, separador `;` por defecto) |
| `-j`, `--json` | Guardar JSON |
| `--separador` | Separador del CSV (default: `;`) |
| `--sin-tabla` | No imprimir la tabla |
| `--sin-color` | Desactivar colores ANSI |
| `-v`, `--verbose` | Mostrar progreso por consola |

## CSV / JSON

- **CSV**: `cedula;nombre;deporte;desde;hasta;dias_restantes;estado` (fechas ISO `AAAA-MM-DD`,
  UTF-8 con BOM para abrir directo en Excel).
- **JSON**: incluye `resultados`, `sin_resultados`, `errores`, la fecha de cálculo y el
  umbral usado.

## Códigos de salida

| Código | Significado |
| --- | --- |
| `0` | Consultas completadas (aunque no haya resultados) |
| `1` | Al menos una consulta falló por error de red/HTTP |
| `2` | Error de argumentos, archivo inexistente o ninguna cédula válida |

## Archivos

| Archivo | Descripción |
| --- | --- |
| `carnes_deportista.py` | Scraper y CLI |
| `servidor.py` | Servidor web local (stdlib) y endpoint `/api/consulta` |
| `static/index.html` | Interfaz |
| `static/style.css` | Estilos |
| `static/app.js` | Lógica del navegador y exportación CSV |
| `cedulas_ejemplo.txt` | Entrada de ejemplo |

## Notas

- Una persona puede tener **varios carnés** (uno por deporte); se listan todos.
- Si el sitio responde `No existen resultados coincidentes.`, la cédula se informa
  como "sin resultados" y se continúa con el resto.
- El sitio es público y no requiere autenticación. Se incluye una pausa entre consultas
  y reintentos con backoff para no sobrecargarlo.
- La interfaz web procesa hasta 100 cédulas por consulta y serializa los pedidos para
  no saturar el sitio oficial.
- Si la Secretaría Nacional del Deporte cambia el HTML, hay que ajustar
  `parsear_resultados()`; el resto del flujo no cambia.
