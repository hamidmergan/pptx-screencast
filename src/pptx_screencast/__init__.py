from .config import Settings, env_defaults, resolve
from .core import build_scripts, make_video, write_script
from .glossary import parse_glossary, read_glossary
from .material import clean_material, prepare_materials
from .review import find_unchanged_slides
from .errors import (
    ConfigError,
    ModelError,
    ScreencastError,
    ScriptError,
    SlideError,
    ToolError,
    VideoError,
)
from .naming import build_artifact_stem
from .script_file import (
    numbered_headings,
    parse_script_file,
    read_script_file,
    write_script_file,
)
from .selection import parse_slides
from .slides import extract_notes_per_slide, extract_text_per_slide, pptx_to_images
from .subtitle_converter import vtt_to_cues, vtt_to_srt
from .subtitles import build_subtitle_srt, build_subtitle_vtt
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
    "numbered_headings",
    "build_artifact_stem",
    "build_subtitle_vtt",
    "build_subtitle_srt",
    "vtt_to_cues",
    "vtt_to_srt",
    "Settings",
    "resolve",
    "env_defaults",
    "parse_slides",
    "parse_glossary",
    "read_glossary",
    "clean_material",
    "prepare_materials",
    "find_unchanged_slides",
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
