"""What the repository promises outside the Python code.

The compose file is the only place an operator sets a default, so a setting
that is not listed there cannot be set in Docker at all. The package data
glob and the workflow are checked for the same reason: nothing green in the
test suite would notice.
"""

from pathlib import Path

from pptx_screencast import config

ROOT = Path(__file__).resolve().parent.parent


def _read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def test_the_compose_file_lists_every_setting_of_the_page():
    compose = _read("docker-compose.yml")
    missing = [
        config.ENV_PREFIX + env_name
        for _, env_name, _ in config.PAGE_SETTINGS
        if config.ENV_PREFIX + env_name not in compose
    ]
    assert missing == []


def test_the_compose_file_lists_the_settings_of_the_video():
    compose = _read("docker-compose.yml")
    for name in ("FPS", "CRF", "BURN_IN", "MIN_CHARS", "MAX_CHARS", "WORK_DIR",
                 "BATCH_SIZE", "BATCH_MAX_WORKERS", "BATCH_TIMEOUT", "STT_TIMEOUT"):
        assert config.ENV_PREFIX + name in compose, name


def test_every_package_data_folder_exists():
    package = ROOT / "src" / "pptx_screencast"
    for line in _read("pyproject.toml").splitlines():
        if not line.startswith("pptx_screencast = ["):
            continue
        entries = line.split("[", 1)[1].rstrip("]").replace('"', "").split(",")
        for entry in (e.strip() for e in entries if e.strip()):
            assert list(package.glob(entry)), f"{entry} matches nothing"
        return
    raise AssertionError("pyproject names no package data")


def test_the_workflow_installs_the_speech_package_on_its_own():
    """pip cannot resolve the sibling from an index yet, so it has its own step."""
    workflow = _read(".github/workflows/ci.yml")
    assert "DOC2SPEECH_SOURCE" in workflow
    assert workflow.index("pip install \"${DOC2SPEECH_SOURCE") < workflow.index('pip install -e ".[test]"')


def test_the_image_installs_the_speech_package_on_its_own():
    dockerfile = _read("Dockerfile")
    assert "ARG DOC2SPEECH_SOURCE" in dockerfile
    assert "DOC2SPEECH_SOURCE" in _read("docker-compose.yml")


def test_the_readme_names_every_environment_variable():
    readme = _read("README.md")
    for _, env_name, _ in config.PAGE_SETTINGS:
        assert config.ENV_PREFIX + env_name in readme, env_name


def test_the_spelling_of_recognise_does_not_drift():
    """The code and the log messages are British, so the texts have to be too."""
    for name in ("README.md", "CHANGELOG.md", "PLAN.md"):
        text = _read(name).lower()
        assert "recognize" not in text, name
        assert "recognized" not in text, name
        assert "recogniser" in text or "recognis" in text or "recognition" in text, name


def test_the_readme_names_the_libass_requirement():
    readme = _read("README.md")
    assert "libass" in readme
