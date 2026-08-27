"""Leitura de tela: captura, OCR e clique por texto.

Serve para duas coisas: inspecionar o que está na tela (`screen read`) e como
plano C quando a automação do navegador não achar o botão — você localiza o
texto e clica nele pelas coordenadas reais da tela.

As dependências (mss, pytesseract, pyautogui) são importadas sob demanda, para
que o download do Suno continue funcionando em máquinas sem tesseract instalado.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path


class ScreenDependencyError(RuntimeError):
    """Falta uma dependência de leitura de tela; a mensagem diz como instalar."""


@dataclass
class Word:
    text: str
    left: int
    top: int
    width: int
    height: int
    confidence: float

    @property
    def center(self) -> tuple[int, int]:
        return self.left + self.width // 2, self.top + self.height // 2


def _require(module: str, hint: str):
    try:
        return __import__(module)
    except ImportError as exc:
        raise ScreenDependencyError(f"falta o módulo {module!r}: {hint}") from exc


def grab(monitor: int = 0, save_to: Path | None = None):
    """Captura a tela e devolve uma imagem PIL.

    monitor=0 é a área total (todos os monitores); 1 é o primeiro monitor.
    """
    _require("mss", "pip install mss")
    _require("PIL", "pip install Pillow")
    import mss
    from PIL import Image

    with mss.mss() as sct:
        if monitor >= len(sct.monitors):
            raise ValueError(
                f"monitor {monitor} não existe (há {len(sct.monitors) - 1} telas)"
            )
        shot = sct.grab(sct.monitors[monitor])
        image = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")

    if save_to:
        save_to = Path(save_to).expanduser()
        save_to.parent.mkdir(parents=True, exist_ok=True)
        image.save(save_to)
    return image


def _check_tesseract() -> None:
    if shutil.which("tesseract") is None:
        raise ScreenDependencyError(
            "o binário do tesseract não está no PATH. "
            "Ubuntu/Debian: sudo apt install tesseract-ocr tesseract-ocr-por | "
            "macOS: brew install tesseract tesseract-lang | "
            "Windows: https://github.com/UB-Mannheim/tesseract/wiki"
        )


def read_words(image=None, lang: str = "por+eng", min_confidence: float = 40) -> list[Word]:
    """Roda OCR e devolve as palavras com posição na tela."""
    _require("pytesseract", "pip install pytesseract")
    _check_tesseract()
    import pytesseract

    if image is None:
        image = grab()

    data = pytesseract.image_to_data(
        image, lang=lang, output_type=pytesseract.Output.DICT
    )
    words: list[Word] = []
    for i, text in enumerate(data["text"]):
        text = (text or "").strip()
        if not text:
            continue
        try:
            confidence = float(data["conf"][i])
        except (TypeError, ValueError):
            confidence = -1.0
        if confidence < min_confidence:
            continue
        words.append(
            Word(
                text=text,
                left=int(data["left"][i]),
                top=int(data["top"][i]),
                width=int(data["width"][i]),
                height=int(data["height"][i]),
                confidence=confidence,
            )
        )
    return words


def read_text(image=None, lang: str = "por+eng") -> str:
    """Todo o texto visível na tela, em uma string."""
    _require("pytesseract", "pip install pytesseract")
    _check_tesseract()
    import pytesseract

    return pytesseract.image_to_string(image if image is not None else grab(), lang=lang)


def find(pattern: str, words: list[Word] | None = None, regex: bool = False) -> list[Word]:
    """Palavras cujo texto casa com o padrão (por padrão, substring sem acento-sensível)."""
    words = read_words() if words is None else words
    if regex:
        matcher = re.compile(pattern, re.I)
        return [w for w in words if matcher.search(w.text)]
    needle = pattern.casefold()
    return [w for w in words if needle in w.text.casefold()]


def click(word: Word, dry_run: bool = False) -> tuple[int, int]:
    """Move o mouse até o centro da palavra e clica."""
    x, y = word.center
    if dry_run:
        return x, y
    _require("pyautogui", "pip install pyautogui")
    import pyautogui

    pyautogui.moveTo(x, y, duration=0.25)
    pyautogui.click()
    return x, y
