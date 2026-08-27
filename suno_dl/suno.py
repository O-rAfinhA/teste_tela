"""Descoberta e download das faixas da sua biblioteca do Suno.

Estratégia em camadas, da mais confiável para a mais frágil:

1. Interceptação de rede — enquanto a página carrega e rola, o app faz chamadas
   JSON que trazem id, título e URL do áudio de cada faixa. Varremos qualquer
   resposta JSON em busca desses objetos, sem depender de um endpoint fixo.
2. Varredura do DOM — <audio src>, links .mp3 e o payload do Next.js.
3. Cliques na interface (--via-ui) — usa o próprio botão de download da página.

As duas primeiras camadas sobrevivem a mudanças de layout; a terceira sobrevive
a mudanças de API. Juntas cobrem a maioria das quebras.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Iterable

LIBRARY_URLS = [
    "https://suno.com/me",
    "https://suno.com/library",
]

UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I
)
AUDIO_URL_RE = re.compile(r"https?://[^\s\"']+\.(?:mp3|m4a|wav)(?:\?[^\s\"']*)?", re.I)

# Chaves onde o Suno costuma guardar a URL do áudio, em ordem de preferência.
AUDIO_KEYS = ("audio_url", "audioUrl", "stream_audio_url", "streamAudioUrl", "audio")
TITLE_KEYS = ("title", "name", "display_name")


@dataclass
class Track:
    id: str
    title: str = ""
    audio_url: str = ""
    image_url: str = ""
    created_at: str = ""
    duration: float | None = None
    tags: str = ""

    def merge(self, other: "Track") -> None:
        """Completa campos vazios com os de outra observação da mesma faixa."""
        for f in ("title", "audio_url", "image_url", "created_at", "tags"):
            if not getattr(self, f) and getattr(other, f):
                setattr(self, f, getattr(other, f))
        if self.duration is None and other.duration is not None:
            self.duration = other.duration

    def fallback_audio_url(self) -> str:
        """O CDN do Suno serve o mp3 pelo id, mesmo quando a API não mandou a URL."""
        return self.audio_url or f"https://cdn1.suno.ai/{self.id}.mp3"


class TrackSink:
    """Acumula faixas, deduplicando por id."""

    def __init__(self) -> None:
        self._tracks: dict[str, Track] = {}

    def add(self, track: Track) -> bool:
        """Devolve True se a faixa era nova."""
        if not track.id:
            return False
        existing = self._tracks.get(track.id)
        if existing is None:
            self._tracks[track.id] = track
            return True
        existing.merge(track)
        return False

    def __len__(self) -> int:
        return len(self._tracks)

    def tracks(self) -> list[Track]:
        return list(self._tracks.values())


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_str(node: dict, keys: Iterable[str]) -> str:
    for key in keys:
        value = node.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def track_from_node(node: dict) -> Track | None:
    """Interpreta um dicionário JSON como faixa, se ele se parecer com uma."""
    ident = node.get("id") or node.get("clip_id") or node.get("song_id")
    if not isinstance(ident, str) or not UUID_RE.match(ident):
        return None

    audio = _first_str(node, AUDIO_KEYS)
    title = _first_str(node, TITLE_KEYS)
    # Sem áudio e sem título é provavelmente um usuário, uma playlist ou um
    # registro qualquer que só coincide em ter um uuid — descarta.
    if not audio and not title:
        return None
    if audio and not AUDIO_URL_RE.match(audio):
        audio = ""

    metadata = node.get("metadata") if isinstance(node.get("metadata"), dict) else {}
    return Track(
        id=ident,
        title=title,
        audio_url=audio,
        image_url=_first_str(node, ("image_url", "imageUrl", "image_large_url")),
        created_at=_first_str(node, ("created_at", "createdAt")),
        duration=_as_float(node.get("duration") or metadata.get("duration")),
        tags=_first_str(node, ("tags",)) or _first_str(metadata, ("tags",)),
    )


def walk_json(data: Any, sink: TrackSink, depth: int = 0) -> None:
    """Percorre um JSON arbitrário recolhendo tudo que pareça uma faixa."""
    if depth > 12:
        return
    if isinstance(data, dict):
        track = track_from_node(data)
        if track is not None:
            sink.add(track)
        for value in data.values():
            walk_json(value, sink, depth + 1)
    elif isinstance(data, list):
        for item in data:
            walk_json(item, sink, depth + 1)


# --------------------------------------------------------------------------
# Camada 1: interceptação de rede
# --------------------------------------------------------------------------


def attach_network_listener(page, sink: TrackSink) -> None:
    def on_response(response):
        content_type = (response.headers or {}).get("content-type", "")
        if "json" not in content_type.lower():
            return
        try:
            payload = response.json()
        except Exception:
            return  # resposta já descartada, corpo binário, JSON inválido
        walk_json(payload, sink)

    page.on("response", on_response)


# --------------------------------------------------------------------------
# Camada 2: varredura do DOM
# --------------------------------------------------------------------------

_DOM_SCRIPT = """
() => {
  const urls = new Set();
  document.querySelectorAll('audio[src], source[src], a[href]').forEach(el => {
    const u = el.src || el.href || '';
    if (/\\.(mp3|m4a|wav)(\\?|$)/i.test(u)) urls.add(u);
  });
  let nextData = null;
  try {
    const el = document.getElementById('__NEXT_DATA__');
    if (el) nextData = JSON.parse(el.textContent);
  } catch (e) { /* payload ausente ou malformado */ }
  return { urls: [...urls], nextData };
}
"""


def harvest_dom(page, sink: TrackSink) -> None:
    try:
        result = page.evaluate(_DOM_SCRIPT)
    except Exception:
        return
    for url in result.get("urls") or []:
        match = re.search(r"([0-9a-f-]{36})\.(?:mp3|m4a|wav)", url, re.I)
        if match:
            sink.add(Track(id=match.group(1).lower(), audio_url=url))
    if result.get("nextData"):
        walk_json(result["nextData"], sink)


# --------------------------------------------------------------------------
# Rolagem: a biblioteca carrega sob demanda
# --------------------------------------------------------------------------


def scroll_until_settled(
    page,
    sink: TrackSink,
    max_rounds: int = 400,
    patience: int = 6,
    pause: float = 1.2,
    log=print,
) -> None:
    """Rola até parar de aparecer faixa nova por `patience` rodadas seguidas."""
    stale = 0
    last_count = len(sink)
    for round_no in range(max_rounds):
        page.mouse.wheel(0, 2200)
        page.wait_for_timeout(int(pause * 1000))
        harvest_dom(page, sink)

        if len(sink) > last_count:
            log(f"  ... {len(sink)} faixas encontradas")
            last_count = len(sink)
            stale = 0
        else:
            stale += 1
            if stale >= patience:
                log(f"  fim da lista (rodada {round_no + 1})")
                return
    log("  limite de rolagem atingido — aumente --max-scroll se faltou música")


def collect_tracks(page, log=print) -> list[Track]:
    """Abre a biblioteca, rola até o fim e devolve as faixas encontradas."""
    sink = TrackSink()
    attach_network_listener(page, sink)

    for url in LIBRARY_URLS:
        log(f"Abrindo {url}")
        try:
            page.goto(url, wait_until="domcontentloaded")
        except Exception as exc:
            log(f"  não consegui abrir: {exc}")
            continue
        page.wait_for_timeout(4000)
        harvest_dom(page, sink)
        if len(sink):
            break

    if not len(sink):
        log(
            "Nenhuma faixa apareceu. Você está logado? Rode `python -m suno_dl login` "
            "e faça o login na janela que abrir."
        )
        return []

    log(f"{len(sink)} faixas na primeira tela; rolando para carregar o resto...")
    scroll_until_settled(page, sink, log=log)
    return sink.tracks()


# --------------------------------------------------------------------------
# Download
# --------------------------------------------------------------------------


def download_tracks(
    context,
    tracks: list[Track],
    out_dir: Path,
    skip_existing: bool = True,
    log=print,
) -> dict:
    """Baixa cada faixa usando a sessão do navegador (cookies incluídos)."""
    from .naming import safe_filename, unique_path

    out_dir = Path(out_dir).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = out_dir / "manifest.json"
    already: dict[str, str] = {}
    if skip_existing and manifest_path.exists():
        try:
            for entry in json.loads(manifest_path.read_text("utf-8")):
                # Entradas que falharam antes têm file=None: ignora e tenta de novo.
                name, ident = entry.get("file"), entry.get("id")
                if name and ident and (out_dir / name).exists():
                    already[ident] = name
        except Exception as exc:
            log(f"manifest.json ilegível ({exc}) — vou rebaixar tudo")

    entries: list[dict] = []
    ok = failed = skipped = 0

    for index, track in enumerate(sorted(tracks, key=lambda t: t.created_at), start=1):
        label = track.title or track.id
        if track.id in already:
            skipped += 1
            entries.append({**asdict(track), "file": already[track.id]})
            continue

        url = track.fallback_audio_url()
        stem = safe_filename(f"{index:03d} - {track.title or track.id}")
        destination = unique_path(out_dir, stem, ".mp3")

        try:
            response = context.request.get(url, timeout=120_000)
            if not response.ok:
                raise RuntimeError(f"HTTP {response.status}")
            body = response.body()
            if len(body) < 1024:
                raise RuntimeError(f"resposta pequena demais ({len(body)} bytes)")
            destination.write_bytes(body)
        except Exception as exc:
            failed += 1
            log(f"[{index}/{len(tracks)}] FALHOU  {label}: {exc}")
            entries.append({**asdict(track), "file": None, "error": str(exc)})
            continue

        ok += 1
        size_mb = destination.stat().st_size / 1_048_576
        log(f"[{index}/{len(tracks)}] ok  {destination.name}  ({size_mb:.1f} MB)")
        entries.append({**asdict(track), "file": destination.name})

    manifest_path.write_text(
        json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log(f"\nBaixadas {ok} | puladas {skipped} | falharam {failed}")
    log(f"Pasta: {out_dir}")
    log(f"Manifesto: {manifest_path}")
    return {"ok": ok, "skipped": skipped, "failed": failed, "dir": str(out_dir)}
