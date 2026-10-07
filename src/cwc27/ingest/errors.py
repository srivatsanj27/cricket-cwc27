"""Errors shared by the ingest modules."""


class ParseError(ValueError):
    """A Cricsheet file is malformed or outside the project's scope."""
