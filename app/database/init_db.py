"""Crea el esquema, aplica las columnas nuevas y carga los datos base.

Uso: ``python -m app.database.init_db [--demo] [--reset]``
"""

from __future__ import annotations

import argparse

from sqlalchemy import text

from app.database.models import Base
from app.database.seeds.base import seed_base
from app.database.session import get_engine

# Cambios sobre tablas que ya existían. create_all() sólo crea tablas nuevas (con sus índices y
# restricciones), así que estas sentencias idempotentes (PostgreSQL) actualizan una BD existente
# sin perder datos. No hay Alembic: cambios de tipo o renombres requieren `make reset-db`.
SCHEMA_UPGRADES = [
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified BOOLEAN NOT NULL DEFAULT TRUE",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS deletion_requested_at TIMESTAMPTZ",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS deletion_scheduled_for TIMESTAMPTZ",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_updated_at TIMESTAMPTZ",
    "UPDATE users SET avatar_updated_at = now() "
    "WHERE avatar IS NOT NULL AND avatar_updated_at IS NULL",
    "ALTER TABLE verification_codes ADD COLUMN IF NOT EXISTS payload VARCHAR(255) "
    "NOT NULL DEFAULT ''",
    # Borrar al creador de un reto ya no borra el reto (antes ON DELETE CASCADE).
    """DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = 'challenges_creator_id_fkey' AND confdeltype <> 'n') THEN
            ALTER TABLE challenges DROP CONSTRAINT challenges_creator_id_fkey;
        END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'challenges_creator_id_fkey')
        THEN
            ALTER TABLE challenges ADD CONSTRAINT challenges_creator_id_fkey
                FOREIGN KEY (creator_id) REFERENCES users (id) ON DELETE SET NULL;
        END IF;
    END $$""",
]

# Restricciones CHECK agregadas después de crear las tablas: (tabla, nombre, condición).
CHECK_UPGRADES = [
    ("grade_items", "ck_item_grade", "grade >= 0"),
    ("support_messages", "ck_no_self_message", "sender_id <> recipient_id"),
    ("user_reports", "ck_no_self_report", "reporter_id <> reported_id"),
    ("user_reports", "ck_report_single_target", "post_id IS NULL OR comment_id IS NULL"),
]


def _add_check(table: str, name: str, condition: str) -> str:
    return f"""DO $$ BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = '{name}') THEN
            ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({condition});
        END IF;
    END $$"""


def create_schema(reset: bool = False) -> None:
    engine = get_engine()
    if reset:
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            for statement in SCHEMA_UPGRADES:
                conn.execute(text(statement))
            for check in CHECK_UPGRADES:
                conn.execute(text(_add_check(*check)))
        # Índices declarados en los modelos después de crear la tabla (create_all no los agrega
        # a tablas existentes).
        for table in Base.metadata.sorted_tables:
            for index in table.indexes:
                index.create(conn, checkfirst=True)


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
