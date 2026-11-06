"""Adaptador HTTP para ejecutar el handler existente como Vercel Function."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from servidor import Manejador as Handler  # noqa: E402
