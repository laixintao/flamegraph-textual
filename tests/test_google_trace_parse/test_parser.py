import json

from flamegraph_textual.parsers import choose_parser, parse
from flamegraph_textual.parsers.google_trace_parser import GoogleTraceParser

from ..utils import frame2json


def _enc(obj) -> bytes:
    return json.dumps(obj).encode()


# ── fixtures ──────────────────────────────────────────────────────────────────

SIMPLE_X_EVENTS = [
    {"name": "main", "ph": "X", "ts": 0, "dur": 50, "pid": 1, "tid": 1},
    {"name": "foo", "ph": "X", "ts": 10, "dur": 20, "pid": 1, "tid": 1},
    {"name": "bar", "ph": "X", "ts": 10, "dur": 10, "pid": 1, "tid": 1},
]

SIMPLE_BE_EVENTS = [
    {"name": "main", "ph": "B", "ts": 0, "pid": 1, "tid": 1},
    {"name": "foo", "ph": "B", "ts": 10, "pid": 1, "tid": 1},
    {"name": "bar", "ph": "B", "ts": 20, "pid": 1, "tid": 1},
    {"name": "bar", "ph": "E", "ts": 30, "pid": 1, "tid": 1},
    {"name": "foo", "ph": "E", "ts": 40, "pid": 1, "tid": 1},
    {"name": "main", "ph": "E", "ts": 50, "pid": 1, "tid": 1},
]


# ── validate ──────────────────────────────────────────────────────────────────


def test_validate_detects_array_format():
    assert GoogleTraceParser.validate(_enc(SIMPLE_X_EVENTS))


def test_validate_detects_object_format():
    doc = {"traceEvents": SIMPLE_X_EVENTS}
    assert GoogleTraceParser.validate(_enc(doc))


def test_validate_detects_be_events():
    assert GoogleTraceParser.validate(_enc(SIMPLE_BE_EVENTS))


def test_validate_rejects_non_json():
    assert not GoogleTraceParser.validate(b"a;b;c 10\n")


def test_validate_rejects_json_without_trace_events():
    assert not GoogleTraceParser.validate(_enc({"foo": "bar"}))


def test_validate_rejects_array_without_ph():
    assert not GoogleTraceParser.validate(_enc([{"name": "x", "ts": 0}]))


def test_validate_rejects_speedscope_object():
    doc = {
        "$schema": "https://www.speedscope.app/file-format-schema.json",
        "shared": {"frames": []},
        "profiles": [],
    }
    # speedscope files have no "traceEvents" key → rejected
    assert not GoogleTraceParser.validate(_enc(doc))


# ── X event (complete event) parsing ─────────────────────────────────────────


def test_parse_x_events_array_format():
    """main(50us) contains foo(20us) which contains bar(10us)."""
    profile = GoogleTraceParser("t.json").parse(_enc(SIMPLE_X_EVENTS))
    tree = frame2json(profile.root_stack)

    # main self-time = 50 - 20 = 30; foo self-time = 20 - 10 = 10; bar = 10
    thread_children = tree["root"]["children"][0]
    thread_name = list(thread_children.keys())[0]
    thread_data = thread_children[thread_name]

    main = thread_data["children"][0]["main"]
    foo = main["children"][0]["foo"]
    bar = foo["children"][0]["bar"]

    assert main["values"][0] == 50
    assert foo["values"][0] == 20
    assert bar["values"][0] == 10


def test_parse_x_events_object_format():
    doc = {"traceEvents": SIMPLE_X_EVENTS, "displayTimeUnit": "us"}
    profile = GoogleTraceParser("t.json").parse(_enc(doc))
    assert profile.sample_types[0].sample_unit == "microseconds"
    assert profile.root_stack.children[0].children[0].name == "main"


def test_parse_x_events_sample_type():
    profile = GoogleTraceParser("t.json").parse(_enc(SIMPLE_X_EVENTS))
    assert profile.sample_types[0].sample_type == "time"
    assert profile.sample_types[0].sample_unit == "microseconds"


# ── B/E duration event parsing ────────────────────────────────────────────────


def test_parse_be_events():
    """Same structure as X events but described with begin/end pairs."""
    # B main(0), B foo(10), B bar(20), E bar(30), E foo(40), E main(50)
    # bar self = 10, foo self = 10, main self = 30
    profile = GoogleTraceParser("t.json").parse(_enc(SIMPLE_BE_EVENTS))
    tree = frame2json(profile.root_stack)

    thread_children = tree["root"]["children"][0]
    thread_data = list(thread_children.values())[0]
    main = thread_data["children"][0]["main"]
    foo = main["children"][0]["foo"]
    bar = foo["children"][0]["bar"]

    assert main["values"][0] == 50
    assert foo["values"][0] == 30
    assert bar["values"][0] == 10


def test_parse_be_leaf_only():
    events = [
        {"name": "solo", "ph": "B", "ts": 0, "pid": 1, "tid": 1},
        {"name": "solo", "ph": "E", "ts": 100, "pid": 1, "tid": 1},
    ]
    profile = GoogleTraceParser("t.json").parse(_enc(events))
    thread_frame = profile.root_stack.children[0]
    assert thread_frame.children[0].name == "solo"
    assert thread_frame.children[0].values[0] == 100


