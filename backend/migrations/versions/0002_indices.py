"""Índices para consultar citas por negocio, empleado y cliente

El calendario pide citas por rango de fechas del negocio o de un empleado, y la
validación de solapes busca por cliente. Las claves foráneas de Postgres no
crean índices solas. Se usa IF NOT EXISTS para poder aplicarla aunque alguno ya
exista.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-01
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE INDEX IF NOT EXISTS ix_cita_negocio_fecha ON cita (negocio_id, fecha)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_cita_empleado_fecha ON cita (usuario_negocio_id, fecha)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_cita_cliente_fecha ON cita (cliente_id, fecha)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_cita_cliente_fecha")
    op.execute("DROP INDEX IF EXISTS ix_cita_empleado_fecha")
    op.execute("DROP INDEX IF EXISTS ix_cita_negocio_fecha")