class ScreencastError(Exception):
    """Base class of all errors in this package."""


class ConfigError(ScreencastError):
    """A setting is missing or a value is invalid."""


class ToolError(ScreencastError):
    """A required system tool is missing or failed."""


class SlideError(ScreencastError):
    """The presentation cannot be read, or it holds no usable slide."""


class ScriptError(ScreencastError):
    """The narration could not be generated, read or written."""


class ModelError(ScreencastError):
    """A model server did not answer, or the answer was unusable."""


class VideoError(ScreencastError):
    """ffmpeg could not build the video."""
