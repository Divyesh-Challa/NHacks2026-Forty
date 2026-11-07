"""Point the app at a throwaway SQLite file before anything imports app.config."""

import os
import tempfile

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/test.db"
os.environ["DEMO_CAREGIVER_PASSWORD"] = "test-password"
