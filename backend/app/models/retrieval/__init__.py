"""Query-time views of a chunk, from raw hit to something readable.

Three shapes for what is arguably one thing, and the progression is the point.
A `SearchHit` is what one strategy returned. A `FusedHit` is the same chunk after
two strategies have been combined, carrying the rank each of them gave it. A
`ScoredChunk` is that hit hydrated with enough content to be read or cited.

**Fusion uses rank, never score.** Scores from keyword search and vector search
are not comparable — different scales, different distributions, both moving as the
corpus grows. `score` survives on these models for display and debugging only,
and `FusedHit.ranks` keeps each strategy's position because that is what explains
a result: a chunk at rank 1 in keyword and 40 in vector tells a very different
story from one that placed third in both.

**`ScoredChunk` is denormalised on purpose.** It carries the meeting title and
speakers rather than just a `meeting_id`, so an evidence panel renders without a
request per hit. The cost is that adding a field means reshaping a response the
frontend already reads, which is a trade taken knowingly.

Nothing here is stored. The stored form is `Chunk` in the `transcript` package —
these are what a query makes of it.
"""
