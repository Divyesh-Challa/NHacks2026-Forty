# Stage runbook

For the 5-minute demo. Everything here uses synthetic data and fake accounts.

Read this once the night before. Run the pre-show checklist at least 30 minutes before you go on.

## Who runs what

| Device | Runs | Opens |
| --- | --- | --- |
| **Stage laptop** | backend, signal service, frontend dev server. All terminals stay on the laptop screen. | projector: `https://localhost:5173/patient/p1` |
| **Presenter device** (second laptop or phone, never the projector) | nothing | `https://<LAN IP>:5173/demo` |
| **Caregiver phone** | nothing | `https://<LAN IP>:5173/caregiver` |
| **Wearer** | electrodes → Arduino → stage laptop | nothing |

`<LAN IP>` is the **Network** URL the dev server prints when it starts (the `Network:` line in terminal 2). Use that exact address.

We run one dev server mode for the whole show: `make frontend-https`. That is the mode the caregiver phone needs for notifications. Everything then uses `https://`. If you fall back to plain `make frontend`, replace `https` with `http` everywhere below, including the pairing origin.

Accept the self-signed certificate warning once on each device.

## Pre-show checklist

Run these in order. Terminals are numbered so you know which one to look at.

**Once per laptop (skip if already done):**

```bash
cp .env.example .env      # optional: add ANTHROPIC_API_KEY. Without it, prediction uses the fixed fallback list
make setup                # venvs + npm install
```

**Terminal 1: backend**

```bash
make backend              # http://localhost:8000
```

**Terminal 2: frontend**

```bash
make frontend-https       # prints the Network URL: use it on the phones
```

**Terminal 3: signal service, real electrodes**

1. Check the electrodes first, with the Arduino plugged in:

   ```bash
   ls /dev/tty.usb*                       # find the port
   make plot PORT=/dev/tty.usbmodemXXXX   # check placement: each gesture crosses the solid line, rest stays inside the dashed floor
   ```

2. Close `make plot` with Ctrl+C before you go on. Two readers on the same serial port each get part of the data, so the numbers are wrong.

3. Optional, about 3 minutes, with the wearer:

   ```bash
   make calibrate PORT=/dev/tty.usbmodemXXXX
   ```

4. Start the live signal (only after `make plot` is closed):

   ```bash
   make signal-hw PORT=/dev/tty.usbmodemXXXX
   ```

**Terminal 3 instead, if there are no electrodes:** see fallback 1.

**Pair the stage laptop (before the pitch):**

1. In the browser you will project from, open `https://localhost:5173/pair`.
2. Enter the demo code `123456` and press Pair.
3. Open `https://localhost:5173/patient/p1`. The header should say **Paired**, not **Not paired · open /pair**.

Rules for pairing:

- Pair in the exact browser, profile and URL origin the projector shows. The token lives in that origin's localStorage. `http://localhost:5173`, `https://localhost:5173` and `http://<LAN IP>:5173` are three different places.
- Pair before you open the patient screen. If it was already open, reload it after pairing. A tab that was open first keeps showing "Not paired" until it reloads.
- The token lasts 365 days, so one pairing is enough. Keep the same browser profile.
- The demo code is `DEMO_PAIR_CODE` in `backend/app/seed.py`. The backend checks it against the database.
- The **Paired** header is in the open PR `loop/pairing-token`. Until that merges, the header will not show it. The pairing itself works: `/pair` stores the token under `relay_patient_token`.

**Caregiver phone:**

1. Join the phone to the same Wi-Fi as the laptop.
2. Open `https://<LAN IP>:5173/caregiver`. Accept the certificate warning.
3. Log in with `caregiver@example.com` / `relay-demo`. The login tap unlocks the HELP sound.
4. If the page offers "enable notifications", allow them.
5. Keep the screen on and the Relay page in the foreground. No lock, no app switching. Reloading the page resets the sound unlock, so after any reload tap **Tap to enable HELP alert sound** again.

**Presenter device:**

1. Open `https://<LAN IP>:5173/demo`. Accept the certificate warning.
2. Check that the top bar says **Live**. If it says **Backend offline**, start `make backend`.

**Final check:**

```bash
make demo-check           # plays the 3 steps against a throwaway backend. Must print DEMO READY
```

`make demo-check` does not use your real database or devices. It only proves the code path works. Run it on the stage laptop after the other steps.

**Projector rules:**

- Use an **extended** display, not mirroring. The patient browser goes on the projector. All terminals stay on the laptop screen.
- Do not show the backend terminal on the projector. The uvicorn access log prints WebSocket URLs, and those include auth tokens. Both fallbacks need the terminals, so keep them on the laptop.
- Put the patient screen full screen (browser full-screen, F11 on most laptops).

## The 3-step pitch

Keep `https://<LAN IP>:5173/demo` on the presenter device. The audience sees the projector only.

**Step 1: select a phrase with eye movement.**
- Presenter: open the patient screen in full screen.
- Wearer (or keyboard): look left and right to reach "I need water". Accept it. Relay speaks it.
- Audience sees: the board in split mode, the phrase spoken aloud.

