"""Seeds ~2 weeks of realistic-looking demo data (manual courses, graded
tasks with varying start-lead-times, study sessions) so the Analytics
Dashboard and AI Recommendation System can be exercised end-to-end without a
live Canvas/Gradescope/PrairieLearn account. Also backdates
`data_collection_started_at` so recommendations are immediately eligible.

Additive - never wipes existing data (see app.demo.seed_demo_data). For the
wipe-and-reseed used by the public demo deployment, see app.demo.reset_demo.

Run from backend/: `python scripts/seed_demo_data.py`
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import Session  # noqa: E402

from app.db import engine, init_db  # noqa: E402
from app.demo import seed_demo_data  # noqa: E402


def seed() -> None:
    init_db()
    with Session(engine) as session:
        seed_demo_data(session)
    print("Seeded demo data: 4 courses, ~24 tasks, ~2 weeks of study sessions.")
    print("data_collection_started_at backdated 8 days - recommendations are eligible now.")


if __name__ == "__main__":
    seed()
