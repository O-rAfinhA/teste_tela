"""Plano B do download: usar o botão de download da própria interface do Suno.

Mais lento e mais sensível a mudanças de layout que o download direto, mas
funciona mesmo se a API interna mudar de formato, porque percorre o mesmo
caminho que você percorreria no mouse.
"""

from __future__ import annotations

from pathlib import Path

from .naming import safe_filename, unique_path

# Rótulos em inglês e português — a interface muda conforme o idioma da conta.
MENU_LABELS = ["Download", "Baixar", "Descargar"]
FORMAT_LABELS = ["MP3 Audio", "MP3", "Audio", "Áudio"]


def _click_first_visible(page, labels: list[str], timeout: int = 4000) -> bool:
    """Tenta cada rótulo até um estar visível e clicável."""
    for label in labels:
        locator = page.get_by_text(label, exact=False).first
        try:
            locator.wait_for(state="visible", timeout=timeout)
            locator.click()
            return True
        except Exception:
            continue
    return False


def download_via_ui(page, track, out_dir: Path, log=print) -> Path | None:
    """Abre a página da faixa e aciona o download pela interface.

    Devolve o caminho salvo, ou None se a interface não cooperou.
    """
    out_dir = Path(out_dir).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        page.goto(f"https://suno.com/song/{track.id}", wait_until="domcontentloaded")
        page.wait_for_timeout(2500)
    except Exception as exc:
        log(f"  não abriu a página da faixa: {exc}")
        return None

    with page.expect_download(timeout=90_000) as download_info:
        if not _click_first_visible(page, MENU_LABELS):
            log("  não achei o botão de download nesta página")
            return None
        # O menu de formato só aparece em algumas versões da interface; quando
        # não aparece, o clique anterior já disparou o download.
        _click_first_visible(page, FORMAT_LABELS, timeout=2500)

    download = download_info.value
    suffix = Path(download.suggested_filename or "audio.mp3").suffix or ".mp3"
    stem = safe_filename(track.title or track.id)
    destination = unique_path(out_dir, stem, suffix)
    download.save_as(str(destination))
    return destination
