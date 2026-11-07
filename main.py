"""Zune HD (ztOS SDK app, dev.oneplus2.zunehd) — stage 3.

Opens directly on the music hub (ztos.Pivot: artists/albums/songs/playlists/
settings — the home hub of stage 1/2 is gone, see STATO.md). Back from the hub
closes the app. Data: slipmatd when its stage is ready (client.backend), demo
data otherwise with a visible notice. Artwork: template -> disk cache ->
async load (art.py). Perf counters: ZUNE_PERF=1 (perf.py).

No QML/Qt Quick; the SDK is used unmodified (copia in .sdk/). 360x640 points.
"""
import os

import ztos
import perf
import hub
import screens
import player

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
                music.turn(["artists", "albums", "songs", "playlists"].index(step))
            elif step == "settings":
                music.turn(4)
            elif step == "now":
                app.push(player.NowPlaying(app))
            elif step == "options":
                page = player.NowPlaying(app)
                app.push(page)
                QTimer.singleShot(800, page.view._open_options)
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

app.run(music)
