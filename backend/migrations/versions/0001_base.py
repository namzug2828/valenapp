"""Base: el esquema que ya existe en tu base de datos

Esta migración NO hace nada a propósito. Representa el punto de partida: las
tablas originales del diagrama más lo que ya aplicaste con migraciones.sql
(usuario_negocio.activo, servicios_de_cita.cantidad, email único en minúsculas
y las restricciones anti-solape de citas).

En tu base ya existente se marca como aplicada SIN ejecutarla:
    alembic stamp 0001

Para crear una base nueva desde cero (otro equipo, producción): restaura el
esquema con pg_dump/pg_restore (pg_dump --schema-only de tu base actual),
y después ejecuta `alembic stamp 0001` y `alembic upgrade head`.

Revision ID: 0001
Revises:
Create Date: 2026-11-01
"""
from alembic import op  # noqa: F401
import sqlalchemy as sa  # noqa: F401

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass