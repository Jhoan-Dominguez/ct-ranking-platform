"""Crea el esquema, aplica las columnas nuevas y carga los datos base.

Uso: ``python -m app.database.init_db [--demo] [--reset]``
"""

from __future__ import annotations

import argparse

from sqlalchemy import text

from app.database.models import Base
from app.database.seeds.base import seed_base
from app.database.session import get_engine

# Columnas agregadas a tablas que ya existían. create_all() sólo crea tablas nuevas, así que
# estas sentencias idempotentes (PostgreSQL) actualizan una BD existente sin perder datos.
COLUMN_UPGRADES = [
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified BOOLEAN NOT NULL DEFAULT TRUE",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS deletion_requested_at TIMESTAMPTZ",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS deletion_scheduled_for TIMESTAMPTZ",
]


def create_schema(reset: bool = False) -> None:
    engine = get_engine()
    if reset:
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    if engine.dialect.name == "postgresql":
        with engine.begin() as conn:
            for statement in COLUMN_UPGRADES:
                conn.execute(text(statement))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reset", action="store_true", help="Elimina y recrea todas las tablas")
    parser.add_argument("--demo", action="store_true", help="Carga usuarios y datos de ejemplo")
    args = parser.parse_args()

    create_schema(reset=args.reset)
    seed_base()
    print("Esquema y datos base listos.")
    if args.demo:
        from app.database.seeds.demo import load_demo

        load_demo()


if __name__ == "__main__":
    main()
