#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Interfaz web local para la consulta de Carné del Deportista.

Levanta un servidor HTTP en 127.0.0.1 que sirve la interfaz estática
(static/) y expone POST /api/consulta reutilizando el scraper de
carnes_deportista.py.

    python servidor.py
    python servidor.py --puerto 8080 --no-abrir
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import re
import sys
import threading
import time
import webbrowser
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from carnes_deportista import (
    ConsultaError,
    crear_sesion,
    consultar_cedula,
    normalizar_cedula,
)

RAIZ = Path(__file__).resolve().parent
ESTATICOS = RAIZ / "static"

MAX_CEDULAS = 100
MAX_CUERPO = 256 * 1024
TIPOS = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
}

# Serializa las consultas: evita ráfagas contra el sitio oficial.
BLOQUEO = threading.Lock()


class Manejador(BaseHTTPRequestHandler):
    server_version = "CarnesSND/1.0"

    def _ruta_solicitada(self) -> str:
        """Recupera la ruta original conservada por el rewrite de Vercel."""
        parseada = urlparse(self.path)
        original = parse_qs(parseada.query).get("__original_path", [None])[0]
        return unquote(original if original is not None else parseada.path)

    # ----------------------------- GET ---------------------------------- #
    def do_GET(self) -> None:  # noqa: N802 (API de BaseHTTPRequestHandler)
        ruta = self._ruta_solicitada()
        if ruta in ("/", "/index.html"):
            self._servir_estatico("index.html")
        elif ruta == "/api/salud":
            self._responder_json(200, {"ok": True})
        else:
            self._servir_estatico(ruta.lstrip("/"))

    # ----------------------------- POST --------------------------------- #
    def do_POST(self) -> None:  # noqa: N802
        ruta = self._ruta_solicitada()
        if ruta != "/api/consulta":
            self._responder_json(404, {"error": "Ruta no encontrada."})
            return

        try:
            largo = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            largo = 0
        if largo <= 0 or largo > MAX_CUERPO:
            self._responder_json(400, {"error": "Solicitud inválida."})
            return

        try:
            cuerpo = json.loads(self.rfile.read(largo).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._responder_json(400, {"error": "El cuerpo debe ser JSON válido."})
            return
        if not isinstance(cuerpo, dict):
            self._responder_json(400, {"error": "El cuerpo debe ser un objeto JSON."})
            return

        try:
            respuesta = procesar_consulta(
                cedulas=cuerpo.get("cedulas", ""),
                dias_aviso=cuerpo.get("dias_aviso", 30),
            )
        except ValueError as exc:
            self._responder_json(400, {"error": str(exc)})
            return
        except Exception as exc:  # noqa: BLE001 - se informa al front
            self._responder_json(500, {"error": f"Error inesperado: {exc}"})
            return

        self._responder_json(200, respuesta)

    # Vercel enruta las peticiones a la misma clase de handler.
    def do_HEAD(self) -> None:  # noqa: N802
        self.do_GET()

    # --------------------------- auxiliares ----------------------------- #
    def _servir_estatico(self, ruta_relativa: str) -> None:
        destino = (ESTATICOS / ruta_relativa).resolve()
        try:
            destino.relative_to(ESTATICOS)
        except ValueError:
            self._responder(403, b"Prohibido", "text/plain; charset=utf-8")
            return
        if not destino.is_file():
            self._responder(404, b"No encontrado", "text/plain; charset=utf-8")
            return

        tipo = TIPOS.get(destino.suffix.lower())
        if tipo is None:
            tipo = mimetypes.guess_type(destino.name)[0] or "application/octet-stream"
        self._responder(200, destino.read_bytes(), tipo)

    def _responder(
        self,
        codigo: int,
        cuerpo: bytes,
        tipo: str,
        cabeceras_extra: dict[str, str] | None = None,
    ) -> None:
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for clave, valor in (cabeceras_extra or {}).items():
            self.send_header(clave, valor)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(cuerpo)

    def _responder_json(self, codigo: int, datos: dict) -> None:
        cuerpo = json.dumps(datos, ensure_ascii=False).encode("utf-8")
        self._responder(codigo, cuerpo, "application/json; charset=utf-8")

    def log_message(self, formato: str, *args) -> None:  # noqa: A003
        sys.stderr.write(f"[web] {self.address_string()} — {formato % args}\n")


def procesar_consulta(cedulas, dias_aviso, espera: float = 0.4) -> dict:
    """Normaliza las cédulas, consulta el sitio y arma la respuesta JSON."""
    if isinstance(cedulas, (list, tuple)):
        lineas = [str(valor) for valor in cedulas]
    else:
        lineas = str(cedulas or "").splitlines()

    try:
        dias_aviso = int(dias_aviso)
    except (TypeError, ValueError):
        dias_aviso = 30
    dias_aviso = max(0, min(dias_aviso, 3650))

    validas: list[str] = []
    invalidas: list[str] = []
    for linea in lineas:
        for parte in re.split(r"[,;\s]+", linea.strip()):
            if not parte:
                continue
            cedula = normalizar_cedula(parte)
            if cedula is None:
                invalidas.append(parte)
            elif cedula not in validas:
                validas.append(cedula)

    if not validas:
        raise ValueError("Ingresá al menos una cédula válida (6 a 8 dígitos).")
    if len(validas) > MAX_CEDULAS:
        raise ValueError(f"Máximo {MAX_CEDULAS} cédulas por consulta.")

    hoy = date.today()
    resultados: list[dict] = []
    sin_resultados: list[dict] = []
    errores: list[dict] = []

    with BLOQUEO:
        sesion = crear_sesion(2)
        try:
            for indice, cedula in enumerate(validas):
                try:
                    encontrados, alertas = consultar_cedula(
                        sesion,
                        cedula,
                        timeout=30.0,
                        hoy=hoy,
                        dias_aviso=dias_aviso,
                    )
                except ConsultaError as exc:
                    errores.append({"cedula": cedula, "mensaje": str(exc)})
                else:
                    if encontrados:
                        resultados.extend(carne.a_dict() for carne in encontrados)
                    else:
                        sin_resultados.append(
                            {
                                "cedula": cedula,
                                "mensaje": alertas[0] if alertas else "Sin datos para esta cédula.",
                            }
                        )
                if espera and indice < len(validas) - 1:
                    time.sleep(espera)
        finally:
            sesion.close()

    return {
        "consultado": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "fecha_calculo": hoy.isoformat(),
        "dias_aviso": dias_aviso,
        "resultados": resultados,
        "sin_resultados": sin_resultados,
        "invalidas": invalidas,
        "errores": errores,
    }


def main(argv: list[str] | None = None) -> int:
    argumentos = parsear_argumentos(argv)
    direccion = f"http://{argumentos.host}:{argumentos.puerto}/"

    try:
        servidor = ThreadingHTTPServer((argumentos.host, argumentos.puerto), Manejador)
    except OSError as exc:
        print(f"No se pudo abrir el puerto {argumentos.puerto}: {exc}", file=sys.stderr)
        print("Probá con otro puerto, por ejemplo: python servidor.py --puerto 8080", file=sys.stderr)
        return 1

    print("=" * 58)
    print("  Consulta de Carné del Deportista — interfaz web")
    print("=" * 58)
    print(f"  Abrí: {direccion}")
    print("  Ctrl+C para detener el servidor")
    print("=" * 58)

    if not argumentos.no_abrir:
        threading.Timer(0.8, lambda: webbrowser.open(direccion)).start()

    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor detenido.")
    finally:
        servidor.server_close()
    return 0


def parsear_argumentos(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Interfaz web local para consultar carnés del deportista.")
    parser.add_argument("--host", default="127.0.0.1", help="Interfaz de escucha (default: 127.0.0.1).")
    parser.add_argument("--puerto", type=int, default=8000, help="Puerto HTTP (default: 8000).")
    parser.add_argument("--no-abrir", action="store_true", help="No abrir el navegador automáticamente.")
    return parser.parse_args(argv)


if __name__ == "__main__":
    sys.exit(main())
