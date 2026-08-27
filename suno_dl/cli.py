"""Interface de linha de comando.

    python -m suno_dl login             # abre o navegador para você logar (1x)
    python -m suno_dl list              # mostra o que achou na sua biblioteca
    python -m suno_dl download          # baixa tudo
    python -m suno_dl screen read       # lê o texto da sua tela agora
    python -m suno_dl screen find "Download"
    python -m suno_dl screen click "Download"
"""

from __future__ import annotations

import argparse
import json
import sys
from contextlib import contextmanager
from pathlib import Path

from .browser import DEFAULT_PROFILE, browser_context, first_page

DEFAULT_OUT = Path.home() / "Music" / "Suno"


def _browser_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--profile", type=Path, default=DEFAULT_PROFILE,
        help=f"pasta do perfil do navegador (padrão: {DEFAULT_PROFILE})",
    )
    parser.add_argument(
        "--channel", default=None,
        help="use 'chrome' para rodar no Chrome instalado em vez do Chromium do Playwright",
    )
    parser.add_argument(
        "--headless", action="store_true",
        help="sem janela (só funciona depois que o login já está salvo no perfil)",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="suno_dl",
        description="Baixa as músicas da SUA biblioteca do Suno, com leitura de tela de apoio.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_login = sub.add_parser("login", help="abre o Suno para você fazer login uma vez")
    _browser_flags(p_login)

    p_list = sub.add_parser("list", help="lista as faixas encontradas, sem baixar")
    _browser_flags(p_list)
    p_list.add_argument("--json", action="store_true", help="saída em JSON")

    p_dl = sub.add_parser("download", help="baixa as faixas da sua biblioteca")
    _browser_flags(p_dl)
    p_dl.add_argument("-o", "--out", type=Path, default=DEFAULT_OUT,
                      help=f"pasta de destino (padrão: {DEFAULT_OUT})")
    p_dl.add_argument("--limit", type=int, default=0, help="baixa apenas as N primeiras")
    p_dl.add_argument("--redownload", action="store_true",
                      help="rebaixa mesmo o que já está na pasta")
    p_dl.add_argument("--via-ui", action="store_true",
                      help="baixa clicando no botão da página (mais lento, plano B)")

    p_screen = sub.add_parser("screen", help="leitura da tela (OCR)")
    screen_sub = p_screen.add_subparsers(dest="screen_command", required=True)

    p_read = screen_sub.add_parser("read", help="imprime o texto visível na tela")
    p_read.add_argument("--save", type=Path, help="salva a captura em um arquivo")
    p_read.add_argument("--lang", default="por+eng", help="idiomas do OCR")
    p_read.add_argument("--monitor", type=int, default=0)

    p_find = screen_sub.add_parser("find", help="localiza um texto na tela")
    p_find.add_argument("text")
    p_find.add_argument("--regex", action="store_true")
    p_find.add_argument("--lang", default="por+eng")
    p_find.add_argument("--monitor", type=int, default=0)

    p_click = screen_sub.add_parser("click", help="clica no texto encontrado na tela")
    p_click.add_argument("text")
    p_click.add_argument("--regex", action="store_true")
    p_click.add_argument("--lang", default="por+eng")
    p_click.add_argument("--monitor", type=int, default=0)
    p_click.add_argument("--dry-run", action="store_true",
                         help="mostra onde clicaria, sem clicar")

    return parser


# ---------------------------------------------------------------- comandos


def cmd_login(args) -> int:
    with browser_context(args.profile, headless=False, channel=args.channel) as ctx:
        page = first_page(ctx)
        page.goto("https://suno.com/me", wait_until="domcontentloaded")
        print("Faça login na janela que abriu.")
        print("Quando sua biblioteca estiver visível, volte aqui e aperte Enter.")
        try:
            input()
        except (EOFError, KeyboardInterrupt):
            pass
        print(f"Sessão salva em {args.profile}")
    return 0


@contextmanager
def _collect(args):
    """Abre o navegador, coleta a biblioteca e mantém o contexto vivo no bloco."""
    from .suno import collect_tracks

    with browser_context(args.profile, headless=args.headless, channel=args.channel) as ctx:
        page = first_page(ctx)
        yield ctx, page, collect_tracks(page)


def cmd_list(args) -> int:
    with _collect(args) as (_ctx, _page, tracks):
        if args.json:
            from dataclasses import asdict
            print(json.dumps([asdict(t) for t in tracks], ensure_ascii=False, indent=2))
        else:
            for i, t in enumerate(sorted(tracks, key=lambda t: t.created_at), 1):
                dur = f"{t.duration:.0f}s" if t.duration else "  ?  "
                print(f"{i:3d}. {t.title or '(sem título)':45.45} {dur:>6}  {t.created_at[:10]}")
            print(f"\n{len(tracks)} faixas.")
    return 0


def cmd_download(args) -> int:
    from .suno import download_tracks

    with _collect(args) as (ctx, page, tracks):
        if not tracks:
            return 1
        tracks = sorted(tracks, key=lambda t: t.created_at)
        if args.limit:
            tracks = tracks[: args.limit]
            print(f"Limitando às {len(tracks)} primeiras.")

        if args.via_ui:
            from .ui_download import download_via_ui

            ok = 0
            for i, track in enumerate(tracks, 1):
                print(f"[{i}/{len(tracks)}] {track.title or track.id}")
                saved = download_via_ui(page, track, args.out)
                if saved:
                    ok += 1
                    print(f"  salvo: {saved.name}")
            print(f"\nBaixadas {ok} de {len(tracks)}.")
            return 0 if ok else 1

        result = download_tracks(
            ctx, tracks, args.out, skip_existing=not args.redownload
        )
        if result["failed"] and not result["ok"]:
            print("\nTudo falhou. Tente `--via-ui`, que usa o botão da própria página.")
            return 1
    return 0


def cmd_screen(args) -> int:
    from . import screen

    try:
        image = screen.grab(monitor=args.monitor, save_to=getattr(args, "save", None))

        if args.screen_command == "read":
            if getattr(args, "save", None):
                print(f"Captura salva em {args.save}")
            print(screen.read_text(image, lang=args.lang))
            return 0

        words = screen.read_words(image, lang=args.lang)
        hits = screen.find(args.text, words, regex=args.regex)
        if not hits:
            print(f"Não achei {args.text!r} na tela.")
            return 1

        if args.screen_command == "find":
            for w in hits:
                x, y = w.center
                print(f"{w.text!r} em ({x}, {y})  confiança {w.confidence:.0f}%")
            return 0

        x, y = screen.click(hits[0], dry_run=args.dry_run)
        verb = "Clicaria" if args.dry_run else "Cliquei"
        print(f"{verb} em {hits[0].text!r} ({x}, {y})")
        return 0

    except screen.ScreenDependencyError as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 2


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    handlers = {
        "login": cmd_login,
        "list": cmd_list,
        "download": cmd_download,
        "screen": cmd_screen,
    }
    try:
        return handlers[args.command](args)
    except KeyboardInterrupt:
        print("\nInterrompido.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
