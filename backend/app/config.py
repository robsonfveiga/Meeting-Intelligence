"""Settings, loaded from the environment.

Lives at the application root deliberately: everything imports it, including
logging and the client modules, so it sits below the rest of the dependency order.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "meeting-intelligence"
    environment: Literal["local", "test", "production"] = "local"
    log_level: str = "INFO"
    json_logs: bool = True

    # Stored in the plain libpq form because the LangGraph checkpointer wants it
    # that way. SQLAlchemy needs the driver named, hence the property below.
    database_url: str = "postgresql://postgres:postgres@localhost:5433/meetings"

    upload_dir: Path = Path("/data/uploads")
    max_upload_bytes: int = 10 * 1024 * 1024

    # Unused until slice 1. Absent key must not stop the service booting.
    openai_api_key: str | None = None
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    embedding_batch_size: int = 96

    # Characters, not tokens: the target sits far below the model's 8191-token
    # limit, so exact counting would add a dependency without changing anything.
    #
    # Lowered from 1200 after measuring. At 1200 a chunk covered most of a
    # meeting section, and its embedding was diluted enough that "how long did
    # the rollback take" returned the meeting's *opening* rather than the
    # sentence answering it (0.394). At 350 the same query returned the exact
    # line at 0.573. Four hand-written queries cannot separate 350 from 500, so
    # this sits in the clearly-better region; slice 2 tunes it against a real
    # golden set, and adds neighbour expansion so precision does not cost
    # context.
    chunk_target_chars: int = 500
    chunk_max_chars: int = 1000
    chunk_overlap_turns: int = 1

    # Fusion weights. Vector is the baseline; keyword is discounted because an
    # OR-joined query always returns candidates, so it is noisier per hit than
    # dense retrieval. Swept over the golden set: 0 (vector only) scores clearly
    # worse than any non-zero weight, which is the robust finding. The gap
    # between 0.5 and 1.0 is one or two questions out of fifteen — inside the
    # noise floor of a set this size, so 0.75 is a reasonable point rather than
    # a tuned optimum.
    retrieval_keyword_weight: float = 0.75
    retrieval_vector_weight: float = 1.0
    retrieval_candidate_multiplier: int = 4

    # Two tiers. Grading and query rewriting are high-frequency and low-stakes,
    # so they use the cheaper model; only the final synthesis uses the stronger
    # one. Model names are configuration rather than constants because the
    # provider's catalogue moves faster than this codebase will.
    llm_model: str = "gpt-5.5"
    llm_utility_model: str = "gpt-5.4-mini"
    # Unset by default: newer model families reject `temperature`, so it is only
    # sent when explicitly configured.
    llm_temperature: float | None = None
    llm_max_answer_tokens: int | None = None

    # Left at zero deliberately. Published prices change and differ per model; a
    # hardcoded rate reports a confident wrong cost. Token counts are always
    # accurate because they come from the API.
    llm_input_usd_per_mtok: float = 0.0
    llm_output_usd_per_mtok: float = 0.0

    # Extraction. A switch rather than a hardcoded on, because this is the first
    # ingest node that makes a completion call per window over the whole
    # transcript — ingesting a long back catalogue with it off, then turning it
    # on, is a reasonable thing to want.
    extraction_enabled: bool = True
    # Far larger than a retrieval chunk. A decision made in one turn and
    # qualified ten turns later has to arrive in the same call, so precision is
    # the wrong objective here — coverage is.
    extraction_window_chars: int = 6000
    # Falls back to the utility model. Extraction is mechanical and high volume,
    # the same argument that put grading on the cheaper tier, but it reads more
    # text per call than grading does, so it gets its own knob.
    extraction_model: str | None = None
    # A cap on what one window can produce. A transcript that yields fifty
    # "decisions" has not been read well, and storing them would make the
    # decision list useless rather than thorough. Truncation is logged.
    extraction_max_facts_per_window: int = 25

    # Corrective retrieval: one rewrite-and-retry when grading says the excerpts
    # are insufficient. Bounded, because an unbounded loop on a hard question is
    # a way to spend money slowly.
    max_retrieval_attempts: int = 2
    answer_excerpt_count: int = 6

    langsmith_tracing: bool = False
    langsmith_project: str = "meeting-intelligence"
    langsmith_api_key: str | None = None

    @property
    def sqlalchemy_url(self) -> str:
        return self.database_url.replace("postgresql://", "postgresql+psycopg://", 1)


@lru_cache
def get_settings() -> Settings:
    return Settings()
