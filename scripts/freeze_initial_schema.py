"""One-time v1 artifact creation before its release. Refuses to overwrite a revision."""

import json
from pathlib import Path

from sqlalchemy.dialects import sqlite
from sqlalchemy.schema import CreateIndex, CreateTable

from ufm.infrastructure.persistence.models.schema import metadata
from ufm.infrastructure.persistence.sqlite.guards import guard_statements


def main() -> None:
    target = Path("src/ufm/infrastructure/persistence/migrations/versions/0001_initial.json")
    dialect = sqlite.dialect()
    # SQLite permits forward foreign-key references, including the spool/evidence cycle.
    statements = [str(CreateTable(table).compile(dialect=dialect)) for table in metadata.tables.values()]
    statements += [
        str(CreateIndex(index).compile(dialect=dialect))
        for table in metadata.tables.values() for index in sorted(table.indexes, key=lambda x: str(x.name))
    ]
    statements += guard_statements()
    with target.open("x", encoding="utf-8", newline="\n") as output:
        json.dump(statements, output, indent=2, ensure_ascii=False)
        output.write("\n")
    print(f"Frozen {len(metadata.tables)} tables and {len(statements)} DDL statements")


if __name__ == "__main__":
    main()
