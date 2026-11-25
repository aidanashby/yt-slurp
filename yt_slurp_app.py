"""Entry point for the bundled yt-slurp.exe (built with PyInstaller)."""

import sys

import yt_slurp_setup as setup


def main() -> int:
    if len(sys.argv) == 4 and sys.argv[1] == "--check-engine":
        import yt_slurp_engine
        return yt_slurp_engine.check_engine(sys.argv[2], sys.argv[3])
    setup.tidy_after_update()
    import yt_slurp_gui
    return yt_slurp_gui.main()


if __name__ == "__main__":
    sys.exit(main())
