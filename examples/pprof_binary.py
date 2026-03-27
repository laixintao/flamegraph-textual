import argparse
from pathlib import Path

from textual.app import App, ComposeResult

from flamegraph_textual import FlameGraphView

EXAMPLES_DIR = Path(__file__).resolve().parents[1] / "tests" / "pprof_data"
SAMPLES = {
    "profile-10seconds": EXAMPLES_DIR / "profile-10seconds.out",
    "goroutine": EXAMPLES_DIR / "goroutine.out",
    "heap": EXAMPLES_DIR / "heap.out",
}


class PprofDemo(App):
    def __init__(self, profile_path: Path, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.profile_path = profile_path

    def compose(self) -> ComposeResult:
        profile_bytes = self.profile_path.read_bytes()
        yield FlameGraphView(profile_bytes, filename=self.profile_path.name)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Render pprof protobuf with flamegraph_textual."
    )
    parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        help="Optional path to a pprof .out file. Defaults to bundled sample.",
    )
    parser.add_argument(
        "--sample",
        choices=sorted(SAMPLES),
        default="profile-10seconds",
        help="Bundled sample to open when no path is provided.",
    )
    args = parser.parse_args()

    profile_path = args.path or SAMPLES[args.sample]
    PprofDemo(profile_path).run()


if __name__ == "__main__":
    main()
