#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Consulta de Carné del Deportista — Secretaría Nacional del Deporte (Uruguay).

Consulta una o varias cédulas de identidad en
https://aps.deporte.gub.uy/ConsultaCarneDeportista/ y devuelve, por cada carné:

  * Nombre y apellido
  * Deporte
  * Fecha "desde" (trámite)
  * Fecha "hasta" (vencimiento)
  * Estado calculado: "En fecha", "Pronto a vencer" o "Vencido"

Ejemplos
--------
    python carnes_deportista.py 55541330
    python carnes_deportista.py 55541330 12345678 4.123.456-7
    python carnes_deportista.py --archivo cedulas.txt --csv salida.csv
    python carnes_deportista.py --archivo cedulas.txt --json salida.json --sin-tabla

Sin argumentos abre un modo interactivo para pegar cédulas una por una.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Iterable

try:
    import requests
    from bs4 import BeautifulSoup
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
except ModuleNotFoundError as exc:  # pragma: no cover - depende del entorno
    sys.exit(
        f"Falta la dependencia '{exc.name}'.\n"
        "Instalala con:\n\n    pip install -r requirements.txt\n"
    )


URL_BASE = "https://aps.deporte.gub.uy/ConsultaCarneDeportista/"
URL_CONSULTA = URL_BASE + "Carnes/consultar"
TIPO_DOCUMENTO_CEDULA = "1"  # 1 = Cédula de identidad, 2 = Pasaporte, 3 = Otro

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

RE_FECHA = r"(\d{2}/\d{2}/\d{4})"
RE_NOMBRE = re.compile(r"^(?P<nombre>.*?)\s*\((?P<documento>\d+)\)\s*$")
RE_NO_DIGITOS = re.compile(r"[^\d]")
RE_CEDULA_VALIDA = re.compile(r"^\d{6,8}$")


class Estado(str, Enum):
    EN_FECHA = "En fecha"
    PRONTO = "Pronto a vencer"
    VENCIDO = "Vencido"
    SIN_FECHA = "Sin fecha"


@dataclass
class Carne:
    cedula: str
    nombre: str
    deporte: str
    desde: date | None
    hasta: date | None
    estado: Estado
    dias_restantes: int | None

    def a_dict(self) -> dict:
        datos = asdict(self)
        datos["desde"] = self.desde.isoformat() if self.desde else None
        datos["hasta"] = self.hasta.isoformat() if self.hasta else None
        datos["estado"] = self.estado.value
        return datos


@dataclass
class ErrorConsulta:
    cedula: str
    mensaje: str


class ConsultaError(Exception):
    """Error de red, HTTP o de formato de respuesta."""


# --------------------------------------------------------------------------- #
# Utilidades
# --------------------------------------------------------------------------- #
class Color:
    """Códigos ANSI simples; se desactivan con --sin-color o si no hay TTY."""

    habilitado = True

    RESET = "\033[0m"
    NEGRITA = "\033[1m"
    GRIS = "\033[90m"
    VERDE = "\033[92m"
    AMARILLO = "\033[93m"
    ROJO = "\033[91m"

    @classmethod
    def pintar(cls, texto: str, codigo: str) -> str:
        if not cls.habilitado:
            return texto
        return f"{codigo}{texto}{cls.RESET}"


COLOR_ESTADO = {
    Estado.EN_FECHA: Color.VERDE,
    Estado.PRONTO: Color.AMARILLO,
    Estado.VENCIDO: Color.ROJO,
    Estado.SIN_FECHA: Color.GRIS,
}


def configurar_consola() -> None:
    """Asegura UTF-8 en la consola de Windows (acentos y símbolos de la tabla)."""
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.kernel32.SetConsoleOutputCP(65001)
            ctypes.windll.kernel32.SetConsoleCP(65001)
        except Exception:  # noqa: BLE001 - consola sin soporte, seguimos igual
            pass
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except (AttributeError, ValueError, OSError):
            pass


def normalizar_cedula(valor: str) -> str | None:
    """Quita puntos, guiones y espacios. Devuelve None si no parece una cédula."""
    limpio = RE_NO_DIGITOS.sub("", (valor or "").strip())
    if not RE_CEDULA_VALIDA.match(limpio):
        return None
    return limpio


def formatear_fecha(valor: date | None) -> str:
    return valor.strftime("%d/%m/%Y") if valor else "—"


def parsear_fecha(texto: str) -> date:
    return datetime.strptime(texto, "%d/%m/%Y").date()


def clasificar(hasta: date | None, hoy: date, dias_aviso: int) -> tuple[Estado, int | None]:
    """Calcula el estado del carné según su fecha de vencimiento."""
    if hasta is None:
        return Estado.SIN_FECHA, None
    dias = (hasta - hoy).days
    if dias < 0:
        return Estado.VENCIDO, dias
    if dias <= dias_aviso:
        return Estado.PRONTO, dias
    return Estado.EN_FECHA, dias


def leer_archivo_cedulas(ruta: Path) -> list[str]:
    if not ruta.exists():
        raise FileNotFoundError(f"No se encontró el archivo: {ruta}")
    contenido = ruta.read_text(encoding="utf-8-sig")
    return [
        linea
        for linea in contenido.splitlines()
        if linea.strip() and not linea.lstrip().startswith("#")
    ]


def recolectar_cedulas(argumentos: argparse.Namespace) -> tuple[list[str], list[str]]:
    """Devuelve (cédulas válidas sin duplicados, valores inválidos)."""
    crudos: list[str] = list(argumentos.cedulas)

    if argumentos.archivo:
        crudos.extend(leer_archivo_cedulas(Path(argumentos.archivo)))

    if not crudos and not sys.stdin.isatty():  # permite: type cedulas.txt | python script.py
        crudos.extend(sys.stdin.read().splitlines())

    if not crudos:
        crudos = modo_interactivo()

    validas: list[str] = []
    invalidas: list[str] = []
    for crudo in crudos:
        # admite varias cédulas por línea separadas por coma, punto y coma o espacios
        for parte in re.split(r"[,;\s]+", crudo.strip()):
            if not parte:
                continue
            cedula = normalizar_cedula(parte)
            if cedula is None:
                invalidas.append(parte)
            elif cedula not in validas:
                validas.append(cedula)

    return validas, invalidas


def modo_interactivo() -> list[str]:
    print(
        Color.pintar("Consulta de Carné del Deportista", Color.NEGRITA)
        + "\nIngresá cédulas (sin puntos ni guiones). Enter vacío para consultar.\n"
    )
    cedulas: list[str] = []
    while True:
        try:
            linea = input(f"Cédula {len(cedulas) + 1}: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not linea:
            break
        cedulas.append(linea)
    return cedulas


# --------------------------------------------------------------------------- #
# Consulta y parseo
# --------------------------------------------------------------------------- #
def crear_sesion(reintentos: int) -> requests.Session:
    sesion = requests.Session()
    sesion.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "es-UY,es;q=0.9,en;q=0.8",
            "Referer": URL_BASE,
            "Origin": "https://aps.deporte.gub.uy",
        }
    )
    estrategia = Retry(
        total=reintentos,
        connect=reintentos,
        read=reintentos,
        backoff_factor=0.8,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"POST"}),
        raise_on_status=False,
    )
    adaptador = HTTPAdapter(max_retries=estrategia)
    sesion.mount("https://", adaptador)
    sesion.mount("http://", adaptador)
    return sesion


