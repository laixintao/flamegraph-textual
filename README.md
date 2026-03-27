# flamegraph-textual

`flamegraph-textual` is an interactive flamegraph component for
[Textual](https://github.com/Textualize/textual).

![](./docs/flamegraph-textual.png)

It is the rendering library extracted from
[flameshow](https://github.com/laixintao/flameshow). Use it when you want to
embed a terminal flamegraph inside your own Textual app instead of launching a
standalone viewer.

## Install

From PyPI:

```shell
pip install flamegraph-textual
```

From a local checkout:

```shell
git clone git@github.com:laixintao/flamegraph-textual.git
cd flamegraph-textual
pip install -e .
```

For development with Poetry:

```shell
git clone git@github.com:laixintao/flamegraph-textual.git
cd flamegraph-textual
poetry install
```

## What It Does

- Renders flamegraphs as a Textual widget
- Parses profile input for you
- Supports keyboard and mouse navigation
- Supports multiple sample types when present in the profile
- Works with bundled demo data or your own files

## Quick Start

`FlameGraphView` is the main entrypoint. Pass it raw profile data and a
filename. The library parses the content internally.

```python
from pathlib import Path

from textual.app import App, ComposeResult

from flamegraph_textual import FlameGraphView


class Demo(App):
    def compose(self) -> ComposeResult:
        profile_bytes = Path("profile.out").read_bytes()
        yield FlameGraphView(profile_bytes, filename="profile.out")


Demo().run()
```

For stackcollapse text input, passing `str` also works:

```python
from pathlib import Path

from flamegraph_textual import FlameGraphView

profile_text = Path("stacks.txt").read_text(encoding="utf-8")
widget = FlameGraphView(profile_text, filename="stacks.txt")

# Optional: skip auto-detection when you already know the format
widget = FlameGraphView(
    profile_text,
    filename="stacks.txt",
    profile_type="stackcollapse",
)
```

For Austin collapsed text, use the same parser explicitly:

```python
from pathlib import Path

from flamegraph_textual import FlameGraphView

austin_text = Path("austin.txt").read_text(encoding="utf-8")
widget = FlameGraphView(
    austin_text,
    filename="austin.txt",
    profile_type="austin",
)
```

## Supported Input Formats

- `pprof`: pprof protobuf profiles
- `stackcollapse`: generic collapsed-stack text in FlameGraph format
- `austin`: Austin collapsed text; parsed with the same stackcollapse parser

### Format Notes

- `pprof`
  Binary protobuf profiles such as Go `pprof` output. Use this when your input
  is raw profile bytes.
- `stackcollapse`
  Plain text in collapsed-stack format, where each line looks like
  `frame_a;frame_b;frame_c 10`.
- `austin`
  Austin's collapsed text output is stackcollapse-compatible, often with
  metadata comment lines such as `# austin: ...`, `# interval: ...`, and
  `# mode: ...`. Those comment lines are ignored by the parser.

The parser selection is automatic through:
[parse](./flamegraph_textual/parsers/__init__.py)

## Try It Immediately

This repo includes sample profiles under:

- [tests/pprof_data](./tests/pprof_data)
- [tests/stackcollapse_data](./tests/stackcollapse_data)

Run the bundled examples with no setup:

```shell
python examples/pprof_binary.py
python examples/pprof_binary.py --sample goroutine
python examples/pprof_binary.py --sample heap

python examples/stackcollapse_text.py
python examples/stackcollapse_text.py --sample simple
python examples/stackcollapse_text.py --sample perf
```

You can still pass your own file path:

```shell
python examples/pprof_binary.py /path/to/profile.out
python examples/stackcollapse_text.py /path/to/stacks.txt
```

## Main API

The public exports are defined in:
[__init__.py](./flamegraph_textual/__init__.py)

Most users should start with:

- [FlameGraphView](./flamegraph_textual/view.py)
  for embedding a flamegraph widget in a Textual app
- [parse](./flamegraph_textual/parsers/__init__.py)
  if you want to parse profile bytes yourself

`parse(...)` and `FlameGraphView(...)` both support an optional
`profile_type` argument. Supported values are `pprof`, `stackcollapse`, and
`austin`. If omitted, the library auto-detects the parser as before.

Other public exports:

- `FlameGraphApp`
  convenience alias around the full demo-style app
- `FlameGraph`
  lower-level rendering widget
- `FlameGraphScroll`
  scroll container used around the flamegraph widget
- `Frame`, `Profile`, `SampleType`
  data model types
- `FrameMap`, `add_array`
  lower-level rendering helpers used by the widget

## Controls

Inside the widget:

- `j` / `k` / `h` / `l` or arrow keys move selection
- `Enter` zooms in
- `Esc` zooms out
- `Tab` switches sample type
- `i` opens the detail screen when mounted inside a Textual app
- Mouse hover updates frame details
- Mouse click zooms into a frame

## Regenerate Protobuf Bindings

The canonical pprof schema lives in:
[profile.proto](./proto/profile.proto)

The generated Python module lives in:
[profile_pb2.py](./flamegraph_textual/parsers/profile_pb2.py)

Regenerate it with:

```shell
poetry add --group dev grpcio-tools
poetry run python -m grpc_tools.protoc \
  -I proto \
  --python_out=flamegraph_textual/parsers \
  proto/profile.proto
```

## Development

Run tests with:

```shell
pytest -q
```
