"""Asset path check for a Victoria 3 mod.

An icon or texture path naming no file is not caught at load. The engine logs
it once and draws nothing thereafter, so a missing icon reaches the screen as
an empty space rather than as an error.

  ASSET_MISSING   a gfx path that resolves to no file in the mod and appears in
                  no vanilla asset manifest

The mod's own tree answers most of them. The rest need a manifest, because a
vanilla asset lives in the game install rather than in any repository: generate
it once with tools/make_asset_manifest.py against a checkout of the game and
commit the result. Without a manifest the check reports only the paths the mod
was expected to ship itself and says so.
"""

import argparse
import os
import re
import sys

from vic3lib import Report, load_config, read_lines, walk_files

ASSET = re.compile(r'"((?:gfx|game/gfx)/[^"]+\.(?:dds|tga|png|bk2|mesh|anim))"')
MANIFEST = ".github/vanilla-assets.txt"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mod", default=".")
    parser.add_argument("--config", default=".github/vic3-validate.json")
    args = parser.parse_args()

    config = load_config(args.mod, args.config)
    report = Report("Asset paths")

    manifest_path = os.path.join(args.mod, config.get("asset_manifest", MANIFEST))
    manifest = set()
    if os.path.isfile(manifest_path):
        manifest = {line.strip().replace("\\", "/").lower()
                    for line in read_lines(manifest_path) if line.strip()}
    else:
        print(f"::notice::No vanilla asset manifest at "
              f"{os.path.relpath(manifest_path, args.mod)}, so only the mod's own "
              "assets are resolved and a vanilla path cannot be told from a typo.")

    own = set()
    for _, rel in walk_files(args.mod, ("",), "gfx"):
        own.add(rel.lower())

    seen = set()
    for directory in ("common", "events", "gui"):
        for full, rel in walk_files(args.mod, (".txt", ".gui"), directory):
            for number, line in enumerate(read_lines(full), 1):
                for match in ASSET.finditer(line):
                    path = match.group(1).replace("\\", "/")
                    lookup = path[len("game/"):] if path.startswith("game/") else path
                    lookup = lookup.lower()
                    if lookup in own or lookup in manifest:
                        continue
                    if not manifest:
                        continue
                    if (rel, path) in seen:
                        continue
                    seen.add((rel, path))
                    report.error(
                        "ASSET_MISSING",
                        f"'{path}' names no file in this mod and none in the vanilla "
                        "asset manifest. The engine logs it once and draws nothing.",
                        rel, number,
                    )

    sys.exit(report.finish())


if __name__ == "__main__":
    main()
