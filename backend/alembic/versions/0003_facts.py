"""Extracted facts: decisions, commitments and open threads.

The table 0001 deliberately did not guess at. Now that the extraction pass
exists, its shape is constrained by something real: a statement, the turns it
was drawn from, and — for commitments only — an owner and a due date in the
words the transcript used.

One table with a `kind` discriminator rather than one per kind. The three are
structurally identical and are almost always read together, so separate tables
would buy nothing and make every cross-kind listing a union.

`kind` is a plain `String(16)` rather than a Postgres enum type. Adding a value
to a Postgres enum is a migration; the taxonomy here is the part most likely to
grow, and paying a schema change for it would be paying for the wrong thing.
Validation lives in `FactKind`, at the boundary where a bad value would be
written.

Revision ID: 0003
Revises: 0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "facts",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
        sa.Column(
            "meeting_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("meetings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("owner", sa.Text(), nullable=True),
        sa.Column("due_text", sa.Text(), nullable=True),
        sa.Column("start_turn_index", sa.Integer(), nullable=False),
        sa.Column("end_turn_index", sa.Integer(), nullable=False),
        sa.Column("start_ms", sa.Integer(), nullable=False),
        sa.Column("end_ms", sa.Integer(), nullable=False),
        sa.Column("speakers", sa.ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_index("ix_facts_meeting_id", "facts", ["meeting_id"])
    op.create_index("ix_facts_kind", "facts", ["kind"])


def downgrade() -> None:
    op.drop_index("ix_facts_kind", table_name="facts")
    op.drop_index("ix_facts_meeting_id", table_name="facts")
    op.drop_table("facts")
