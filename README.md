# Relay

Relay is an accessible communication system for people with ALS. It lets a
person choose and speak messages using eye movement and double blinks, without
requiring a camera. 

All data in this demonstration is synthetic.

## Try Relay

### What you need

- A computer running **macOS, Windows, or Linux**
- **Python 3.11 or newer**
- **Node.js 20 or newer**
- An internet browser such as Chrome, Edge, Firefox, or Safari

### 1. Download the project

Visit the [public GitHub repository](https://github.com/Divyesh-Challa/NHacks2026-Forty)
and choose **Code → Download ZIP**. Unzip the download and open the extracted
`NHacks2026-Forty` folder.

### 2. Install and start Relay

Open a terminal in that folder.

**macOS/Linux**

```bash
make setup
```

**Windows**

```powershell
cd backend
py -3 -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
cd ..\signal
py -3 -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
cd ..\frontend
npm install
cd ..
```

### 3. Use the real hardware

Connect two BioAmp EXG Pills to an Arduino Uno:

- Pill 1: `VCC` to `5V`, `GND` to `GND`, `OUT` to `A0`; place electrodes near
  the outer corners of the eyes.
- Pill 2: `VCC` to `5V`, `GND` to `GND`, `OUT` to `A1`; place electrodes above
  and below one eye.
- Connect the reference electrode behind the ear or on the forehead.

Use the computer on battery power while recording. Install
[Arduino CLI](https://arduino.github.io/arduino-cli/) and the Arduino Uno
board package, then flash the Relay program once:

```text
arduino-cli core update-index
arduino-cli core install arduino:avr
arduino-cli compile -b arduino:avr:uno arduino/relay_exg
arduino-cli upload -b arduino:avr:uno -p PORT arduino/relay_exg
```

Replace `PORT` with the Arduino port shown by
`arduino-cli board list`:

- macOS: `/dev/cu.usbmodem...`
- Linux: `/dev/ttyACM0`
- Windows: `COM3`

Close the Arduino Serial Monitor and any other program using the port. Then
calibrate the sensors:

```text
make frontend
make calibrate-cue PORT=PORT
```

Open **http://localhost:5173/calibrate**, select **Start**, and follow the
on-screen calibration prompts. When calibration finishes, close the calibration
tools.

Start Relay in three terminal windows:

```text
make backend
make signal-hw PORT=PORT
make frontend
```

On Windows, run the matching commands from the Makefile with the project’s
Python environments, or use Windows Subsystem for Linux (WSL).

### 4. Open the demonstration

Open **http://localhost:5173/patient/p1** in your browser. Use eye movements
and double blinks to control Relay.

### Keyboard demonstration option

If the hardware is unavailable, the keyboard signal simulator can demonstrate
the interface. Start Relay in three terminal windows instead:

```text
make backend
make signal-keyboard
make frontend
```

Then open **http://localhost:5173/patient/p1**. Keyboard controls are:

- Arrow keys: move through choices
- Space: select
- `B`: accept a suggested message
- Backspace: go back
- Hold `H`: send a caregiver alert

To view the caregiver screen, open
**http://localhost:5173/caregiver** in another browser tab.

Demo login:

- Email: `caregiver@example.com`
- Password: `relay-demo`


## Credits

- **Team member 1:** Divyesh Challa 
- **Team member 2:** Tolu Bankole 
- **Team member 3:** Lawrence Velilla
- **Team member 4:** Nathaniel Edillon 
- **Team member 5:** Fikayo Ebyn-Ahisu 

Built for natHacks 2026 — Healthcare & Accessibility.
