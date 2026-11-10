# PERF-ON-B.md — measuring performance on the phone

Purpose: with `ZUNE_PERF=1` the app writes, once per second, a `zune-perf`
line to its log (`~/.local/state/ztos/<id>.log`) with: frames/s (paintGL),
swaps/s (frameSwapped = frames presented), frame-to-frame interval avg/min/max
(`d_paint` and `d_swap`), CPU ms inside `zsdk_draw` and the number of quads,
frames whose quads are identical to the previous one (`identical` = updates
without a content change), textures uploaded (count/bytes/size), **textures
alive on the GPU (`tex_live`, `tex_live_bytes` — the GPU budget: there must be
no `MESA: error` in the log)**, ms of Qt raster passes, layer refreshes, widget
paints and content changes (`changes`). See `perf.py` for the exact format.

Goal: ≥ 30 real fps (`d_swap` avg ≤ 33 ms), 60 if possible (≤ 16.7 ms).

## 1) Install and start with the counters on

Install normally ([INSTALL.md](INSTALL.md)). From a shell **inside the ztOS
session** (the same environment as the menu: `FD_MESA_DEBUG=sysmem`,
`QT_QPA_PLATFORM=wayland`, `ZTMETRO_SCALE=3`):

```sh
ZUNE_PERF=1 ~/.local/share/ztos/apps/dev.oneplus2.zunehd
```

If your ssh is **not** in the graphical session, copy the shell's environment
first (read-only) and then launch:

```sh
eval "$(tr '\0' '\n' < /proc/$(pgrep -f 'ztmetro' | head -1)/environ \
  | grep -E '^(XDG_RUNTIME_DIR|WAYLAND_DISPLAY|DISPLAY|QT_QPA_PLATFORM|FD_MESA_DEBUG|ZTMETRO_SCALE|XDG_SESSION_TYPE)=' \
  | sed 's/$/;/')"
ZUNE_PERF=1 ~/.local/share/ztos/apps/dev.oneplus2.zunehd
```

To measure from the app menu, add a second `.desktop` entry whose `Exec=` is
`env ZUNE_PERF=1 …/dev.oneplus2.zunehd` (and remove it when you are done, so
the menu keeps a single entry).

## 2) What to do while it runs, then collect the log

(a) leave the first screen still for 5 s; (b) scroll a list up and down for
10 s; (c) enter a page and go back 3 times; (d) open "now playing" from the app
bar and go back. Then:

```sh
cat ~/.local/state/ztos/dev.oneplus2.zunehd.log
# from the computer: scp <user>@<phone-ip>:'~/.local/state/ztos/dev.oneplus2.zune*.log' /tmp/
```

While scrolling also note the free CPU (`top -bn1 | head`), the GPU clock, and
how smooth it looks (1 = jerky, 5 = smooth).

## 3) Results sheet

| scenario | fps (swaps/s) | d_swap avg/max ms | draw ms max | quad max | identical/s | upload bytes/s | raster ms/s | paints/s | changes/s | smooth (1-5) | free CPU | GPU clock |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| music pivot, still | | | | | | | | | | | | |
| list scroll (songs) | | | | | | | | | | | | |
| page enter/exit | | | | | | | | | | | | |
| now playing (while playing) | | | | | | | | | | | | |
| progress bar every 500 ms (snapshot) | | | | | | | | | | | | |

Reading: low `d_swap` with low `draw ms` means the app is fine; high `d_swap`
with low `draw ms` means waiting on frame pacing (Wayland frame callbacks);
high upload ms means memcpy cost in `sysmem`; high `identical` means redraws
without a change.

## 4) The "progress bar advances in jumps" scenario

Open the app with `ZUNE_PERF=1`, play a track and stay on the player for 15 s
without touching anything. During playback the log should show `paints` ~2/s
(only the seek bar), `raster` ~0 ms and no jump in `changes`. Before the fix
every snapshot (every 500 ms) invalidated the whole page, causing a full-page
repaint at DPR 3 and a bar visible only every ~2 s. Report `paints/s`,
`raster ms/s` and `top -b -H -d 2 -n 5` on the python3 thread.

## 5) Is it really a pipeline cap?

The claim "pipeline cap of ~29 fps" is **not proven** for this app. The
experiment: run the same app with `ZUNE_PERFMODE=big` and `normal`
(`ztos.performance()` asks the phone's power manager how to treat the app;
`big` keeps the big cores open to it) over: scroll of the songs list (15 s),
page push (open an album 5 times), player playing 15 s. For each case record
the `zune-perf` lines (fps, `d_swap`, `draw_ms`, raster ms/s), `top -b -H -d 2
-n 5` and, read-only, `cat /sys/devices/system/cpu/cpu*/cpufreq/scaling_cur_freq`.

Reading: `d_swap` ≈ 33 ms with `draw` ≈ 1 ms ⇒ waiting for presentation; the
python3 thread above 90% or a high `draw_ms` ⇒ CPU-bound (does it change with
`big`?).

## 6) The swap0 experiment

`ZUNE_SWAP0=1` makes the GL layer's swap non-blocking (swap interval 0). With
interval 1 every frame waits for the compositor's frame callback after the
layer swap and then the host commit waits for another one: two serial waits,
~33 ms per frame. Run the same scenario as above with and without it and
compare `swaps` per second and `d_swap`. If it goes from ~30 to ~60 fps with
`draw_ms` unchanged the hypothesis holds; if nothing changes, or there is
flicker or tearing, drop it.