**Step 2: eyes decline, switch to jaw scan.**
- Presenter: press **Degrade eyes** on `/demo`.
- Wearer: keep looking left and right and double-blinking at full effort until the banner appears. Reliability only moves when the wearer makes attempts. If the wearer stops, the switch stops.
- Audience sees: the banner **"Eye movement and blinking reliability fell below 60%. Switching to scan mode with jaw clench to select."** The board changes to scan mode. Jaw clench now selects.
- Known issue until the single-banner fix lands: eye movement and blink can drop a few seconds apart. You may first see **"Eye movement reliability fell below 60%. Switching to double blink and jaw clench."** (still split mode), then the scan banner 5 to 10 s later. Keep talking; don't press anything again.
- Timing: Relay switches after **10 readings in a row below 60%**. The signal service sends one reliability reading per second (`reliability_interval_ms = 1000` in `config/relay.toml`), so the rule itself takes about 10 s. The README measured about **19 s** from the click to the switch on the synthetic source, because the rolling accuracy window has to fall first. On hardware, expect **15 to 20 s while the wearer keeps trying**.
- Wearer: finish the next message with a jaw clench.

**Step 3: call for help.**
- Wearer: hold a jaw clench for 2 s. Or, on the patient screen, hold **H** for 2 s.
- Audience sees: the caregiver phone sounds and shows **HELP**. The patient screen shows "HELP sent to caregiver". Click that overlay to dismiss it.

## Reset between run-throughs

1. On `/demo`, press **Restore all**.
2. Wearer: keep looking left and right and double-blinking at full effort until split returns. Reliability only moves on attempts.
3. Wait for recovery. Relay switches back to split only after **20 readings in a row at or above 75%**, about 20 s at one reading per second, plus the time the wearer needs to make the attempts. The README measured about 23 s on the synthetic source.
4. On `/demo`, the run sheet says "Back to split after 20 readings above 75%". The **Switches** box shows the switch back.
5. Clean up the other screens:
   - On the patient screen, click the "HELP sent to caregiver" overlay to dismiss it.
   - On the caregiver phone, tap the red **HELP requested** banner to acknowledge it.
   - If you pressed **M** during the run, press **M** again. The manual override does not clear itself.

## Fallbacks

**1. Electrodes fail → synthetic signal and keyboard.**

Stop terminal 3 (Ctrl+C), then run:

```bash
cd signal && .venv/bin/python run.py --source synthetic --script none
```

Drive the patient screen with the keyboard:

| Key | Command |
| --- | --- |
| ← / → | LEFT / RIGHT |
| Space | SELECT |
| Backspace | BACK |
| Hold H for 2 s | HELP |
| M | toggle split / scan (manual override) |

The arrow keys and Space only change the patient screen. They never reach the signal service, so they do **not** move the reliability numbers. For demo steps 2 and reset, type eye attempts into **terminal 3** instead. Click into terminal 3 first. The keys are `l` (look left), `r` (look right), `b` (double blink), `j` (clench), `h` (hold).

*Step 2 with the keyboard:*
1. Press **Degrade eyes** on `/demo`.
2. In terminal 3, type this and press Enter:

   ```
   lrlrlrbbbbbb
   ```

3. Wait about 15 s. If the scan banner has not appeared, type the same line again. Repeat up to three times. Rehearse this once before the show, because the exact count depends on the timing.
4. Expect about 25% of the typed attempts to be detected. Those move the patient screen as normal commands, so the board will move while you type. That is expected.

*Reset with the keyboard:*
1. Press **Restore all** on `/demo`.
2. In terminal 3, type `lrlrlrbbbbbb` and press Enter. Repeat until split returns, up to three times. The accuracy window needs fresh good attempts to refill.

*Expect stray commands.* Even with `--script none`, the simulated detector produces about one false trigger every 30 s while the signal is at rest. In scan mode a stray jaw clench is a SELECT and can speak a phrase. Keep going if it happens. Do not explain it away in front of the audience. Press BACK if it matters.

Do **not** use **M** to switch to scan for this step. It works, but the banner reads "Switched to scan mode by hand (testing)", which is not the demo.

Do **not** use `make signal` here. It is the Makefile target for the synthetic source, but it runs a built-in gesture loop (look left, blink, look right, clench…) that moves the board by itself. The `--script none` form above turns that loop off. It is a `run.py` flag, not a Makefile target.

**2. Backend crash → restart it.**

```bash
make backend              # in terminal 1, after Ctrl+C
```

- The signal service (terminal 3) retries every 2 s and reconnects by itself.
- The patient, caregiver and `/demo` pages reconnect by themselves. Their WebSocket client (`frontend/src/lib/ws.ts`) waits 1.5 s and tries again.
- Mode is held in memory. After a restart the backend starts from fresh readings. If the eyes were degraded before the crash, the signal service still has them degraded, so the switch to scan happens again. Press **Restore all** on `/demo` to reset.
- If a page looks stuck after the restart, reload it. Boards and the pairing token come back from the database and the browser.
- **After any reload, the caregiver phone needs its sound unlocked again.** Tap **Tap to enable HELP alert sound**. Keep the screen on and the Relay page in the foreground.

