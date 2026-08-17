# Sample transcripts for testing upload

Drop one of these files into the upload panel on the web interface, or post it directly:

```bash
curl -X POST http://localhost:8000/meetings -F "file=@samples/2026-04-08-support-escalation-review.vtt"
```

These are **not** part of the seed corpus in `data/transcripts/`. `make seed` does not
touch this folder, so the files here stay available as a fresh upload even on a
database that has already been seeded.

## `2026-04-08-support-escalation-review.vtt`

A four-person meeting reviewing the support queue in the week after launch. It is
WebVTT with Teams-style `<v Speaker Name>` voice tags, the same shape a real
*Download → .vtt* export produces.

The filename carries the date, so after ingestion the meeting should show a title of
"support escalation review" and a meeting date of 8 April 2026.

It continues the storyline of the seed corpus — the same four speakers, the migration
bugs from the retro, and the pricing increase that was deferred in March — so uploading
it on top of a seeded database gives cross-meeting questions something to find.

### Things worth checking after uploading

Decisions and actions that extraction should pick up:

- The reporting redesign slips one sprint; two engineers move onto the export timeout.
- The invoice history backfill runs Thursday, with a totals comparison before the
  billing screen switches over.
- The pricing increase stays deferred and goes to May planning as a decision item.
- Sofia Marquez closes eleven sign-in cases by Friday; Tom Beckett briefs the two
  customers waiting on the redesign.

Questions that should come back with citations:

- "Why was the reporting redesign delayed?"
- "What did we decide about the price increase?"
- "How many support tickets came in after launch?"
- "Who is fixing the export timeout?"

Questions that should come back refused rather than guessed, because the transcript
never says:

- "What is the revenue impact of the export bug?"
- "When will the reporting redesign ship?"
