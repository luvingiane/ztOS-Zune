# PROFILE-ON-B.md — CPU profiling on the phone

Purpose: the app's `python3` thread was at ~98% of one core while scrolling
(measured with `top -H`). With `ZUNE_PROFILE=1` the app collects `cProfile` and
writes, every 10 s, the **top 40 functions by cumulative time and by own time**
to two places:

- `~/.local/state/ztos/dev.oneplus2.zunehd.log` (the app's stderr)
- `~/.local/state/ztos/zune-profile.txt` (a dedicated append file)

`ZUNE_PERF=1` stays active alongside it (same log: frames, tap_paint,
tex_live…).

## Steps (on the phone, once)

1. Install the build with the dedicated menu entry (see INSTALL.md): besides
   `dev.oneplus2.zunehd.desktop` there is `dev.oneplus2.zunehd-profile.desktop`
   (`Exec=env ZUNE_PROFILE=1 ZUNE_PERF=1 …/dev.oneplus2.zunehd`).
   `printf 'apps\n' > "$XDG_RUNTIME_DIR/ztmetro.ctl"` makes the shell re-read it.
2. Open **"Zune HD (profile)"** from the menu.
3. Scroll the lists (especially **songs**) up and down for ~15 s, open an
   album, go back.
4. Close the app.

## What to collect

```sh
scp <user>@<phone-ip>:~/.local/state/ztos/zune-profile.txt /tmp/
scp <user>@<phone-ip>:~/.local/state/ztos/dev.oneplus2.zunehd.log /tmp/
# and while scrolling, to confirm the CPU goal:
top -H -p $(pgrep -f 'ztos/apps/dev.oneplus2.zunehd' | head -1) -d 2 -n 4
```

Goal: the `python3` thread **under 50%** while scrolling; no `MESA: error` in
the log; `tex_live_bytes` in the `zune-perf` line under control.