# ── thread/process grouping ───────────────────────────────────────────────────


def test_parse_multi_thread():
    """Two threads produce two separate subtrees under root."""
    events = [
        {"name": "alpha", "ph": "X", "ts": 0, "dur": 10, "pid": 1, "tid": 1},
        {"name": "beta", "ph": "X", "ts": 0, "dur": 20, "pid": 1, "tid": 2},
    ]
    profile = GoogleTraceParser("t.json").parse(_enc(events))
    thread_names = {c.name for c in profile.root_stack.children}
    assert len(thread_names) == 2
    assert "pid=1 tid=1" in thread_names
    assert "pid=1 tid=2" in thread_names


def test_parse_thread_name_from_metadata():
    events = [
        {"name": "thread_name", "ph": "M", "pid": 1, "tid": 1, "args": {"name": "Main Thread"}},
        {"name": "work", "ph": "X", "ts": 0, "dur": 50, "pid": 1, "tid": 1},
    ]
    profile = GoogleTraceParser("t.json").parse(_enc(events))
    assert profile.root_stack.children[0].name == "Main Thread"


def test_parse_process_name_from_metadata():
    events = [
        {"name": "process_name", "ph": "M", "pid": 42, "tid": 1, "args": {"name": "MyApp"}},
        {"name": "work", "ph": "X", "ts": 0, "dur": 50, "pid": 42, "tid": 1},
    ]
    profile = GoogleTraceParser("t.json").parse(_enc(events))
    assert profile.root_stack.children[0].name == "MyApp (tid=1)"


# ── displayTimeUnit ───────────────────────────────────────────────────────────


def test_parse_display_time_unit_ms():
    doc = {"traceEvents": SIMPLE_X_EVENTS, "displayTimeUnit": "ms"}
    profile = GoogleTraceParser("t.json").parse(_enc(doc))
    assert profile.sample_types[0].sample_unit == "milliseconds"


def test_parse_display_time_unit_ns():
    doc = {"traceEvents": SIMPLE_X_EVENTS, "displayTimeUnit": "ns"}
    profile = GoogleTraceParser("t.json").parse(_enc(doc))
    assert profile.sample_types[0].sample_unit == "nanoseconds"


# ── highest_lines ─────────────────────────────────────────────────────────────


def test_parse_highest_lines():
    """root → thread → main → foo → bar = depth 4 (not counting root level)."""
    profile = GoogleTraceParser("t.json").parse(_enc(SIMPLE_X_EVENTS))
    # Thread level + 3 function levels = 4
    assert profile.highest_lines == 4


# ── parser registration ───────────────────────────────────────────────────────


def test_choose_parser_detects_google_trace():
    assert choose_parser(_enc(SIMPLE_X_EVENTS)) is GoogleTraceParser


def test_choose_parser_uses_google_trace_type():
    assert choose_parser(_enc(SIMPLE_X_EVENTS), profile_type="google-trace") is GoogleTraceParser


def test_parse_api_returns_profile():
    profile = parse(_enc(SIMPLE_X_EVENTS), "trace.json")
    assert profile.sample_types[0].sample_type == "time"


# ── edge cases ────────────────────────────────────────────────────────────────


def test_parse_skips_unmatched_end_events():
    events = [
        {"name": "foo", "ph": "E", "ts": 100, "pid": 1, "tid": 1},  # no matching B
        {"name": "bar", "ph": "X", "ts": 200, "dur": 10, "pid": 1, "tid": 1},
    ]
    profile = GoogleTraceParser("t.json").parse(_enc(events))
    assert profile.root_stack.children[0].children[0].name == "bar"


def test_parse_ignores_metadata_and_other_events():
    events = [
        {"name": "thread_name", "ph": "M", "pid": 1, "tid": 1, "args": {"name": "T"}},
        {"name": "counter", "ph": "C", "ts": 0, "pid": 1, "tid": 1},
        {"name": "instant", "ph": "i", "ts": 0, "pid": 1, "tid": 1},
        {"name": "work", "ph": "X", "ts": 0, "dur": 10, "pid": 1, "tid": 1},
    ]
    profile = GoogleTraceParser("t.json").parse(_enc(events))
    thread = profile.root_stack.children[0]
    assert thread.name == "T"
    assert thread.children[0].name == "work"


def test_parse_zero_duration_events_ignored():
    events = [
        {"name": "work", "ph": "X", "ts": 0, "dur": 100, "pid": 1, "tid": 1},
        {"name": "instant", "ph": "X", "ts": 50, "dur": 0, "pid": 1, "tid": 1},
    ]
    profile = GoogleTraceParser("t.json").parse(_enc(events))
    thread = profile.root_stack.children[0]
    assert thread.children[0].name == "work"
    # zero-dur instant event contributes nothing
    assert thread.values[0] == 100
