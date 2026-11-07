"""The music library shown by the app: slipmatd when it answers, demo data
otherwise. The demo data is this project's own (carried over from the phase-2
backend, non-visual part); the slipmatd wire client is slipmat/ipc.py.
"""
import os

# ---- demo data (our own, from the phase-2 demo backend) -----------------------


DEMO_ARTISTS = [
    ("Afterglow", "Dream pop, Shoegaze"),
    ("Cobalt Youth", "Indie rock"),
    ("Marisol Vega", "Latin pop"),
    ("Kilowatt Kids", "Electro"),
]

DEMO_ALBUMS = {
    "Afterglow": [("Lowlight Radio", "2019", [
        ("Neon Harbor", 174000), ("Afterglow", 185000), ("Slow Static", 201000),
        ("Midnight Parade", 167000), ("Velvet Antenna", 193000), ("Ghost Frequency", 178000)])],
    "Cobalt Youth": [("Arcade Youth", "2021", [
        ("Arcade Kids", 224000), ("Brighter Than Blue", 253000), ("Pixel Heart", 198000),
        ("Cassette Sunrise", 211000), ("Chrome Dreams", 236000)])],
    "Marisol Vega": [("Blueprint", "2018", [
        ("Blueprint", 261000), ("Ritmo Lento", 244000), ("Sangre Azul", 229000),
        ("La Última Ola", 272000)])],
    "Kilowatt Kids": [("Brownout", "2022", [
        ("Brownout", 187000), ("Overdrive", 176000), ("Supernova Baby", 205000),
        ("Circuit Breaker", 192000), ("Watt Machine", 183000), ("After Party", 215000)])],
}

DEMO_PLAYLISTS = [
    ("Late Night Drive", "Demo curator", [
        ("Afterglow", "Lowlight Radio", "Neon Harbor"),
        ("Cobalt Youth", "Arcade Youth", "Arcade Kids"),
        ("Kilowatt Kids", "Brownout", "Overdrive")]),
    ("Focus", "Demo curator", [
        ("Marisol Vega", "Blueprint", "Ritmo Lento"),
        ("Afterglow", "Lowlight Radio", "Slow Static")]),
]

# what the demo plays right now (drives the home strip and Now Playing)
NOW_PLAYING = {"title": "Neon Harbor", "artist": "Afterglow",
               "album": "Lowlight Radio", "duration_ms": 174000, "position_ms": 41000}


def demo_library():
    """The demo library as flat lists of dicts (slipmat-entry-like)."""
    songs, albums, artists, playlists = [], [], [], []
    for artist, genres in DEMO_ARTISTS:
        artists.append({"kind": "artist", "id": f"artist-{artist}", "name": artist,
                        "subtitle": genres})
        for album, year, tracks in DEMO_ALBUMS[artist]:
            albums.append({"kind": "album", "id": f"album-{album}", "name": album,
                           "subtitle": f"{artist} — {year}", "artist": artist})
            for i, (title, dur) in enumerate(tracks, 1):
                songs.append({"kind": "song", "id": f"lib-{album}-{i}", "title": title,
                              "subtitle": f"{artist} — {album}", "artist": artist,
                              "album": album, "duration_ms": dur, "track_number": i})
    for name, curator, tracks in DEMO_PLAYLISTS:
        playlists.append({"kind": "playlist", "id": f"playlist-{name}", "name": name,
                          "subtitle": f"{curator} — {len(tracks)} tracks",
                          "tracks": [{"title": t, "artist": a, "album": al}
                                     for a, al, t in tracks]})
    return {"artists": artists, "albums": albums, "songs": songs, "playlists": playlists}


# ---- slipmatd ----------------------------------------------------------------
# The wire client is slipmat/ipc.py (async: requests go out, answers come back
# as `rows`/`snapshot`/`queue` events). client.py wraps it for the pages; when
# slipmatd is not running the app shows the demo data above.

def slipmat_available():
    from slipmat.ipc import socket_path
    path = socket_path()
    return bool(path) and os.path.exists(path)
