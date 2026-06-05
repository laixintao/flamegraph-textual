import json

import pytest

from flamegraph_textual.parsers import choose_parser, parse
from flamegraph_textual.parsers.speedscope_parser import SpeedscopeParser

from ..utils import frame2json


def _make_doc(**kwargs):
    doc = {
        "$schema": "https://www.speedscope.app/file-format-schema.json",
        "shared": {
            "frames": [
                {"name": "main", "file": "app.py", "line": 1},
                {"name": "foo", "file": "app.py", "line": 10},
                {"name": "bar", "file": "app.py", "line": 20},
                {"name": "baz", "file": "app.py", "line": 30},
            ]
        },
        "profiles": [],
    }
    doc.update(kwargs)
    return json.dumps(doc).encode()


def _sampled_profile(**kwargs):
    p = {
        "type": "sampled",
        "name": "test",
        "unit": "microseconds",
        "startValue": 0,
        "endValue": 5000,
        "samples": [[0, 1, 2], [0, 1, 3], [0, 1, 2]],
        "weights": [1000, 500, 1000],
    }
    p.update(kwargs)
    return p


def _evented_profile(**kwargs):
    p = {
        "type": "evented",
        "name": "test",
        "unit": "microseconds",
        "startValue": 0,
        "endValue": 5000,
        "events": [
            {"type": "O", "at": 0, "frame": 0},
            {"type": "O", "at": 10, "frame": 1},
            {"type": "O", "at": 20, "frame": 2},
            {"type": "C", "at": 30, "frame": 2},
            {"type": "C", "at": 40, "frame": 1},
            {"type": "C", "at": 50, "frame": 0},
        ],
    }
    p.update(kwargs)
    return p


# ── validate ──────────────────────────────────────────────────────────────────


def test_validate_detects_schema_url():
    data = _make_doc(profiles=[_sampled_profile()])
    assert SpeedscopeParser.validate(data)


def test_validate_detects_structure_without_schema():
    doc = {
        "shared": {"frames": [{"name": "main"}]},
        "profiles": [_sampled_profile()],
    }
    assert SpeedscopeParser.validate(json.dumps(doc).encode())


def test_validate_rejects_non_json():
    assert not SpeedscopeParser.validate(b"a;b;c 10\n")


def test_validate_rejects_unrelated_json():
    assert not SpeedscopeParser.validate(json.dumps({"foo": "bar"}).encode())


def test_validate_rejects_binary():
    assert not SpeedscopeParser.validate(b"\x00\x01\x02\x03")


# ── sampled profile ───────────────────────────────────────────────────────────


def test_parse_sampled_profile():
    data = _make_doc(profiles=[_sampled_profile()])
    parser = SpeedscopeParser("test.json")
    profile = parser.parse(data)

    # samples: [main→foo→bar]*2 weight 1000 each, [main→foo→baz] weight 500
    assert frame2json(profile.root_stack) == {
        "root": {
            "values": [2500],
            "children": [
                {
                    "main": {
                        "values": [2500],
                        "children": [
                            {
                                "foo": {
                                    "values": [2500],
                                    "children": [
                                        {"bar": {"values": [2000], "children": []}},
                                        {"baz": {"values": [500], "children": []}},
                                    ],
                                }
                            }
                        ],
                    }
                }
            ],
        }
    }


def test_parse_sampled_profile_highest_lines():
    data = _make_doc(profiles=[_sampled_profile()])
    profile = SpeedscopeParser("test.json").parse(data)
    assert profile.highest_lines == 3


def test_parse_sampled_sample_types():
    data = _make_doc(profiles=[_sampled_profile(unit="microseconds")])
    profile = SpeedscopeParser("test.json").parse(data)
    assert profile.sample_types[0].sample_type == "time"
    assert profile.sample_types[0].sample_unit == "microseconds"


def test_parse_sampled_unit_bytes():
    data = _make_doc(profiles=[_sampled_profile(unit="bytes")])
    profile = SpeedscopeParser("test.json").parse(data)
    assert profile.sample_types[0].sample_type == "memory"
    assert profile.sample_types[0].sample_unit == "bytes"


def test_parse_sampled_unit_none():
    data = _make_doc(profiles=[_sampled_profile(unit="none")])
    profile = SpeedscopeParser("test.json").parse(data)
    assert profile.sample_types[0].sample_type == "samples"
    assert profile.sample_types[0].sample_unit == "count"


# ── evented profile ───────────────────────────────────────────────────────────


def test_parse_evented_profile():
    # O main(0), O foo(10), O bar(20), C bar(30), C foo(40), C main(50)
    # bar self-time = 30-20 = 10
    # foo self-time = (40-10) - 10 = 20
    # main self-time = (50-0) - 30 = 20
    data = _make_doc(profiles=[_evented_profile()])
    profile = SpeedscopeParser("test.json").parse(data)

    tree = frame2json(profile.root_stack)
    root_val = tree["root"]["values"][0]
    main_val = tree["root"]["children"][0]["main"]["values"][0]
    foo_val = tree["root"]["children"][0]["main"]["children"][0]["foo"]["values"][0]
    bar_val = (
        tree["root"]["children"][0]["main"]["children"][0]["foo"]["children"][0][
            "bar"
        ]["values"][0]
    )

    # main inclusive = 50, foo inclusive = 30, bar inclusive = 10
    assert main_val == 50
    assert foo_val == 30
    assert bar_val == 10
    assert root_val == 50


def test_parse_evented_profile_sample_types():
    data = _make_doc(profiles=[_evented_profile(unit="nanoseconds")])
    profile = SpeedscopeParser("test.json").parse(data)
    assert profile.sample_types[0].sample_type == "time"
    assert profile.sample_types[0].sample_unit == "nanoseconds"


