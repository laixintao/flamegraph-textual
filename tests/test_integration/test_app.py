import asyncio

from flamegraph_textual.render.app import FlameshowApp


def test_app_startup(profile10s_profile):
    async def run() -> None:
        app = FlameshowApp(profile10s_profile)
        async with app.run_test() as pilot:
            center_text = app.query_one("HeaderOpenedFilename")
            assert (
                center_text.filename
                == "pprof_data/profile-10seconds.out: (cpu, nanoseconds)"
            )

            await pilot.press("j")
            flamegraph_widget = app.query_one("FlameGraph")
            assert flamegraph_widget.view_frame._id == 34
            assert flamegraph_widget.view_frame.name == "runtime.mcall"

    asyncio.run(run())
