# Stage runbook

For the 5-minute demo. Everything here uses synthetic data and fake accounts.

Read this once the night before. Run the pre-show checklist at least 30 minutes before you go on.

## Who runs what

| Device | Runs | Opens |
| --- | --- | --- |
| **Stage laptop** | backend, signal service, frontend dev server | projector: `https://localhost:5173/patient/p1` |
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

2. Optional, about 3 minutes, with the wearer:

   ```bash
   make calibrate PORT=/dev/tty.usbmodemXXXX
   ```

3. Start the live signal:

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
3. Log in with `caregiver@example.com` / `relay-demo`.
4. The login tap unlocks the HELP sound. If the page offers "enable notifications", allow them.

**Presenter device:**

1. Open `https://<LAN IP>:5173/demo`. Accept the certificate warning.
2. Check that the top bar says **Live**. If it says **Backend offline**, start `make backend`.

**Final check:**

```bash
make demo-check           # plays the 3 steps against a throwaway backend. Must print DEMO READY
```

`make demo-check` does not use your real database or devices. It only proves the code path works. Run it on the stage laptop after the other steps.

**Projector rules:**

- Do not show the backend terminal on the projector. The uvicorn access log prints WebSocket URLs, and those include auth tokens.
- Put the patient screen full screen (browser full-screen, F11 on most laptops).

## The 3-step pitch

Keep `https://<LAN IP>:5173/demo` on the presenter device. The audience sees the projector only.

**Step 1: select a phrase with eye movement.**
- Presenter: open the patient screen in full screen.
- Wearer (or keyboard): look left and right to reach "I need water". Accept it. Relay speaks it.
- Audience sees: the board in split mode, the phrase spoken aloud.

**Step 2: eyes decline, switch to jaw scan.**
- Presenter: press **Degrade eyes** on `/demo`.
- Audience sees: the banner **"Eye movement and blinking reliability fell below 60%. Switching to scan mode with jaw clench to select."** The board changes to scan mode. Jaw clench now selects.
- Known issue until the single-banner fix lands: eye movement and blink can drop a few seconds apart. You may first see **"Eye movement reliability fell below 60%. Switching to double blink and jaw clench."** (still split mode), then the scan banner 5 to 10 s later. Keep talking; don't press anything again.
- Timing: Relay switches after **10 readings in a row below 60%**. The signal service sends one reliability reading per second (`reliability_interval_ms = 1000` in `config/relay.toml`), so the rule itself takes about 10 s. The README measured about **19 s** from the click to the switch on the synthetic source, because the rolling accuracy window has to fall first. Expect 15 to 20 s on stage.
- Wearer: finish the next message with a jaw clench.

**Step 3: call for help.**
- Wearer: hold a jaw clench for 2 s. Or, on the patient screen, hold **H** for 2 s.
- Audience sees: the caregiver phone sounds and shows **HELP**. The patient screen shows "HELP sent to caregiver".

## Reset between run-throughs

1. On `/demo`, press **Restore all**.
2. Wait for recovery. Relay switches back to split only after **20 readings in a row at or above 75%**, about 20 s at one reading per second. The README measured about 23 s.
3. On `/demo`, the run sheet says "Back to split after 20 readings above 75%". The **Switches** box shows the switch back.

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
| M | toggle split / scan |

Demo steps 2 and 3 still work: press **Degrade eyes** on `/demo`, then hold H for HELP.

Do **not** use `make signal` here. It is the Makefile target for the synthetic source, but it runs a built-in gesture loop (look left, blink, look right, clench…) that moves the board by itself. The `--script none` form above turns that loop off. It is a `run.py` flag, not a Makefile target.

**2. Backend crash → restart it.**

```bash
make backend              # in terminal 1, after Ctrl+C
```

- The signal service (terminal 3) retries every 2 s and reconnects by itself.
- The patient, caregiver and `/demo` pages reconnect by themselves. Their WebSocket client (`frontend/src/lib/ws.ts`) waits 1.5 s and tries again.
- Mode is held in memory. After a restart the backend starts from fresh readings. If the eyes were degraded before the crash, the signal service still has them degraded, so the switch to scan happens again. Press **Restore all** on `/demo` to reset.
- If a page looks stuck after the restart, reload it. Boards and the pairing token come back from the database and the browser.

**3. No venue Wi-Fi → phone hotspot.**

1. Turn on the phone's personal hotspot.
2. Join the stage laptop, the presenter device and the caregiver phone to it. The phone that hosts the hotspot does not need to join.
3. Find the laptop's new address:

   ```bash
   ipconfig getifaddr en0    # macOS: prints the laptop's IP on en0 (Wi-Fi on most Macs)
   ```

   If that prints nothing, check System Settings → Wi-Fi for the address.
4. Use `https://<new IP>:5173/...` on the phones and presenter device. The dev server listens on all interfaces, so it does not need a restart.
5. Restart `make frontend-https` if you want the Network line printed again.

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

**Checked against the Makefile or code only (not run):**
- `make setup`, `make test`, `make gates`: they install, build or run the full gate. Not run here.
- `make plot`, `make calibrate`, `make signal-hw`: hardware targets. Not run.
- `make frontend`, `make frontend-https`, `make backend`: `make -n` only. Starting them here was not confirmed, so the exact `Network:` line format is from `frontend/vite.config.ts`, not from output.
- `make signal`: `make -n` only. The scripted loop is from `signal/sources/synthetic.py` (`DEFAULT_SCRIPT`).
- The pairing "Paired" header: not on `main` yet. Written as the intended procedure.
