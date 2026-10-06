"""File storage on local disk.

Uploaded PDFs live in `<storage_dir>/pdfs` (private). Cropped figures live in
`<storage_dir>/public` and are served at `/files/...`. Swap these helpers for an
S3/GCS implementation when running more than one API host.
"""

import hashlib
from pathlib import Path

from app.config import get_settings


def root() -> Path:
    path = Path(get_settings().storage_dir).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def public_dir() -> Path:
    path = root() / "public"
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_pdf(data: bytes) -> tuple[str, str]:
    digest = hashlib.sha256(data).hexdigest()
    path = root() / "pdfs" / f"{digest}.pdf"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(data)
    return str(path), digest
