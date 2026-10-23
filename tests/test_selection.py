"""The selection must never shift the slide numbers."""

import pytest

from pptx_screencast.errors import ConfigError
from pptx_screencast.selection import (
    audio_slots,
    clip_pairs,
    parse_slides,
    slide_selection,
)


def test_without_a_choice_every_slide_is_included():
    a = slide_selection(4, None, None)
    assert a.clip_slides == [0, 1, 2, 3]
    assert a.excluded == set()
    assert a.old_audio_allowed == {0, 1, 2, 3}


def test_the_rest_is_excluded():
    a = slide_selection(4, [0, 3], [])
    assert a.clip_slides == [0, 3]
    assert a.excluded == {1, 2}


def test_the_clip_slides_are_in_order():
    assert slide_selection(4, [3, 0, 2], []).clip_slides == [0, 2, 3]


def test_a_slide_spoken_again_may_not_reuse_its_old_audio():
    a = slide_selection(4, None, [1])
    assert a.old_audio_allowed == {0, 2, 3}


def test_speaking_again_outside_the_choice_changes_nothing():
    a = slide_selection(4, [0, 1], [3])
    assert a.old_audio_allowed == {0, 1}
    assert a.excluded == {2, 3}


def test_numbers_outside_the_range_are_dropped():
    a = slide_selection(3, [0, 7, -1], [9])
    assert a.clip_slides == [0]
    assert a.excluded == {1, 2}


def test_a_repeated_number_counts_once():
    assert slide_selection(3, [1, 1, 1], []).clip_slides == [1]


def test_an_empty_choice_yields_no_clips():
    a = slide_selection(3, [], [])
    assert a.clip_slides == []
    assert a.excluded == {0, 1, 2}


def test_no_slides_at_all():
    a = slide_selection(0, None, None)
    assert a.clip_slides == []
    assert a.excluded == set()


def test_the_build_position_carries_the_right_slide_number():
    """With slide 2 excluded, clip 1 has to belong to slide 3, not to slide 2."""
    assert clip_pairs([0, 2, 3], 4) == [(0, 0), (1, 2), (2, 3)]


def test_more_slides_than_images_are_cut_off():
    assert clip_pairs([0, 1, 2, 3], 2) == [(0, 0), (1, 1)]


def test_an_excluded_slide_gets_no_slot_for_new_audio():
    """False means the old audio of this slide stays."""
    assert audio_slots(4, [0, 2, 3]) == [True, False, True, True]


def test_without_a_choice_no_slide_gets_new_audio():
    assert audio_slots(3, []) == [False, False, False]


# -- Slide numbers people type --


def test_a_single_number_counts_from_one():
    assert parse_slides("1") == [0]


def test_a_range_includes_both_ends():
    assert parse_slides("1-5") == [0, 1, 2, 3, 4]


def test_ranges_and_numbers_can_be_mixed():
    assert parse_slides("1-3,8") == [0, 1, 2, 7]


def test_spaces_and_repeats_do_not_matter():
    assert parse_slides(" 2, 2 , 1 ") == [0, 1]


def test_an_empty_choice_is_empty():
    assert parse_slides("") == []


@pytest.mark.parametrize("text", ["abc", "0", "5-1", "1-", "-3"])
def test_nonsense_is_refused(text):
    with pytest.raises(ConfigError):
        parse_slides(text)
