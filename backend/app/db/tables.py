"""Table definitions, using SQLAlchemy Core rather than the ORM.

Core because we do explicit inserts and selects and map results to the pydantic
models in `app/models/` ourselves. The ORM's identity map and change tracking
would buy nothing here, and it would mean two layers of mapping instead of one.
"""

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ARRAY,
    Column,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from app.config import get_settings

metadata = MetaData()

_EMBEDDING_DIMENSIONS = get_settings().embedding_dimensions

meetings = Table(
    "meetings",
    metadata,
    Column("id", PGUUID(as_uuid=True), primary_key=True),
    Column("title", Text, nullable=False),
    Column("source_filename", Text, nullable=False),
    Column("source_format", String(16), nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=True),
    Column("duration_ms", Integer, nullable=True),
    Column("participants", ARRAY(Text), nullable=False, server_default="{}"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

turns = Table(
    "turns",
    metadata,
    Column("id", PGUUID(as_uuid=True), primary_key=True),
    Column(
        "meeting_id",
        PGUUID(as_uuid=True),
        ForeignKey("meetings.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("turn_index", Integer, nullable=False),
    Column("speaker", Text, nullable=False),
    Column("start_ms", Integer, nullable=False),
    Column("end_ms", Integer, nullable=False),
    Column("text", Text, nullable=False),
    UniqueConstraint("meeting_id", "turn_index", name="uq_turns_meeting_index"),
    Index("ix_turns_meeting_id", "meeting_id"),
)

# One table with a `kind` column rather than three tables. A decision, a
# commitment and an open thread are the same thing structurally — a statement
# with a stretch of transcript behind it — and they are almost always read
# together. Three tables would triple the read and write code and turn every
# cross-kind listing into a union.
facts = Table(
    "facts",
    metadata,
    Column("id", PGUUID(as_uuid=True), primary_key=True),
    Column(
        "meeting_id",
        PGUUID(as_uuid=True),
        ForeignKey("meetings.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("kind", String(16), nullable=False),
    Column("statement", Text, nullable=False),
    # Only ever set on commitments. Free text, because "before the retro" is what
    # was said and a parsed date would be a precision the transcript lacks.
    Column("owner", Text, nullable=True),
    Column("due_text", Text, nullable=True),
    # The evidence. Not nullable: a fact that cannot point at turns is not stored.
    Column("start_turn_index", Integer, nullable=False),
    Column("end_turn_index", Integer, nullable=False),
    Column("start_ms", Integer, nullable=False),
    Column("end_ms", Integer, nullable=False),
    Column("speakers", ARRAY(Text), nullable=False, server_default="{}"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Index("ix_facts_meeting_id", "meeting_id"),
    Index("ix_facts_kind", "kind"),
)

chunks = Table(
    "chunks",
    metadata,
    Column("id", PGUUID(as_uuid=True), primary_key=True),
    Column(
        "meeting_id",
        PGUUID(as_uuid=True),
        ForeignKey("meetings.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("chunk_index", Integer, nullable=False),
    Column("start_turn_index", Integer, nullable=False),
    Column("end_turn_index", Integer, nullable=False),
    Column("start_ms", Integer, nullable=False),
    Column("end_ms", Integer, nullable=False),
    Column("speakers", ARRAY(Text), nullable=False, server_default="{}"),
    Column("text", Text, nullable=False),
    Column("context_header", Text, nullable=True),
    # Nullable: a chunk exists before it is embedded, and that gap is exactly
    # what makes a failed ingest resumable.
    Column("embedding", Vector(_EMBEDDING_DIMENSIONS), nullable=True),
    # Maintained by Postgres. Hybrid retrieval needs keyword search alongside
    # vectors; meetings are full of proper nouns that embeddings blur together.
    Column(
        "text_search",
        TSVECTOR,
        Computed("to_tsvector('english', text)", persisted=True),
    ),
    UniqueConstraint("meeting_id", "chunk_index", name="uq_chunks_meeting_index"),
    Index("ix_chunks_meeting_id", "meeting_id"),
    Index("ix_chunks_text_search", "text_search", postgresql_using="gin"),
)
