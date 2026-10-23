from .core import build_scripts, make_video, write_script
from .glossary import parse_glossary, read_glossary
from .errors import (
    ConfigError,
    ModelError,
    ScreencastError,
    ScriptError,
    SlideError,
    ToolError,
    VideoError,
)
from .script_file import parse_script_file, read_script_file, write_script_file
from .selection import parse_slides
from .slides import extract_notes_per_slide, extract_text_per_slide, pptx_to_images
from .tools import missing_tools, require_tools

__version__ = "0.1.0"

__all__ = [
    "make_video",
    "write_script",
    "build_scripts",
    "extract_text_per_slide",
    "extract_notes_per_slide",
    "pptx_to_images",
    "parse_script_file",
    "read_script_file",
    "write_script_file",
    "parse_slides",
    "parse_glossary",
    "read_glossary",
    "missing_tools",
    "require_tools",
    "ScreencastError",
    "ConfigError",
    "ToolError",
    "SlideError",
    "ScriptError",
    "ModelError",
    "VideoError",
    "__version__",
]
