"""Replace the default admin credentials in the production (Neon) database.

The bootstrap admin is only created when no admin exists. An earlier test run had
already created admin@example.com / admin12345 -- the README's public defaults --
so the strong ADMIN_PASSWORD set on Render was never applied. This updates that
row in place, keeping the user id (and anything already owned by it) intact.

Run:  backend/.venv/bin/python fix-admin-credentials.py
"""
import pathlib, re, sys

sys.path.insert(0, "backend")
from sqlalchemy import create_engine, text
from app.config import Settings
from app.security import hash_password, verify_password

env = dict(
    re.match(r'([A-Z_]+)="?(.*?)"?$', line).groups()
    for line in pathlib.Path(".deploy.env").read_text().splitlines()
    if line.strip() and not line.startswith("#")
)
NEW_EMAIL = "vaghasiyajenish34@gmail.com"
NEW_PASSWORD = env["ADMIN_PASSWORD"]          # the generated one, also set on Render

engine = create_engine(Settings(_env_file=None, database_url=env["DATABASE_URL"]).database_url)
with engine.begin() as conn:
    print("users before:", conn.execute(text("select id, email, role from users order by id")).fetchall())
    updated = conn.execute(
        text("update users set email=:e, password_hash=:p where email='admin@example.com'"),
        {"e": NEW_EMAIL, "p": hash_password(NEW_PASSWORD)},
    ).rowcount
    print(f"rows updated: {updated}")
    print("users after :", conn.execute(text("select id, email, role from users order by id")).fetchall())
    stored = conn.execute(text("select password_hash from users where email=:e"), {"e": NEW_EMAIL}).scalar()

print("new password verifies :", verify_password(NEW_PASSWORD, stored))
print("old default accepted  :", verify_password("admin12345", stored), "(must be False)")
