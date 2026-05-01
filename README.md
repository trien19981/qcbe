# QCMaster API (FastAPI + PostgreSQL)

## Yêu cầu

- Python 3.11+ (khi chạy API trên máy, không qua Docker)
- Docker (tùy chọn: chỉ để chạy **API + Redis**; **Postgres dùng remote**)

## Chạy API bằng Docker (Redis trong Docker + DB remote)

1. Tạo `.env` từ `.env.example` và đặt **`DATABASE_URL`** trỏ tới Postgres **remote** (`postgresql+asyncpg://...`).

2. Chạy stack:

```bash
cd qcmaster-api
docker compose up --build -d
```

- API: **http://127.0.0.1:8002** (Swagger: `/docs`)
- Redis: `localhost:6379` (container; compose gán `REDIS_URL=redis://redis:6379/0` cho service `api`)

Trên **DB remote**, chạy một lần `document/sql/001_users.sql` (psql, DBeaver, v.v.).

Tạo user dev (trong container API):

```bash
docker compose exec api python scripts/seed_dev_user.py
```

Dừng: `docker compose down` (volume Redis giữ dữ liệu rate-limit / session tùy cấu hình).

---

## Chạy API trên máy (không Docker)

```bash
cd qcmaster-api
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
# chỉnh DATABASE_URL, REDIS_URL (vd: redis://localhost:6379/0)
.venv/bin/uvicorn app.main:app --reload --port 8002
```

Mở: `http://localhost:8002/docs`, health: `/api/health`, DB: `/api/health/db`.

## Cấu hình environment

Xem `.env.example`: `DATABASE_URL`, `SECRET_KEY`, Redis, JWT, CORS.
