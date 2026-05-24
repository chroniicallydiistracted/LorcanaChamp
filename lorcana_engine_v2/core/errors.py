class V2EngineError(Exception):
    """Base class for v2 engine errors."""

class IllegalCommandError(V2EngineError):
    """Raised when a command is not legal in the current state."""

class UnsupportedV2ShapeError(V2EngineError):
    """Raised when v2 intentionally does not support a source shape yet."""
