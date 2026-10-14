"""Entry point for the bundled yt-slurp.exe (built with PyInstaller)."""

import sys

import yt_slurp_setup as setup


def main() -> int:
    setup.tidy_after_update()
    import yt_slurp_gui
    return yt_slurp_gui.main()


if __name__ == "__main__":
    sys.exit(main())
