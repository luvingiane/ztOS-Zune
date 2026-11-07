# PERF-ON-B.md — misure sul telefono B (solo il proprietario le esegue; B non si tocca da qui)

Scopo: con `ZUNE_PERF=1` sia **Zune HD** (`dev.oneplus2.zunehd`) sia l'app
minima di riferimento (**Zune Ref**, `dev.oneplus2.zuneref`) scrivono nel loro
log (`~/.local/state/ztos/<id>.log`) una riga `zune-perf` al secondo con:
frame/s (paintGL), swap/s (frameSwapped = frame presentados), intervallo
frame-to-frame avg/min/max (d_paint e d_swap), ms CPU dentro `zsdk_draw` e
numero di quad, frame con quad identici al precedente (`identical` =
aggiornamenti senza cambio di contenuto), texture caricate (numero/byte/dim),
ms delle passate raster Qt, refresh del layer, paint dei widget, cambi di
contenuto (`changes`). Vedi `perf.py` per il formato esatto.

Obiettivo: ≥ 30 fps reali (d_swap avg ≤ 33 ms), 60 se possibile (≤ 16.7 ms).

## 1) Copia i due binari su B (dal PC)

```sh
cd ~/Github_Clones/ztos-zune-sdk
ssh <user>@<phone-ip> 'mkdir -p ~/.local/share/ztos/apps ~/.local/share/applications ~/.local/share/icons/hicolor/scalable/apps'
scp dist/dev.oneplus2.zunehd ref/dist/dev.oneplus2.zuneref <user>@<phone-ip>:~/.local/share/ztos/apps/
ssh <user>@<phone-ip> 'chmod 755 ~/.local/share/ztos/apps/dev.oneplus2.zunehd ~/.local/share/ztos/apps/dev.oneplus2.zuneref'
ssh <user>@<phone-ip> 'cat > ~/.local/share/icons/hicolor/scalable/apps/dev.oneplus2.zuneref.svg' < ref/icon.svg
ssh <user>@<phone-ip> 'cat > ~/.local/share/applications/dev.oneplus2.zuneref.desktop' <<'DESKTOP'
[Desktop Entry]
Type=Application
Name=Zune Ref
Comment=Minimal SDK reference app for perf comparison
Exec=/home/zerone/.local/share/ztos/apps/dev.oneplus2.zuneref
Icon=dev.oneplus2.zuneref
Terminal=false
StartupWMClass=ztos.dev.oneplus2.zuneref
Categories=Audio;Music;
X-ZtOS-Id=dev.oneplus2.zuneref
X-ZtOS-Version=0.1.0
DESKTOP
# (il .desktop di dev.oneplus2.zunehd è già quello di INSTALL.md)
# fa rileggere la lista app alla shell (dentro la sessione ztOS):
printf 'apps\n' > "${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/ztmetro.ctl"
```

## 2) Avvio instrumentato (ZUNE_PERF=1) — un comando per app

Da una shell **dentro la sessione ztOS** (stesso ambiente del menu: lì c'è già
`FD_MESA_DEBUG=sysmem`, `QT_QPA_PLATFORM=wayland`, `ZTMETRO_SCALE=3`):

```sh
ZUNE_PERF=1 ~/.local/share/ztos/apps/dev.oneplus2.zuneref   # rifai: lista che scorre + push pagina
ZUNE_PERF=1 ~/.local/share/ztos/apps/dev.oneplus2.zunehd    # home: ferma, scroll, tap entra/esci
```

Se il tuo ssh **non** è nella sessione grafica, copia prima l'ambiente della
shell (sola lettura) e poi lancia:

```sh
eval "$(tr '\0' '\n' < /proc/$(pgrep -f 'ztmetro' | head -1)/environ \
  | grep -E '^(XDG_RUNTIME_DIR|WAYLAND_DISPLAY|DISPLAY|QT_QPA_PLATFORM|FD_MESA_DEBUG|ZTMETRO_SCALE|XDG_SESSION_TYPE)=' \
  | sed 's/$/;/')"
ZUNE_PERF=1 ~/.local/share/ztos/apps/dev.oneplus2.zunehd
```

In alternativa, dal menu senza toccare l'ambiente: avvia normalmente e il log
cresce lo stesso (il bootstrap dell'SDK manda stderr nel log), ma senza
`ZUNE_PERF=1` i contatori restano spenti — quindi per le misure usa i comandi
sopra.

## 3) Cosa fare mentre gira (per scenario) e poi raccogliere il log

Per ogni app: (a) lascia la prima schermata ferma 5 s; (b) scorri la lista
su e giù per 10 s; (c) entra in una pagina e torna indietro (turnstile) 3
volte; (d) su Zune HD apri la strip/quickplay (now playing) se presente.
Poi:

```sh
cat ~/.local/state/ztos/dev.oneplus2.zuneref.log
cat ~/.local/state/ztos/dev.oneplus2.zunehd.log
# dal PC: scp <user>@<phone-ip>:'~/.local/state/ztos/dev.oneplus2.zune*.log' /tmp/
```

Mentre scrolli, annota anche: CPU libera totale (`top -bn1 | head`), clock GPU
(la stessa misura di `gfx3d_clk_src` che hai già fatto), e quanto "va fluido"
a occhio (1 = a scatti, 5 = fluido).

## 4) Modulo di risposta (compila e incolla qui / in STATO.md)

| app | scenario | fps (swaps/s) | d_swap avg/max ms | draw ms max | quad max | identical/s | upload byte/s | raster ms/s | paints/s | changes/s | fluido (1-5) | CPU libera | clk GPU |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| zuneref | ferma | | | | | | | | | | | | |
| zuneref | scroll | | | | | | | | | | | | |
| zuneref | push/pop | | | | | | | | | | | | |
| zunehd | home ferma | | | | | | | | | | | | |
| zunehd | scroll home | | | | | | | | | | | | |
| zunehd | turnstile entra/esci | | | | | | | | | | | | |
| zunehd | now playing | | | | | | | | | | | | |

Lettura: se `zuneref` è a 60 fps e `zunehd` no → il costo è nel contenuto
dell'app (raster ms/s e uploads lo dicono); se anche `zuneref` lagga →
pipeline SDK/telefono (d_swap alto con draw ms basso = pacing/attesa frame
Wayland; upload ms alti = costo memcpy in `sysmem`; identical alto =
 ridisegna senza cambiado). Incolla anche 3-5 righe `zune-perf` raw per
ciascuna app.
