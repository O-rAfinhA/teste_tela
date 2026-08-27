"""Playwright com perfil persistente: você loga uma vez, a sessão fica salva."""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path

DEFAULT_PROFILE = Path(
    os.environ.get("SUNO_DL_PROFILE", Path.home() / ".suno-dl" / "profile")
)

# Caminho de um Chrome/Chromium já instalado. Só é necessário se o navegador do
# Playwright não estiver disponível ("Executable doesn't exist at ...").
CHROMIUM_PATH = os.environ.get("SUNO_DL_CHROMIUM") or None

# Passe --channel chrome para usar o Chrome instalado na sua máquina em vez do
# Chromium que o Playwright baixa. Útil se você já tem sessões salvas nele.
LAUNCH_ARGS = [
    "--disable-blink-features=AutomationControlled",
]


@contextmanager
def browser_context(
    profile_dir: Path = DEFAULT_PROFILE,
    headless: bool = False,
    channel: str | None = None,
    downloads_dir: Path | None = None,
    executable_path: str | None = None,
):
    """Abre um contexto persistente e o fecha ao final.

    O diretório de perfil guarda os cookies do Suno, então o login sobrevive
    entre execuções — é o que permite rodar com --headless depois da primeira vez.
    """
    from playwright.sync_api import sync_playwright

    profile_dir = Path(profile_dir).expanduser()
    profile_dir.mkdir(parents=True, exist_ok=True)

    playwright = sync_playwright().start()
    try:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=headless,
            channel=channel,
            executable_path=executable_path or CHROMIUM_PATH,
            args=LAUNCH_ARGS,
            viewport={"width": 1440, "height": 900},
            accept_downloads=True,
            downloads_path=str(downloads_dir) if downloads_dir else None,
        )
        context.set_default_timeout(30_000)
        try:
            yield context
        finally:
            context.close()
    finally:
        playwright.stop()


def first_page(context):
    """O contexto persistente já nasce com uma aba; reaproveita em vez de abrir outra."""
    return context.pages[0] if context.pages else context.new_page()
