"""
Tạo user dev nếu chưa có (chạy sau khi đã apply document/sql/001_users.sql).

Usage:
  cd qcmaster-api && .venv/bin/python -m scripts.seed_dev_user
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.user import User
from app.security import hash_password


async def main() -> None:
    email = os.environ.get("SEED_EMAIL", "admin@qcmaster.dev")
    password = os.environ.get("SEED_PASSWORD", "admin12345")
    async with AsyncSessionLocal() as session:
        r = await session.execute(select(User).where(User.email == email))
        if r.scalar_one_or_none():
            print(f"User {email} already exists.")
            return
        user = User(
            email=email,
            password_hash=hash_password(password),
            full_name="Dev Admin",
            role="admin",
            is_active=True,
        )
        session.add(user)
        await session.commit()
        print(f"Created {email} / password from SEED_PASSWORD (default admin12345)")


if __name__ == "__main__":
    asyncio.run(main())
