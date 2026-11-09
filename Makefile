.PHONY: gates setup backend signal signal-keyboard signal-hw plot calibrate calibrate-cue live-test frontend frontend-https test demo-check

setup:
	cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
	cd signal && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
	cd frontend && npm install

backend:
	cd backend && .venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

signal:
	cd signal && .venv/bin/python run.py --source synthetic

# Keyboard demo: no scripted gestures reach the wheel, but /demo degrade still drops reliability.
signal-keyboard:
	cd signal && .venv/bin/python run.py --source synthetic --script quiet

# Hardware: make signal-hw PORT=/dev/tty.usbmodem1101  (find it with: ls /dev/tty.usb*)
signal-hw:
	cd signal && .venv/bin/python run.py --source arduino --port $(PORT)

# Filtered traces + thresholds; synthetic without PORT
plot:
	cd signal && .venv/bin/python -m tools.plot_live --filtered $(if $(PORT),--source serial --port $(PORT),)

# Guided calibration (~3 min) with PORT; instant synthetic dry run without
calibrate:
	cd signal && .venv/bin/python calibration.py $(if $(PORT),--source serial --port $(PORT),)

# Cue-driven calibration on the /calibrate page (dot + voice): make calibrate-cue PORT=/dev/cu.usbmodem1101
calibrate-cue:
	cd signal && .venv/bin/python calibration.py --source serial --port $(PORT) --cue

# Shuffled-prompt check of the current calibration (30 prompts on the /calibrate page): make live-test PORT=/dev/cu.usbmodem1101
live-test:
	cd signal && .venv/bin/python -m tools.live_confusion --port $(PORT)

frontend:
	cd frontend && npm run dev

# Self-signed HTTPS so phone browsers allow HELP notifications (accept the certificate warning once).
frontend-https:
	cd frontend && HTTPS=1 npm run dev

test:
	cd backend && .venv/bin/pytest -q
	cd signal && .venv/bin/pytest -q
	cd frontend && npm run build

# Plays the 3-step stage demo against a throwaway backend; prints PASS/FAIL per step.
demo-check:
	backend/.venv/bin/python scripts/demo_check.py

# The agent loop's definition of done (tests, build, lint, demo-check). `scripts/gates.sh quick` skips demo-check.
gates:
	scripts/gates.sh
