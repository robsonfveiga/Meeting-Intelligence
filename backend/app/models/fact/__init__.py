"""Decisions, commitments and open threads pulled out of a meeting.

**Two models rather than one**, for the same reason `ParsedTurn` and `Turn` are
separate in the `transcript` package. The model that reads a transcript can supply
a statement and the turns it came from, but it cannot supply a meeting identifier,
a time range or a speaker list. A single model with those fields required would be
a lie about what the extractor produces; a single model with them optional would
push the question "is this hydrated yet?" into every caller.

So `ExtractedFact` is what comes back from the provider — a claim plus the turn
indices it rests on — and `Fact` is what is stored, after those indices have been
checked against the turns actually supplied and resolved into real speakers and
timestamps.

**The turn indices are the whole guardrail.** A fact that cannot point at a stretch
of transcript is not admissible, and one pointing outside the window it was
extracted from is discarded and counted. That check is mechanical, so it always
holds — the same discipline the `answer` package applies to citation markers, and
with the same limit: verified evidence is not verified meaning.

**Attribution never comes from the model.** Whatever an extractor claims about who
said something, the speakers and time on a stored `Fact` are read off the turns it
cites.

`FactKind` lives here because it is this vocabulary. `owner` and `due` mean
something only on a commitment and are cleared on the other kinds, so a decision
cannot arrive with a spurious assignee.
"""
