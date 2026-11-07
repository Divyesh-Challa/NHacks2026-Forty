.PHONY: setup backend signal frontend frontend-https test

setup:
	cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
	cd signal && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
	cd frontend && npm install

backend:
	cd backend && .venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

signal:
	cd signal && .venv/bin/python run.py --source synthetic

frontend:
	cd frontend && npm run dev

# Self-signed HTTPS so phone browsers allow HELP notifications (accept the certificate warning once).
frontend-https:
	cd frontend && HTTPS=1 npm run dev

test:
	cd backend && .venv/bin/pytest -q
	cd signal && .venv/bin/pytest -q
	cd frontend && npm run build