def consultar_cedula(
    sesion: requests.Session,
    cedula: str,
    *,
    timeout: float,
    hoy: date,
    dias_aviso: int,
) -> tuple[list[Carne], list[str]]:
    """Consulta una cédula y devuelve (carnés encontrados, mensajes del sitio)."""
    try:
        respuesta = sesion.post(
            URL_CONSULTA,
            data={"documento": cedula, "idtipodocumento": TIPO_DOCUMENTO_CEDULA},
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise ConsultaError(f"Error de conexión: {exc}") from exc

    if respuesta.status_code != 200:
        raise ConsultaError(f"El sitio respondió HTTP {respuesta.status_code}")

    respuesta.encoding = "utf-8"
    return parsear_resultados(respuesta.text, cedula, hoy=hoy, dias_aviso=dias_aviso)


def parsear_resultados(
    html: str,
    cedula: str,
    *,
    hoy: date,
    dias_aviso: int,
) -> tuple[list[Carne], list[str]]:
    soup = BeautifulSoup(html, "html.parser")
    contenedor = soup.find("div", class_="container") or soup

    alertas = [
        re.sub(r"\s+", " ", alerta.get_text(" ", strip=True)).strip()
        for alerta in contenedor.select(".alert")
    ]

    carnes: list[Carne] = []
    persona: dict[str, str] | None = None

    for nodo in contenedor.find_all(["h4", "strong"]):
        if nodo.name == "h4":
            texto = re.sub(r"\s+", " ", nodo.get_text(" ", strip=True)).strip()
            coincidencia = RE_NOMBRE.match(texto)
            if coincidencia:
                persona = {
                    "nombre": coincidencia.group("nombre").strip(),
                    "documento": coincidencia.group("documento"),
                }
            else:
                persona = {"nombre": texto, "documento": cedula}
            continue

        bloque = nodo.find_parent("div")
        if bloque is None or persona is None:
            continue

        texto_bloque = re.sub(r"\s+", " ", bloque.get_text(" ", strip=True))
        if "desde" not in texto_bloque.lower():
            continue

        deporte = re.sub(r"\s+", " ", nodo.get_text(" ", strip=True)).strip(" :")
        desde = _buscar_fecha(texto_bloque, "desde")
        hasta = _buscar_fecha(texto_bloque, "hasta")
        estado, dias = clasificar(hasta, hoy, dias_aviso)

        carnes.append(
            Carne(
                cedula=persona.get("documento") or cedula,
                nombre=persona["nombre"],
                deporte=deporte or "Sin especificar",
                desde=desde,
                hasta=hasta,
                estado=estado,
                dias_restantes=dias,
            )
        )

    return carnes, alertas


def _buscar_fecha(texto: str, etiqueta: str) -> date | None:
    coincidencia = re.search(rf"{etiqueta}\s*:?\s*{RE_FECHA}", texto, flags=re.IGNORECASE)
    if not coincidencia:
        return None
    try:
        return parsear_fecha(coincidencia.group(1))
    except ValueError:
        return None


# --------------------------------------------------------------------------- #
# Salidas
# --------------------------------------------------------------------------- #
def imprimir_tabla(
    carnes: list[Carne],
    sin_resultados: list[tuple[str, str]],
    errores: list[ErrorConsulta],
    hoy: date,
    dias_aviso: int,
) -> None:
    if carnes:
        cabecera = ["CÉDULA", "NOMBRE Y APELLIDO", "DEPORTE", "DESDE", "HASTA", "DÍAS", "ESTADO"]
        filas: list[list[str]] = []
        for carne in carnes:
            dias = "—" if carne.dias_restantes is None else str(carne.dias_restantes)
            filas.append(
                [
                    carne.cedula,
                    carne.nombre,
                    carne.deporte,
                    formatear_fecha(carne.desde),
                    formatear_fecha(carne.hasta),
                    dias,
                    carne.estado.value,
                ]
            )

        anchos = [
            max(len(cabecera[i]), *(len(fila[i]) for fila in filas))
            for i in range(len(cabecera))
        ]

        def linea(valores: Iterable[str]) -> str:
            return "  ".join(valor.ljust(anchos[i]) for i, valor in enumerate(valores))

        print()
        print(Color.pintar(linea(cabecera), Color.NEGRITA))
        print(Color.pintar("  ".join("─" * ancho for ancho in anchos), Color.GRIS))
        for fila, carne in zip(filas, carnes):
            prefijo = linea(fila[:-1]) + "  "
            print(prefijo + Color.pintar(fila[-1].ljust(anchos[-1]), COLOR_ESTADO[carne.estado]))

    for cedula, mensaje in sin_resultados:
        print(f"\n{Color.pintar('○', Color.GRIS)} {cedula}: sin resultados"
              + (f" ({mensaje})" if mensaje else ""))

    for error in errores:
        print(f"\n{Color.pintar('✖', Color.ROJO)} {error.cedula}: {error.mensaje}")

    conteo = {estado: 0 for estado in Estado}
    for carne in carnes:
        conteo[carne.estado] += 1

    print()
    print(
        Color.pintar(
            f"Consultado: {datetime.now().strftime('%d/%m/%Y %H:%M')} · "
            f"criterio 'pronto a vencer': ≤ {dias_aviso} días",
            Color.GRIS,
        )
    )
    print(
        f"{len(carnes)} carné(s) · "
        f"{Color.pintar(str(conteo[Estado.EN_FECHA]) + ' en fecha', Color.VERDE)} · "
        f"{Color.pintar(str(conteo[Estado.PRONTO]) + ' pronto a vencer', Color.AMARILLO)} · "
        f"{Color.pintar(str(conteo[Estado.VENCIDO]) + ' vencido(s)', Color.ROJO)} · "
        f"{len(sin_resultados)} sin resultados · {len(errores)} error(es)"
    )
    print()


def escribir_csv(ruta: Path, carnes: list[Carne], separador: str) -> None:
    columnas = ["cedula", "nombre", "deporte", "desde", "hasta", "dias_restantes", "estado"]
    with ruta.open("w", encoding="utf-8-sig", newline="") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=columnas, delimiter=separador)
        escritor.writeheader()
        for carne in carnes:
            fila = carne.a_dict()
            escritor.writerow({columna: fila[columna] for columna in columnas})


