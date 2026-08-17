"""A generated answer, the evidence under it, and how it was built.

**`AnswerTrace` is part of the response, not a debug extra.** Every answer ships
the query actually used, whether it was rewritten, how many hits were considered,
per-stage timings, tokens, and any citation markers that were dropped. Shipping it
always means an interface never has to ask a second time, and it means the
question "why did it say that?" is answerable from the payload the caller already
holds rather than from a log nobody has access to.

**`dropped_markers` is the field to read first.** It lists markers the model
emitted that pointed at excerpts we never supplied. Non-zero is a grounding
failure. It is surfaced rather than swallowed precisely because it is unflattering.

**An `AnswerCitation` cannot exist without its evidence.** Citations are built
from the markers that survived verification against the excerpts actually sent, so
one pointing at nothing is not possible by construction. What that does *not*
establish is that the cited excerpt supports the claim — a semantic judgement,
measured in the evaluation harness rather than asserted here.

`Answer.refused` is the deterministic case: retrieval found nothing usable, so no
model was called at all and the refusal cost nothing.
"""
