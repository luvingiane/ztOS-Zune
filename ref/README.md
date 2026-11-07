# ref/ — minimal SDK reference app (dev.oneplus2.zuneref)

Purpose: on the phone, run this next to Zune HD with `ZUNE_PERF=1` and compare
the per-second `zune-perf` lines (see `../PERF-ON-B.md`). It uses the same SDK
pipeline (page, entries, turnstile, GPU list scroll) with minimal content, so:

- ref smooth + Zune HD not → the cost is in Zune HD's content;
- ref lagging too → the cost is in the SDK/phone pipeline (kernel/driver).

`perf.py` is a copy of `../perf.py` (the app bundle contains only this folder);
re-copy it when `../perf.py` changes: `cp ../perf.py ref/perf.py`.

Build (from this folder, the SDK copy is gitignored in the parent):

```sh
cd ~/Github_Clones/ztos-zune-sdk/ref
python3 ../.sdk/ztos/sdk/bin/ztos-sdk build        # -> ref/dist/dev.oneplus2.zuneref
python3 ../.sdk/ztos/sdk/bin/ztos-sdk run --shot /tmp/ref.png   # try it here
```
