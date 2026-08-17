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
as it stands. `Citation` will be the opposite case when it arrives, carrying the
meeting title and speaker denormalised so the evidence panel renders without a
request per citation.

A shape owned by more than one resource moves to `common.py`.
"""