**3. No venue Wi-Fi → phone hotspot.**

Use this fallback when the venue Wi-Fi is down or when the phone cannot load the Network URL even though it shows Wi-Fi as connected. Venue Wi-Fi with client isolation does this: the laptop and the phone are on the same network, but cannot reach each other.

1. Turn on the phone's personal hotspot.
2. Join the stage laptop and the presenter device to it. The phone that hosts the hotspot does not need to join.
3. Find the laptop's new address:

   ```bash
   ipconfig getifaddr en0    # macOS: prints the laptop's IP on en0 (Wi-Fi on most Macs)
   ```

   If that prints nothing, check System Settings → Wi-Fi for the address.
4. A new IP is a new origin for the browser. On each device:
   - Caregiver phone: open the new `https://<new IP>:5173/caregiver`, accept the certificate again, **log in again**, then tap **Tap to enable HELP alert sound** and allow notifications.
   - Presenter device: open `https://<new IP>:5173/demo` and accept the certificate again.
   - Projector: nothing to do. It uses `https://localhost:5173`, which the new IP does not change. Only re-pair the projector if it was opened on the LAN IP instead of localhost.
5. The dev server listens on all interfaces, so it does not need a restart. Restart `make frontend-https` only if you want the Network line printed again.

If the phone still cannot load `https://<new IP>:5173` while both devices show a connection, the network is isolating clients. Move everything to the phone hotspot as above. If that is not possible, skip the live HELP step and say so on stage.

**4. Phone notifications blocked.**

HELP still sounds and shows a red banner on the caregiver page. iPhone Safari only shows web notifications for sites added to the Home Screen. Rely on the sound and the banner there.

**5. Projector resolution.**

Nothing in the code handles projector resolution. The patient screen is built for large targets. If text is cut off, change the projector's scaling in the OS, not the app.

## Credentials and codes

- Caregiver login: `caregiver@example.com` / `relay-demo`
- Patient pairing code: `123456`

Both are fake. The caregiver password can be changed with `DEMO_CAREGIVER_PASSWORD` in `.env`.

## Checked

What was run, and what was only checked against the Makefile.

**Run:**
- `make demo-check`: printed **DEMO READY**. All four steps and the prediction check passed. The remap banner text above comes from this run.
- `make -n` on every target listed in the checklist: `setup`, `backend`, `signal`, `signal-hw PORT=…`, `plot` (with and without `PORT`), `calibrate` (with and without `PORT`), `frontend`, `frontend-https`, `test`, `demo-check`, `gates`.
- `cd signal && .venv/bin/python run.py --help`: confirmed `--script none`, `--source`, `--port`.
- `ipconfig getifaddr en0`: printed an IP address.
- Read in code: pairing TTL (`backend/app/auth.py` `pair()`, 365 days), caregiver login TTL (7 days, the default), reliability rate (1 s), remap and recover windows (10 and 20), the `ws.ts` reconnect delay (1.5 s), the signal service reconnect (2 s), `DEMO_PAIR_CODE` in `backend/app/seed.py`.
- Read in code (keyboard fallback): the keyboard sim (`frontend/src/lib/keyboardSim.ts`) handles commands on the patient page only. Terminal keys `l/r/b/j/h` queue gesture attempts in the synthetic source, and every attempt is recorded for reliability (`signal/sources/synthetic.py` `trigger`/`attempt`). The M banner text comes from `backend/app/input_manager.py` `force_mode`.
- Read in code (reset and phone): the patient overlay dismisses on click (`frontend/src/pages/Patient.tsx`). The caregiver urgent banner clears on tap (`frontend/src/pages/Caregiver.tsx`). The alert-sound unlock is a module-level audio context (`frontend/src/lib/alertSound.ts`), so a reload resets it.
- Read in code (`/demo`): button labels "Degrade eyes", "Eye movement only", "Restore all"; the remap countdown ("Low n of 10", "N more low readings"); reliability bars with cutoff marks at 60% and 75%; the Switches box (`frontend/src/pages/Demo.tsx`).

**Checked against the Makefile or code only (not run):**
- `make setup`, `make test`, `make gates`: they install, build or run the full gate. Not run here.
- `make plot`, `make calibrate`, `make signal-hw`: hardware targets. Not run.
- `make frontend`, `make frontend-https`, `make backend`: `make -n` only. Starting them here was not confirmed, so the exact `Network:` line format is from `frontend/vite.config.ts`, not from output.
- `make signal`: `make -n` only. The scripted loop is from `signal/sources/synthetic.py` (`DEFAULT_SCRIPT`).
- The keyboard-fallback typing counts (`lrlrlrbbbbbb`, up to three repeats) are from code reading, not a live run. Rehearse once.
- The pairing "Paired" header: not on `main` yet. Written as the intended procedure.
