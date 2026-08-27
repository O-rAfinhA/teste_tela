"""Nomes de arquivo seguros em Linux, macOS e Windows."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def safe_filename(name: str, fallback: str = "sem-titulo", max_len: int = 120) -> str:
    """Transforma um título arbitrário em um nome de arquivo utilizável."""
    name = unicodedata.normalize("NFC", name or "").strip()
    name = _ILLEGAL.sub("_", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    if name.upper() in _RESERVED:
        name = f"_{name}"
    if len(name) > max_len:
        name = name[:max_len].rstrip()
    return name or fallback


def unique_path(directory: Path, stem: str, suffix: str) -> Path:
    """Devolve um caminho que ainda não existe, acrescentando ' (2)', ' (3)'..."""
    candidate = directory / f"{stem}{suffix}"
    if not candidate.exists():
        return candidate
    for n in range(2, 1000):
        candidate = directory / f"{stem} ({n}){suffix}"
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"nomes demais colidindo com {stem!r}")
