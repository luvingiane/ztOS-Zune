"""A fake slipmatd for tests: a unix socket speaking the newline-JSON protocol
(slipmat/ipc.py + IPC.md). On connect it pushes stage/snapshot/queue from
tests/fixtures/misc.json; it answers browse/search/open with the fixtures and
records every request line to `requests_log` for assertions.
"""
import json
import os
import socket
import threading

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def load(name):
    with open(os.path.join(FIXTURES, name)) as f:
        return json.load(f)


class FakeSlipmatd:
    def __init__(self, sock_path, requests_log=None, stage="ready"):
        self.sock_path = sock_path
        self.requests = []
        self.requests_log = requests_log
        self.stage = stage
        self._stop = False
        self._thread = None

    def start(self):
        if os.path.exists(self.sock_path):
            os.unlink(self.sock_path)
        self._srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._srv.bind(self.sock_path)
        self._srv.listen(4)
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop = True
        try:
            self._srv.close()
        except OSError:
            pass

    def _serve(self):
        while not self._stop:
            try:
                conn, _ = self._srv.accept()
            except OSError:
                return
            threading.Thread(target=self._client, args=(conn,), daemon=True).start()

    def _send(self, conn, obj):
        conn.sendall((json.dumps(obj) + "\n").encode())

    def _client(self, conn):
        misc = load("misc.json")
        stage_ev = dict(misc["stage"])
        stage_ev["stage"] = self.stage
        self._send(conn, stage_ev)
        self._send(conn, misc["snapshot"])
        self._send(conn, misc["queue"])
        f = conn.makefile("rb")
        try:
            for line in f:
                if not line.strip():
                    continue
                req = json.loads(line.decode())
                self.requests.append(req)
                if self.requests_log:
                    with open(self.requests_log, "a") as out:
                        out.write(json.dumps(req) + "\n")
                tag = req.get("req")
                if tag == "browse":
                    view = req.get("view", "")
                    ev = load(f"rows-{view}.json")
                    # emulate the daemon's sort: title asc by default
                    sort = req.get("sort", "title")
                    rev = bool(req.get("reverse", False))
                    entries = ev["entries"]
                    if sort == "title":
                        key = lambda e: (e.get("title") or e.get("name") or "").lower()
                    elif sort == "artist":
                        key = lambda e: (e.get("artist") or "").lower()
                    elif sort in ("year", "added", "updated"):
                        key = lambda e: e.get("year") or e.get("date_added") or ""
                    else:
                        key = lambda e: (e.get("title") or e.get("name") or "").lower()
                    entries = sorted(entries, key=key, reverse=rev)
                    ev["entries"] = entries
                    self._send(conn, ev)
                elif tag == "search":
                    ev = dict(misc["results"])
                    ev["query"] = req.get("query", "")
                    self._send(conn, ev)
                elif tag == "open":
                    ev = dict(misc["page"])
                    ev["kind"] = req.get("kind", "")
                    ev["id"] = req.get("id", "")
                    self._send(conn, ev)
                elif tag in ("transport", "write", "play", "enqueue", "jumpTo",
                             "removeFromQueue", "clearQueue", "refresh", "signIn",
                             "signOut", "quit", "subscribe", "stage", "snapshot", "queue"):
                    pass    # fire-and-forget for these tests
        except OSError:
            pass
        finally:
            try:
                conn.close()
            except OSError:
                pass
