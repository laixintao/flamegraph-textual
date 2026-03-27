# flamegraph-textual

Terminal flamegraph renderer built for Textual.

## Install

```shell
pip install flamegraph-textual
```

## Usage

```python
from textual.app import App, ComposeResult

from flamegraph_textual import FlameGraphView


class Demo(App):
    def compose(self) -> ComposeResult:
        profile_text = open("profile.out", "rb").read()
        yield FlameGraphView(profile_text, filename="profile.out")


Demo().run()
```

## Try It Quickly

Bundled sample profiles live under:
[tests/pprof_data](/Users/xintao.lai/Programs/flameshow-all/flamegraph-textual/tests/pprof_data)
and
[tests/stackcollapse_data](/Users/xintao.lai/Programs/flameshow-all/flamegraph-textual/tests/stackcollapse_data).

You can run the examples without preparing any input files:

```shell
python examples/pprof_binary.py
python examples/pprof_binary.py --sample goroutine
python examples/stackcollapse_text.py
python examples/stackcollapse_text.py --sample simple
```

Both examples also accept an optional positional path if you want to open your
own profile file instead of a bundled sample.

## Regenerate protobuf bindings

The canonical pprof schema now lives in:
[proto/profile.proto](/Users/xintao.lai/Programs/flameshow-all/flamegraph-textual/proto/profile.proto)

To regenerate
[profile_pb2.py](/Users/xintao.lai/Programs/flameshow-all/flamegraph-textual/flamegraph_textual/parsers/profile_pb2.py):

```shell
poetry add --group dev grpcio-tools
poetry run python -m grpc_tools.protoc \
  -I proto \
  --python_out=flamegraph_textual/parsers \
  proto/profile.proto
```
