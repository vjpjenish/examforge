import os
import tempfile
from pathlib import Path

_tmp = tempfile.mkdtemp(prefix="examforge-test-")
# Set TEST_DATABASE_URL to run against Postgres (the database is wiped).
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", f"sqlite:///{_tmp}/test.db")
os.environ["STORAGE_DIR"] = f"{_tmp}/storage"
os.environ["EXTRACTION_PROVIDER"] = "heuristic"
os.environ["ADMIN_EMAIL"] = "admin@test.dev"
os.environ["ADMIN_PASSWORD"] = "admin-password"
os.environ["JWT_SECRET"] = "test-secret-that-is-at-least-32-bytes-long"

import pymupdf  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

SAMPLE_PAGES = [
    """JEE MAIN MOCK TEST - 1
Duration: 60 minutes. Each correct answer +4, each wrong answer -1.
PHYSICS
1. A body of mass 2 kg moves with velocity 3 m/s. Its kinetic energy is
(A) 6 J
(B) 9 J
(C) 12 J
(D) 18 J
2. The SI unit of electric charge is
(A) Ampere
(B) Coulomb
(C) Volt
(D) Ohm
""",
    """CHEMISTRY
3. Which of the following is a noble gas?
(A) Nitrogen (B) Oxygen (C) Argon (D) Hydrogen
4. The number of moles in 36 g of water is
""",
    """ANSWER KEY
1. (B) 2. (B) 3. (C) 4. 2
""",
]


def make_pdf(path: Path, pages: list[str] = SAMPLE_PAGES) -> Path:
    doc = pymupdf.open()
    for text in pages:
        page = doc.new_page()
        page.insert_text((50, 60), text, fontsize=11)
    doc.save(path)
    return path


@pytest.fixture(scope="session")
def client():
    from app.db import Base, engine
    from app.main import app

    Base.metadata.drop_all(engine)

    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def admin_headers(client):
    r = client.post("/api/auth/login", json={"email": "admin@test.dev", "password": "admin-password"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="session")
def sample_pdf(tmp_path_factory):
    return make_pdf(tmp_path_factory.mktemp("pdf") / "sample.pdf")
