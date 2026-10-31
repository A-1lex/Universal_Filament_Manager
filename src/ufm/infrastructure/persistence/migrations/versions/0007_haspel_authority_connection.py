"""Store the selected Haspel authority endpoint and OS credential reference."""

import json
from pathlib import Path

from alembic import op

revision = "0007_haspel_authority_connection"
down_revision = "0006_printer_accounting_authority"
branch_labels = None
depends_on = None


def upgrade() -> None:
    statements = json.loads(Path(__file__).with_suffix(".json").read_text(encoding="utf-8"))
    connection = op.get_bind()
    for statement in statements:
        connection.exec_driver_sql(statement)


def downgrade() -> None:
    raise RuntimeError("migration.restore_verified_backup_required")
