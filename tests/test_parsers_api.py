import pytest

from flamegraph_textual.exceptions import ProfileParseException
from flamegraph_textual.parsers import choose_parser, parse
from flamegraph_textual.parsers.pprof_parser import ProfileParser
from flamegraph_textual.parsers.stackcollapse_parser import StackCollapseParser


def test_choose_parser_uses_profile_type_when_provided(simple_collapse_data):
    parser_cls = choose_parser(simple_collapse_data, profile_type="stackcollapse")
    assert parser_cls is StackCollapseParser


def test_parse_uses_profile_type_when_provided(simple_collapse_data):
    profile = parse(
        simple_collapse_data,
        "a.txt",
        profile_type="stackcollapse",
    )
    assert profile.sample_types[0].sample_type == "samples"
    assert profile.sample_types[0].sample_unit == "count"


def test_choose_parser_supports_austin_profile_type(simple_collapse_data):
    parser_cls = choose_parser(simple_collapse_data, profile_type="austin")
    assert parser_cls is StackCollapseParser


def test_parse_uses_austin_profile_type(simple_collapse_data):
    profile = parse(
        simple_collapse_data,
        "austin.txt",
        profile_type="austin",
    )
    assert profile.sample_types[0].sample_type == "samples"
    assert profile.sample_types[0].sample_unit == "count"


def test_parse_guesses_type_when_profile_type_omitted(profile10s):
    profile = parse(profile10s, "profile.out")
    assert profile.sample_types[0].sample_type == "samples"
    assert profile.sample_types[1].sample_type == "cpu"


def test_choose_parser_accepts_profile_type_with_mixed_case(profile10s):
    parser_cls = choose_parser(profile10s, profile_type="PpRoF")
    assert parser_cls is ProfileParser


def test_choose_parser_rejects_unknown_profile_type(profile10s):
    with pytest.raises(ProfileParseException, match="Unsupported profile_type"):
        choose_parser(profile10s, profile_type="unknown")
