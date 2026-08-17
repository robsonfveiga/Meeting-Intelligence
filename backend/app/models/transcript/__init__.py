"""What is in the corpus: a meeting, what was said in it, and how it was cut up.

Everything here is written during ingestion, and the folder reads in the order
the pipeline builds it. A `ParsedTurn` comes out of the parser before any
database row exists; a `Turn` is the same thing once it belongs to a `Meeting`;
a `Chunk` is a window of consecutive turns, and the unit that gets embedded and
retrieved.

**Two shapes for one idea, deliberately.** `ParsedTurn` and `Turn` differ only in
that a `Turn` has a `meeting_id`. They are separate because parsing happens
before the meeting row exists, and a required identifier the parser cannot supply
would be a lie about what the parser produces. The same argument separates
`ExtractedFact` from `Fact` in the `fact` package.

**`TimeRange` is the shared primitive**, used here and by every package that
needs to point back at a moment in a recording — retrieval, answers, facts.
Milliseconds rather than a timedelta, because that is what transcript formats
give us and what an interface needs back for seeking.

**A turn is never split.** Chunking groups turns and stops there. That single
constraint is what keeps speaker attribution intact all the way through to a
citation, and it is why the chunker is conversation-aware rather than a fixed-size
splitter.

`TranscriptFormat` lives here rather than in a folder of enums: it is part of this
vocabulary, and a reader opening this package should see the full set of formats
the system accepts without going looking.
"""
