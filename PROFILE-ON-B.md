# PROFILE-ON-B.md — profilazione CPU su B (solo il proprietario la esegue)

Scopo: il thread `python3` dell'app era al ~98% di un core durante lo
scorrimento (misura `top -H` di Claude, 8/11). Con `ZUNE_PROFILE=1` l'app
raccoglie `cProfile` e scrive ogni 10 s le **top 40 funzioni per tempo
cumulativo e per tempo proprio** in due posti:

- `~/.local/state/ztos/dev.oneplus2.zunehd.log` (stderr dell'app)
- `~/.local/state/ztos/zune-profile.txt` (appendice dedicata)

`ZUNE_PERF=1` resta attivo insieme (stesso log: frame, tap_paint, tex_live…).

## Passi (sul telefono, da fare una volta)

1. Installa la build con dentro la voce di menu dedicata (INSTALL.md): oltre a
   `dev.oneplus2.zunehd.desktop` c'è `dev.oneplus2.zunehd-profile.desktop`
   (`Exec=env ZUNE_PROFILE=1 ZUNE_PERF=1 …/dev.oneplus2.zunehd`).
   `printf 'apps\n' > "$XDG_RUNTIME_DIR/ztmetro.ctl"` per farla rileggere.
2. Apri la voce **"Zune HD (profile)"** dal menu.
3. Scorri le liste (soprattutto **songs**) su e giù per ~15 s, apri un album,
   torna indietro.
4. Chiudi l'app.

## Cosa riportare a Claude

```sh
scp <user>@<phone-ip>:~/.local/state/ztos/zune-profile.txt /tmp/
scp <user>@<phone-ip>:~/.local/state/ztos/dev.oneplus2.zunehd.log /tmp/
# e durante lo scorrimento, per confermare l'obiettivo CPU:
top -H -p $(pgrep -f 'ztos/apps/dev.oneplus2.zunehd' | head -1) -d 2 -n 4
```

Obiettivo: thread `python3` **sotto il 50%** durante lo scorrimento; nessun
`MESA: error` nel log; `tex_live_bytes` nel formato `zune-perf` sotto controllo.
