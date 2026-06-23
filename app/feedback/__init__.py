"""DB-backed feedback channel (P5, §2.4).

A submission writes a :class:`~app.db.models.Feedback` row (source of truth,
admin-visible) and then forwards one Resend notification to the operator. This
replaces the old mailto black hole and the phantom "feedback button" the
privacy/terms pages used to reference.
"""
