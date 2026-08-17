"""The state a running ingestion job carries, and what it measures.

Two rules govern everything in this package.

**Identifiers, never payloads.** Nodes write their real output to Postgres and put
identifiers in the state. No transcript text, no chunk bodies, and above all no
embedding vectors. The state is checkpointed to the database after every node, so
a payload-carrying state means writing thousands of floats into a checkpoint blob
on every step, and a "resume" that redoes work already saved. Keeping the state
small is what makes resume genuinely resume.

**Every field declares replace or accumulate.** LangGraph replaces by default, so
a field gathering contributions from several nodes needs an explicit reducer.
Getting this wrong on `stats` is silent: you keep only the last node's numbers and
do not notice until you go looking for the cost breakdown. `chunk_ids` and `errors`
accumulate; `fact_ids` deliberately does not, because extraction clears a meeting's
facts before writing and an appending field would disagree with the database it
describes.

**There is no jobs table.** The checkpointer is the job store — the thread
identifier *is* the job identifier, and the status endpoint reads graph state — so
this package is the whole of the job model. `StageStats` per node is what the cost
and latency story is assembled from, and `StageError` carries a `recoverable` flag
because a missing API key and an unparseable file are different outcomes.

`Stage` lives here because it is this vocabulary: the ordered set of places a job
can have reached, with FAILED terminal and reachable from anywhere.
"""
