"""Zune Ref (dev.oneplus2.zuneref) — the MINIMAL ztOS SDK app, for perf.

Same pipeline as Zune HD (ztos.Page, entries, turnstile push/pop, the GPU
scroll path) with the smallest possible content: one page with 60 plain SDK
rows. Run both on the phone with ZUNE_PERF=1 (see ../PERF-ON-B.md):

- if this is smooth and Zune HD is not, the cost is in Zune HD's content;
- if this lags too, the cost is in the SDK/phone pipeline (kernel/driver),
  and that is what we report upstream.

perf.py here is a copy of ../perf.py (the build bundles only this folder).
"""
import ztos
import perf

app = ztos.App()
perf.install(app)


class Detail(ztos.Page):
    def __init__(self, n: int):
        super().__init__(f"item {n}")
        self.text("A pushed page: the turnstile in/out is measured too.")
        self.entry("back", "app.pop()", lambda: app.pop())


class RefHome(ztos.Page):
    def __init__(self):
        super().__init__("ref")
        self.text("Scroll me; tap a row to push a page.")
        for i in range(60):
            self.entry(f"item {i:02d}", "a plain SDK row",
                       on_tap=(lambda i=i: app.push(Detail(i))))


app.run(RefHome())
