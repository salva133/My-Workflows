"""Writes the list of vanilla asset paths the asset check reads.

A vanilla texture lives in the game install rather than in any repository, so
this is run once by hand against a copy of the game and its output committed:

    python3 make_asset_manifest.py "C:/Program Files (x86)/Steam/steamapps/common/Victoria 3/game" \
        > .github/vanilla-assets.txt

Re-run it after a game patch that adds art. Paths are written relative to the
game folder and with forward slashes, which is the form script files name them
in.
"""

import os
import sys

SUFFIXES = (".dds", ".tga", ".png", ".bk2", ".mesh", ".anim")


def main():
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        sys.exit(2)

    root = sys.argv[1]
    gfx = os.path.join(root, "gfx")
    if not os.path.isdir(gfx):
        print(f"No gfx folder under {root}", file=sys.stderr)
        sys.exit(1)

    paths = []
    for current, _, files in os.walk(gfx):
        for name in files:
            if name.lower().endswith(SUFFIXES):
                rel = os.path.relpath(os.path.join(current, name), root)
                paths.append(rel.replace(os.sep, "/"))

    for path in sorted(paths):
        print(path)


if __name__ == "__main__":
    main()
