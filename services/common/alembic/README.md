# Alembic Migrations

This directory houses auto-generated database migrations for shared KITTY models. Run

```bash
alembic -c services/common/alembic.ini revision --autogenerate -m "message"
alembic -c services/common/alembic.ini upgrade head
```

after configuring database credentials via environment variables.
