"""Zune HD (ztOS SDK app, dev.oneplus2.zunehd) — stage 3.

Opens directly on the music hub (ztos.Pivot: artists/albums/songs/playlists/
settings — the home hub of stage 1/2 is gone, see STATO.md). Back from the hub
closes the app. Data: slipmatd when its stage is ready (client.backend), demo
data otherwise with a visible notice. Artwork: template -> disk cache ->
async load (art.py). Perf counters: ZUNE_PERF=1 (perf.py).

No QML/Qt Quick; the SDK is used unmodified (copia in .sdk/). 360x640 points.
"""
import os
import sys
import traceback

import ztos
import perf
import hub
import screens
import player


def _excepthook(exc_type, exc, tb):
    """Every unhandled exception goes to the log WITH context (which page was
    in front) and a short notification, instead of leaving the UI stuck."""
    where = ""
    try:
        a = ztos.App.current
        p = a.page if a is not None else None
        if p is not None:
            where = f" [pagina: {type(p).__name__} {getattr(p, 'title', '')!r}]"
    except Exception:
        pass
    print(f"zunehd: unhandled {exc_type.__name__}: {exc}{where}\n"
          + "".join(traceback.format_tb(tb)), file=sys.stderr, flush=True)
    try:
        ztos.notify("errore", f"{exc_type.__name__}: {str(exc)[:110]} — vedi log")
    except Exception:
        pass


sys.excepthook = _excepthook

app = ztos.App()
perf.install(app)

# dev-only: ZUNE_NAV="songs,now" turns/pushes pages after the entrance so
# `ztos-sdk run --shot` can photograph inner screens (ZTOS_SHOT_AFTER=6000)
_nav = [s for s in os.environ.get("ZUNE_NAV", "").split(",") if s]
music = hub.MusicHub(app)
if _nav:
    from PySide6.QtCore import QTimer

    def _go():
        for step in _nav:
            if step in ("artists", "albums", "songs", "playlists"):
                music.turn({"playlists": 0, "songs": 1, "albums": 2, "artists": 3}[step])
            elif step == "settings":
                music.turn(4)
            elif step == "now":
                app.push(player.NowPlaying(app))
            elif step == "options":
                page = player.NowPlaying(app)
                app.push(page)
                QTimer.singleShot(800, page.view._open_options)
            elif step == "album":
                app.push(hub.DetailPage("album", "album-Lowlight Radio"))
            elif step == "queue":
                app.push(screens.QueuePage())
            elif step == "search":
                app.push(screens.SearchPage())

        if os.environ.get("ZUNE_SCROLL"):
            def _scroll():
                inner = music.current()
                if hasattr(inner, "_fling"):
                    inner._fling(2.5)
                    QTimer.singleShot(1500, _scroll)
            QTimer.singleShot(2500, _scroll)
    QTimer.singleShot(1500, _go)

# A/B switch for the on-device perf matrix (PERF-ON-B.md): ZUNE_PERFMODE=big|eco|normal
# asks the phone's power manager (zrnperfd, ztos.performance) how to treat this app.
_pm = os.environ.get("ZUNE_PERFMODE")
if _pm in ("big", "eco", "normal"):
    print(f"zunehd: ztos.performance({_pm!r}) -> {ztos.performance(_pm)}", flush=True)

app.run(music)
