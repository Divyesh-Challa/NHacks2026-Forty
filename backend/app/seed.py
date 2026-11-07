"""Synthetic demo data only — obviously fake. Never real patient data."""

DEMO_PATIENT_ID = "p1"
DEMO_PATIENT_NAME = "Test Patient (FAKE)"
DEMO_PAIR_CODE = "123456"
DEMO_CAREGIVER_EMAIL = "caregiver@example.com"

DEFAULT_BOARDS: list[dict] = [
    {
        "id": "needs",
        "title": "Needs",
        "items": ["I need water", "I'm hungry", "Bathroom", "Reposition me", "Too hot", "Too cold", "I'm in pain"],
    },
    {"id": "people", "title": "People", "items": ["Call my family", "Call the nurse"]},
    {"id": "feelings", "title": "Feelings", "items": ["I'm happy", "I'm tired", "I'm frustrated", "Thank you", "I love you"]},
    {"id": "yesno", "title": "Yes / No", "items": ["Yes", "No"]},
]
