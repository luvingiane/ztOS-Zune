"""slipmatd availability check. The wire client is slipmat/ipc.py (async:
requests go out, answers come back as `rows`/`snapshot`/`queue` events);
client.py wraps it for the pages. Without the daemon the app shows an empty
state with a notice (no sample data)."""
import os


def slipmat_available():
    from slipmat.ipc import socket_path
    path = socket_path()
    return bool(path) and os.path.exists(path)
