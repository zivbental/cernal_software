"""Engine error hierarchy.

Every exception raised across the boundary derives from :class:`EngineError`. The
Platform catches it, records ``str(exc)`` as the run's user-facing ``error_summary``,
and logs the traceback separately — so error messages here must be safe to show a
researcher: no paths, no credentials, no internals (docs/architecture.md §6.2).
"""


class EngineError(Exception):
    """Base class for every engine failure."""


class InputValidationError(EngineError):
    """The input data is unusable — wrong schema, missing columns, unsupported organism."""


class ChecksumMismatchError(EngineError):
    """The input file does not match the checksum recorded at submission time."""


class UnsupportedGateFamilyError(EngineError):
    """A requested gate family is not registered in this engine build."""


class ScoringProfileError(EngineError):
    """The requested scoring profile is unknown, or its metric set is inconsistent."""


class JobCancelled(EngineError):
    """Raised internally when a progress callback reports that the run should stop.

    Not a failure: the client converts this into a ``cancelled`` JobResult.
    """