def test_parse_evented_leaf_only():
    # Single frame, no children
    doc = {
        "$schema": "https://www.speedscope.app/file-format-schema.json",
        "shared": {"frames": [{"name": "solo"}]},
        "profiles": [
            {
                "type": "evented",
                "name": "t",
                "unit": "none",
                "startValue": 0,
                "endValue": 100,
                "events": [
                    {"type": "O", "at": 0, "frame": 0},
                    {"type": "C", "at": 100, "frame": 0},
                ],
            }
        ],
    }
    profile = SpeedscopeParser("test.json").parse(json.dumps(doc).encode())
    assert profile.root_stack.children[0].name == "solo"
    assert profile.root_stack.children[0].values[0] == 100


# ── activeProfileIndex ────────────────────────────────────────────────────────


def test_parse_uses_active_profile_index():
    doc = {
        "$schema": "https://www.speedscope.app/file-format-schema.json",
        "shared": {
            "frames": [
                {"name": "alpha"},
                {"name": "beta"},
            ]
        },
        "activeProfileIndex": 1,
        "profiles": [
            {
                "type": "sampled",
                "name": "first",
                "unit": "none",
                "startValue": 0,
                "endValue": 10,
                "samples": [[0]],
                "weights": [1],
            },
            {
                "type": "sampled",
                "name": "second",
                "unit": "none",
                "startValue": 0,
                "endValue": 10,
                "samples": [[1]],
                "weights": [2],
            },
        ],
    }
    profile = SpeedscopeParser("test.json").parse(json.dumps(doc).encode())
    assert profile.root_stack.children[0].name == "beta"
    assert profile.root_stack.children[0].values[0] == 2


# ── frame metadata ────────────────────────────────────────────────────────────


def test_parse_frame_file_line_stored():
    data = _make_doc(
        profiles=[
            {
                "type": "sampled",
                "name": "t",
                "unit": "none",
                "startValue": 0,
                "endValue": 10,
                "samples": [[0]],
                "weights": [1],
            }
        ]
    )
    profile = SpeedscopeParser("test.json").parse(data)
    frame = profile.root_stack.children[0]
    assert frame.name == "main"
    assert frame.file == "app.py"
    assert frame.line == 1


# ── parser registration ───────────────────────────────────────────────────────


def test_choose_parser_detects_speedscope():
    data = _make_doc(profiles=[_sampled_profile()])
    assert choose_parser(data) is SpeedscopeParser


def test_choose_parser_uses_speedscope_type(simple_collapse_data):
    from flamegraph_textual.parsers import choose_parser

    data = _make_doc(profiles=[_sampled_profile()])
    assert choose_parser(data, profile_type="speedscope") is SpeedscopeParser


def test_parse_api_returns_profile():
    data = _make_doc(profiles=[_sampled_profile()])
    profile = parse(data, "test.speedscope.json")
    assert profile.sample_types[0].sample_type == "time"
    assert profile.root_stack.children[0].name == "main"


# ── speedscoop_example.json (real-file round-trip) ───────────────────────────
#
# The file encodes this call tree (evented, unit="none"):
#
#   O a(0)  O b(0)  O c(0)  C c(2)  O d(2)  C d(6)  O c(6)  C c(9)  C b(14)  C a(14)
#
# Self-time chains emitted during parsing:
#   a→b→c : 2 (first close) + 3 (second close) = 5
#   a→b→d : 4
#   a→b   : b self-time = 14 − 9 = 5
#   a     : a self-time = 0 → skipped
#
# Expected inclusive values after pile-up:
#   root=14, a=14, b=14, c=5, d=4
#   total_sample = 4 (number of chains emitted)

from pathlib import Path

_PPROF_DATA = Path(__file__).parent.parent / "pprof_data"


@pytest.fixture(scope="module")
def speedscope_example_profile():
    data = (_PPROF_DATA / "speedscoop_example.json").read_bytes()
    return SpeedscopeParser("speedscoop_example.json").parse(data)


def test_speedscope_example_validates():
    data = (_PPROF_DATA / "speedscoop_example.json").read_bytes()
    assert SpeedscopeParser.validate(data)


def test_speedscope_example_tree_structure(speedscope_example_profile):
    assert frame2json(speedscope_example_profile.root_stack) == {
        "root": {
            "values": [14],
            "children": [
                {
                    "a": {
                        "values": [14],
                        "children": [
                            {
                                "b": {
                                    "values": [14],
                                    "children": [
                                        {"c": {"values": [5], "children": []}},
                                        {"d": {"values": [4], "children": []}},
                                    ],
                                }
                            }
                        ],
                    }
                }
            ],
        }
    }


def test_speedscope_example_root_value(speedscope_example_profile):
    assert speedscope_example_profile.root_stack.values[0] == 14


def test_speedscope_example_total_sample(speedscope_example_profile):
    # 4 self-time chains: a→b→c(2), a→b→d(4), a→b→c(3), a→b(5)
    assert speedscope_example_profile.total_sample == 4


def test_speedscope_example_highest_lines(speedscope_example_profile):
    # deepest chain is a→b→c or a→b→d (3 frames deep)
    assert speedscope_example_profile.highest_lines == 3


def test_speedscope_example_sample_type(speedscope_example_profile):
    # unit "none" maps to ("samples", "count")
    st = speedscope_example_profile.sample_types[0]
    assert st.sample_type == "samples"
    assert st.sample_unit == "count"


def test_speedscope_example_frame_names(speedscope_example_profile):
    root = speedscope_example_profile.root_stack
    a = root.children[0]
    b = a.children[0]
    child_names = {f.name for f in b.children}
    assert a.name == "a"
    assert b.name == "b"
    assert child_names == {"c", "d"}
