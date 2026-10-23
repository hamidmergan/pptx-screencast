"""The system tools are checked before the first long step."""

import pptx_screencast.tools as tools
from pptx_screencast.errors import ToolError
import pytest


def test_missing_tools_names_libreoffice(monkeypatch):
    monkeypatch.setattr(tools.shutil, "which", lambda name: None)
    missing = tools.missing_tools()
    assert "libreoffice" in missing
    assert "ffmpeg" in missing
    assert "pdftoppm" in missing


def test_video_only_check_ignores_the_renderer(monkeypatch):
    monkeypatch.setattr(tools.shutil, "which", lambda name: None)
    assert tools.missing_tools(render=False) == ["ffmpeg", "ffprobe"]


def test_everything_present_means_no_complaint(monkeypatch):
    monkeypatch.setattr(tools.shutil, "which", lambda name: "/usr/bin/" + name)
    assert tools.missing_tools() == []
    tools.require_tools()


def test_the_error_says_where_to_get_the_program(monkeypatch):
    monkeypatch.setattr(tools.shutil, "which", lambda name: None)
    with pytest.raises(ToolError) as info:
        tools.require_tools(render=False)
    assert "apt install ffmpeg" in str(info.value)


def test_soffice_counts_as_libreoffice(monkeypatch):
    monkeypatch.setattr(tools.shutil, "which", lambda name: "/usr/bin/soffice" if name == "soffice" else None)
    assert "libreoffice" not in tools.missing_tools()
