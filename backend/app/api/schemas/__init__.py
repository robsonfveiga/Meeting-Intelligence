"""Wire shapes, one module per resource.

Import from the specific module — `from app.api.schemas.jobs import JobResponse`
— rather than re-exporting here. A re-export list has to be maintained, hides
where a type actually lives, and invites import cycles once two schema modules
reference each other.

**A schema is only defined when the wire shape genuinely differs from the domain
model.** Otherwise the route returns the model from `app/models/` directly.
Without that rule this package slowly becomes a shadow copy of the domain, where
every field change means editing two files for no benefit.

That is why there is no `meetings.py`: the meetings endpoint returns `Meeting`
as it stands, and `/chat` returns `Answer` — the domain model already carries the
citations and the trace an interface needs.

`facts.py` is the opposite case, and shows where the rule bites. A `Fact` knows
its `meeting_id` but not the meeting's title, and the useful view of facts is
cross-meeting, so a list of statements without their meeting would be unreadable.
`FactResponse` exists to denormalise that one field.

A shape owned by more than one resource moves to `common.py`.
"""