def escribir_json(
    ruta: Path,
    carnes: list[Carne],
    sin_resultados: list[tuple[str, str]],
    errores: list[ErrorConsulta],
    hoy: date,
    dias_aviso: int,
) -> None:
    datos = {
        "consultado": datetime.now().isoformat(timespec="seconds"),
        "fecha_calculo": hoy.isoformat(),
        "dias_aviso": dias_aviso,
        "resultados": [carne.a_dict() for carne in carnes],
        "sin_resultados": [{"cedula": cedula, "mensaje": mensaje} for cedula, mensaje in sin_resultados],
        "errores": [asdict(error) for error in errores],
    }
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def parsear_argumentos(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Consulta el Carné del Deportista (Secretaría Nacional del Deporte, Uruguay).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Ejemplos:\n"
            "  python carnes_deportista.py 55541330\n"
            "  python carnes_deportista.py 55541330 12345678\n"
            "  python carnes_deportista.py --archivo cedulas.txt --csv salida.csv\n"
        ),
    )
    parser.add_argument("cedulas", nargs="*", help="Cédulas (se aceptan puntos y guiones; se limpian).")
    parser.add_argument("-a", "--archivo", help="Archivo de texto con una o más cédulas (una por línea).")
    parser.add_argument(
        "--dias-aviso",
        type=int,
        default=30,
        metavar="N",
        help="Días para considerar un carné 'pronto a vencer' (por defecto: 30).",
    )
    parser.add_argument(
        "--hoy",
        help="Fecha de referencia DD/MM/AAAA (útil para simulaciones; por defecto: hoy).",
    )
    parser.add_argument("--espera", type=float, default=0.6, help="Segundos entre consultas (por defecto: 0.6).")
    parser.add_argument("-t", "--timeout", type=float, default=30.0, help="Timeout HTTP en segundos (por defecto: 30).")
    parser.add_argument("--reintentos", type=int, default=3, help="Reintentos ante errores de red/HTTP (por defecto: 3).")
    parser.add_argument("-c", "--csv", help="Guardar resultados en un CSV.")
    parser.add_argument("-j", "--json", help="Guardar resultados en un JSON.")
    parser.add_argument("--separador", default=";", help="Separador del CSV (por defecto: ';').")
    parser.add_argument("--sin-tabla", action="store_true", help="No mostrar la tabla por pantalla.")
    parser.add_argument("--sin-color", action="store_true", help="Desactivar colores ANSI.")
    parser.add_argument("-v", "--verbose", action="store_true", help="Mostrar progreso de cada consulta.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    configurar_consola()
    argumentos = parsear_argumentos(argv)

    if argumentos.dias_aviso < 0:
        print("Error: --dias-aviso debe ser 0 o mayor.", file=sys.stderr)
        return 2
    if argumentos.espera < 0:
        print("Error: --espera debe ser 0 o mayor.", file=sys.stderr)
        return 2

    hoy = date.today()
    if argumentos.hoy:
        try:
            hoy = parsear_fecha(argumentos.hoy)
        except ValueError:
            print("Error: --hoy debe tener el formato DD/MM/AAAA.", file=sys.stderr)
            return 2

    if argumentos.sin_color or not sys.stdout.isatty():
        Color.habilitado = False

    try:
        cedulas, invalidas = recolectar_cedulas(argumentos)
    except (FileNotFoundError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    for valor in invalidas:
        print(f"Aviso: '{valor}' no parece una cédula válida (se esperan 6 a 8 dígitos).", file=sys.stderr)
    if not cedulas:
        print("Error: no se recibió ninguna cédula válida.", file=sys.stderr)
        return 2

    sesion = crear_sesion(max(0, argumentos.reintentos))
    carnes: list[Carne] = []
    sin_resultados: list[tuple[str, str]] = []
    errores: list[ErrorConsulta] = []
    total = len(cedulas)

    try:
        for indice, cedula in enumerate(cedulas, start=1):
            if argumentos.verbose:
                print(f"[{indice}/{total}] Consultando {cedula}…", file=sys.stderr)
            try:
                encontrados, alertas = consultar_cedula(
                    sesion,
                    cedula,
                    timeout=argumentos.timeout,
                    hoy=hoy,
                    dias_aviso=argumentos.dias_aviso,
                )
                if encontrados:
                    carnes.extend(encontrados)
                    if argumentos.verbose:
                        print(f"    {len(encontrados)} carné(s) encontrado(s).", file=sys.stderr)
                else:
                    mensaje = alertas[0] if alertas else ""
                    sin_resultados.append((cedula, mensaje))
                    if argumentos.verbose:
                        print("    sin resultados.", file=sys.stderr)
            except ConsultaError as exc:
                errores.append(ErrorConsulta(cedula, str(exc)))
                print(f"Advertencia: no se pudo consultar {cedula}: {exc}", file=sys.stderr)

            if argumentos.espera and indice < total:
                time.sleep(argumentos.espera)
    except KeyboardInterrupt:
        print("\nInterrumpido por el usuario.", file=sys.stderr)
        return 130
    finally:
        sesion.close()

    if not argumentos.sin_tabla:
        imprimir_tabla(carnes, sin_resultados, errores, hoy, argumentos.dias_aviso)

    if argumentos.csv:
        escribir_csv(Path(argumentos.csv), carnes, argumentos.separador)
        print(f"CSV guardado en: {argumentos.csv}")
    if argumentos.json:
        escribir_json(Path(argumentos.json), carnes, sin_resultados, errores, hoy, argumentos.dias_aviso)
        print(f"JSON guardado en: {argumentos.json}")

    return 1 if errores else 0


if __name__ == "__main__":
    sys.exit(main())
