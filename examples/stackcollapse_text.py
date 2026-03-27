import argparse
from pathlib import Path

from textual.app import App, ComposeResult

from flamegraph_textual import FlameGraphView

EXAMPLES_DIR = Path(__file__).resolve().parents[1] / "tests" / "stackcollapse_data"
SAMPLES = {
    "simple": EXAMPLES_DIR / "simple.txt",
    "with-comment": EXAMPLES_DIR / "with_comment.txt",
    "pyspy": EXAMPLES_DIR / "flameshow-pyspy-dump.txt",
    "perf": EXAMPLES_DIR / "perf-vertx-stacks-01-collapsed-all.txt",
}


class StackCollapseDemo(App):
    def __init__(self, profile_path: Path, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.profile_path = profile_path

    def compose(self) -> ComposeResult:
        profile_text = self.profile_path.read_text(encoding="utf-8")
        yield FlameGraphView(
            profile_text,
            filename=self.profile_path.name,
            profile_type="stackcollapse",
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Render stackcollapse-compatible text "
            "(including Austin collapsed output) with flamegraph_textual."
        )
    )
    parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        help=(
            "Optional path to stackcollapse-compatible text. "
            "Defaults to bundled sample."
        ),
    )
    parser.add_argument(
        "--sample",
        choices=sorted(SAMPLES),
        default="pyspy",
        help="Bundled sample to open when no path is provided.",
    )
    args = parser.parse_args()

    profile_path = args.path or SAMPLES[args.sample]
    StackCollapseDemo(profile_path).run()


if __name__ == "__main__":
    main()
