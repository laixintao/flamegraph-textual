import datetime
import json
from pathlib import Path

import pytest

from flamegraph_textual.parsers import profile_pb2
from flamegraph_textual.parsers.pprof_parser import get_frame_tree, parse_profile

pytest_plugins = ("pytest_asyncio",)


class StringTable:
    def __init__(self) -> None:
        self.values = [""]
        self.index = {"": 0}

    def add(self, value: str) -> int:
        if value not in self.index:
            self.index[value] = len(self.values)
            self.values.append(value)
        return self.index[value]


def _to_nanos(dt: datetime.datetime) -> int:
    return int(dt.timestamp() * 1_000_000_000)


def _build_profile10s_bytes() -> bytes:
    profile = profile_pb2.Profile()
    strings = StringTable()

    profile.string_table.extend(strings.values)

    st_samples = profile.sample_type.add()
    st_samples.type = strings.add("samples")
    st_samples.unit = strings.add("count")

    st_cpu = profile.sample_type.add()
    st_cpu.type = strings.add("cpu")
    st_cpu.unit = strings.add("nanoseconds")

    profile.period_type.type = strings.add("cpu")
    profile.period_type.unit = strings.add("nanoseconds")
    profile.period = 10_000_000
    profile.time_nanos = _to_nanos(
        datetime.datetime(
            2023,
            9,
            9,
            7,
            8,
            29,
            866118,
            tzinfo=datetime.timezone.utc,
        )
    )

    mapping = profile.mapping.add()
    mapping.id = 1
    mapping.memory_start = 1
    mapping.memory_limit = 2
    mapping.file_offset = 0
    mapping.filename = strings.add("/tmp/profile10s.bin")
    mapping.build_id = strings.add("")
    mapping.has_functions = True

    function_id = 1
    location_id = 1

    def add_chain_sample(names: list[str], values: list[int]) -> None:
        nonlocal function_id, location_id
        location_ids: list[int] = []
        for depth, name in enumerate(names, start=1):
            fn = profile.function.add()
            fn.id = function_id
            fn.name = strings.add(name)
            fn.system_name = strings.add(name)
            fn.filename = strings.add(f"/src/{name}.go")
            fn.start_line = depth

            loc = profile.location.add()
            loc.id = location_id
            loc.mapping_id = 1
            loc.address = 0x1000 + depth
            line = loc.line.add()
            line.function_id = function_id
            line.line = depth

            location_ids.append(location_id)
            function_id += 1
            location_id += 1

        sample = profile.sample.add()
        sample.location_id.extend(location_ids)
        sample.value.extend(values)

    add_chain_sample(
        [f"sample.one.depth.{i}" for i in range(26)],
        [10, 100],
    )
    add_chain_sample(
        [f"sample.two.depth.{i}" for i in range(7)],
        [20, 200],
    )
    add_chain_sample(
        ["runtime.mcall"],
        [500, 9_999],
    )

    profile.string_table[:] = strings.values
    return profile.SerializeToString()


def _build_goroutine_bytes() -> bytes:
    profile = profile_pb2.Profile()
    strings = StringTable()

    profile.string_table.extend(strings.values)

    sample_type = profile.sample_type.add()
    sample_type.type = strings.add("goroutine")
    sample_type.unit = strings.add("count")

    profile.period_type.type = strings.add("goroutine")
    profile.period_type.unit = strings.add("count")
    profile.period = 1
    profile.time_nanos = _to_nanos(
        datetime.datetime(
            2023,
            9,
            9,
            7,
            8,
            29,
            664363,
            tzinfo=datetime.timezone.utc,
        )
    )

    mappings = [
        (
            1,
            4194304,
            11280384,
            0,
            "/usr/bin/node-exporter",
            True,
            False,
            False,
            False,
        ),
        (
            2,
            140721318682624,
            140721318690816,
            0,
            "[vdso]",
            False,
            False,
            False,
            False,
        ),
        (
            3,
            18446744073699065856,
            18446744073699069952,
            0,
            "[vsyscall]",
            False,
            False,
            False,
            False,
        ),
    ]
    for (
        mapping_id,
        start,
        limit,
        offset,
        filename,
        has_functions,
        has_filenames,
        has_line_numbers,
        has_inline_frames,
    ) in mappings:
        mapping = profile.mapping.add()
        mapping.id = mapping_id
        mapping.memory_start = start
        mapping.memory_limit = limit
        mapping.file_offset = offset
        mapping.filename = strings.add(filename)
        mapping.build_id = strings.add("")
        mapping.has_functions = has_functions
        mapping.has_filenames = has_filenames
        mapping.has_line_numbers = has_line_numbers
        mapping.has_inline_frames = has_inline_frames

    function_names = ["runtime.gopark"] + [
        f"goroutine.frame.{i}" for i in range(2, 25)
    ]

    for function_id, name in enumerate(function_names, start=1):
        fn = profile.function.add()
        fn.id = function_id
        fn.name = strings.add(name)
        fn.system_name = strings.add(name)
        if function_id == 1:
            fn.filename = strings.add("/usr/local/go/src/runtime/proc.go")
            fn.start_line = 0
        else:
            fn.filename = strings.add(f"/src/{name}.go")
            fn.start_line = function_id

    first_loc = profile.location.add()
    first_loc.id = 1
    first_loc.mapping_id = 1
    first_loc.address = 4435364
    first_line = first_loc.line.add()
    first_line.function_id = 1
    first_line.line = 336

    for location_id in range(2, 25):
        loc = profile.location.add()
        loc.id = location_id
        loc.mapping_id = 1
        loc.address = 0x2000 + location_id
        line = loc.line.add()
        line.function_id = location_id
        line.line = location_id

    sample = profile.sample.add()
    sample.location_id.extend(range(1, 25))
    sample.value.append(1)

    profile.string_table[:] = strings.values
    return profile.SerializeToString()


@pytest.fixture(scope="session")
def data_dir(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("fixture-data")
    goroutine_profile = parse_profile(_build_goroutine_bytes(), "profile10s.out")
    with open(root / "goroutine_frametree.json", "w", encoding="utf-8") as f:
        json.dump(get_frame_tree(goroutine_profile.root_stack), f)
    return root


@pytest.fixture(scope="session")
def goroutine_pprof() -> bytes:
    return _build_goroutine_bytes()


@pytest.fixture(scope="session")
def profile10s() -> bytes:
    return _build_profile10s_bytes()


@pytest.fixture(scope="session")
def profile10s_profile(profile10s):
    return parse_profile(profile10s, "pprof_data/profile-10seconds.out")


@pytest.fixture(scope="session")
def simple_collapse_data() -> bytes:
    return b"""a;b;c 1
a;b;c 2
a;b;d 4
a;b;c 2
a;b 5
"""


@pytest.fixture(scope="session")
def collapse_data_with_comment() -> bytes:
    return b"""# austin: 3.7.0
# interval: 100
# mode: wall
a;b;c 10
5
c 4
10
"""
