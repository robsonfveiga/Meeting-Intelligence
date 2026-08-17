"""Narrow ingest to WebVTT.

Scope changed: SubRip, JSON and plain-text parsers were removed in favour of
supporting one format completely. That is a breaking change for stored data even
though no column type changed — `source_format` still holds values the
application can no longer parse back into its enum, so reads fail.

Two fixes, in order:
  - `vtt` was renamed to `webvtt`, so rename the stored values.
  - Meetings ingested from a format we no longer support are deleted. Their
    turns and chunks go with them via ON DELETE CASCADE. Deleting is the honest
    option: the source files are gone, so the rows cannot be re-derived, and
    leaving them would mean a corpus containing meetings the system can no
    longer explain the provenance of.

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("UPDATE meetings SET source_format = 'webvtt' WHERE source_format = 'vtt'")
    op.execute("DELETE FROM meetings WHERE source_format <> 'webvtt'")


def downgrade() -> None:
    # The deleted rows are not recoverable; only the rename can be undone.
    op.execute("UPDATE meetings SET source_format = 'vtt' WHERE source_format = 'webvtt'")
