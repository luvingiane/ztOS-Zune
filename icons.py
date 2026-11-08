"""App icons: GTK (Adwaita) symbolic SVGs, bundled in assets/icons/ and
recolored white at bundle time (see PROVENANCE.md). Buttons use them through
the SDK's own RoundButton (an "assets/icons/*.svg" glyph is rendered by the
SDK at 22x22 inside its standard 44px ring, 68x52/68x74 button — the SDK's
own sizes). This module only maps our logical names to the bundled files and
draws them where no button is wanted (the options menu rows).
"""
import ztos
from PySide6.QtCore import QByteArray, QRectF
from PySide6.QtSvg import QSvgRenderer

FILES = {
    "play": "media-playback-start-symbolic.svg",
    "pause": "media-playback-pause-symbolic.svg",
    "prev": "media-skip-backward-symbolic.svg",
    "next": "media-skip-forward-symbolic.svg",
    "shuffle": "media-playlist-shuffle-symbolic.svg",
    "repeat": "media-playlist-repeat-symbolic.svg",
    "queue": "view-list-symbolic.svg",
    "more": "view-more-horizontal-symbolic.svg",
    "search": "edit-find-symbolic.svg",
    "sort": "view-sort-ascending-symbolic.svg",
    "clear": "edit-clear-all-symbolic.svg",
    "star": "star-new-symbolic.svg",
    "album": "media-optical-cd-audio-symbolic.svg",
    "artist": "system-users-symbolic.svg",
}


def path(name: str) -> str:
    """The bundled asset path for a logical icon name (for RoundButton)."""
    return f"assets/icons/{FILES[name]}"


_renderers = {}


def _renderer(name: str) -> QSvgRenderer:
    r = _renderers.get(name)
    if r is None:
        r = QSvgRenderer(QByteArray(ztos.resource(path(name))))
        _renderers[name] = r
    return r


def draw_glyph(p, name: str, size: float, color=None):
    """Draw icon `name` centered at the painter's origin, `size` px across
    (the bundled symbolic SVGs are white already; `color` is ignored)."""
    s = size / 2.0
    _renderer(name).render(p, QRectF(-s, -s, size, size))
