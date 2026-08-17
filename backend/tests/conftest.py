"""Shared test setup.

Deliberately tiny. Anything needing a database lives in
`tests/integration/conftest.py`, so unit tests keep running with no
infrastructure at all — which is the property that makes them fast enough to
iterate on, and the reason the chunker and ranker are testable exhaustively.
"""

import os

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("JSON_LOGS", "false")
