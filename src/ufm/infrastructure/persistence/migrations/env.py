"""Migration execution uses the caller's already-locked transaction only."""

from alembic import context
from sqlalchemy.engine import Connection

connection = context.config.attributes.get("connection")
if not isinstance(connection, Connection) or not connection.in_transaction():
    raise RuntimeError("migration.explicit_transaction_required")

context.configure(connection=connection, transactional_ddl=True)
with context.begin_transaction():
    context.run_migrations()
