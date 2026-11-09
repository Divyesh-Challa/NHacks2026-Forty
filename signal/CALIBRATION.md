# Recalibrating direction detection

Run commands from the repository root. Stop the hardware signal service, plotter, and live test before calibration: only one process can read the Arduino port.

1. Find the current port with `ls /dev/cu.usb*`.
2. Run `make plot PORT=<port>`. Check A0 and A1 are stable near midscale at rest and that movements are distinct. Fix drifting or clipping signals before calibrating, then close the plotter.
3. Start `make frontend` in a separate terminal.
4. Run `make calibrate-cue PORT=<port>` and open http://localhost:5173/calibrate. Press Start.
5. Keep still during the initial 20 seconds. For each cue, move only your eyes toward the dot, follow it back to centre, and wait there. Avoid turning your head, tensing your face, or forcing unusually large glances. Blink twice only for the double-blink cue; normal spontaneous blinks can still occur.
6. Read the report. Each direction has its own threshold and exact-command count. Missed prompts and extra commands are reported separately. Accuracy now requires exactly the requested command, so compare new results with the new live test rather than old calibration percentages.
   Background noise uses the median absolute deviation within initial rest windows so brief spontaneous blinks do not set direction thresholds. Transient peaks are printed separately; their unwanted commands still reduce the exact score and count toward rest false triggers.
7. A run with saturation, ambiguous polarity, insufficient usable movements, or directions below the noise margin is saved as a rejected candidate under `signal/recordings/`. It does **not** replace `signal/calibration.json` or post to the backend. Resolve the warning and repeat. An accepted run automatically backs up the previous active file to `signal/calibration.prev.json`.
8. Run `make live-test PORT=<port>` on the same page. Aim for at least 25/30 exact trials, with all four directions represented correctly. The test now scores device timestamps and saves trial boundaries, settings, and detections in a JSON file beside the CSV for reproducible replay.
9. Close the test and start/restart `make backend` and `make signal-hw PORT=<port>` in separate terminals. The signal service loads calibration once at startup. Use the unguided wheel (`0` disables the demo guide) when verifying real command accuracy.

Vertical commands wait roughly 700 ms after classification to check nearby horizontal looks and blink recovery. A delayed response is expected; do not repeat the glance immediately. A scan-mode transition after a poor calibration reflects measured reliability and should not be hidden by manually increasing its score.

The detector changes are intended to improve classification, but fresh hardware calibration is still required. Older recordings contain noisy vertical rest segments; removing the old fixed vertical threshold can correctly reject those recordings rather than silently accept noise as commands. Do not copy the old threshold of 28 back just to obtain a higher hit rate.
