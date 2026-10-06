import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from app import storage
from app.api import auth, dashboard, documents, mistakes, pyq, tests
from app.config import get_settings
from app.db import Base, SessionLocal, add_missing_columns, engine
from app.models import Role, User
from app.security import hash_password

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def bootstrap() -> None:
    Base.metadata.create_all(engine)
    if added := add_missing_columns():
        logging.getLogger(__name__).info("Added database columns: %s", ", ".join(added))
    settings = get_settings()
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.role == Role.admin)) is None:
            db.add(
                User(
                    email=settings.admin_email.lower(),
                    name="Admin",
                    password_hash=hash_password(settings.admin_password),
                    role=Role.admin,
                )
            )
            db.commit()


@asynccontextmanager
async def lifespan(_: FastAPI):
    bootstrap()
    stop = None
    if get_settings().embedded_worker:
        from app.worker import start_embedded

        stop = start_embedded()
    yield
    if stop:
        stop.set()


app = FastAPI(title="ExamForge API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
for module in (auth, documents, tests, pyq, dashboard, mistakes):
    app.include_router(module.router)
app.mount("/files", StaticFiles(directory=storage.public_dir()), name="files")


@app.get("/api/health")
def health():
    return {"ok": True}
