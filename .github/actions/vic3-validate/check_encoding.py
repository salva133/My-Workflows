"""File encoding checks for a Victoria 3 mod.

Without a byte order mark the game drops umlauts from a script file without
saying so, and one kind of file wants the opposite: a copy of a vanilla file
carries whatever encoding vanilla wrote it in.

  BOM_MISSING   a script or localization file with no byte order mark
  BOM_PRESENT   a file the config lists as carrying none has one anyway

Both are opt-in through require_bom, so a mod that does not hold the rule is
not held to it.
"""

import argparse
import fnmatch
import os
import sys

from vic3lib import Report, load_config, walk_files

BOM = b"\xef\xbb\xbf"
CONTENT_DIRS = ("common", "events", "localization", "map_data")


def has_bom(path):
    with open(path, "rb") as fh:
        return fh.read(3) == BOM


def matches(rel, patterns):
    return any(fnmatch.fnmatch(rel, p) for p in patterns)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mod", default=".")
    parser.add_argument("--config", default=".github/vic3-validate.json")
    args = parser.parse_args()

    config = load_config(args.mod, args.config)
    report = Report("File encoding")

    if not config.get("require_bom"):
        print("::notice::require_bom is not set, so the encoding checks are skipped.")
        sys.exit(report.finish())

    no_bom = config.get("no_bom", [])
    exempt = config.get("bom_exempt", [])

    for directory in CONTENT_DIRS:
        for full, rel in walk_files(args.mod, (".txt", ".yml"), directory):
            if matches(rel, exempt) or matches(rel, no_bom):
                continue
            if not has_bom(full):
                report.error(
                    "BOM_MISSING",
                    "File carries no byte order mark. The game reads it anyway and "
                    "drops the umlauts on the way.",
                    rel, 1,
                )

    for pattern in no_bom:
        for full, rel in walk_files(args.mod, ("",)):
            if fnmatch.fnmatch(rel, pattern) and has_bom(full):
                report.error(
                    "BOM_PRESENT",
                    "File carries a byte order mark, and the config asks for none "
                    "here because it stands in for a vanilla file written without one.",
                    rel, 1,
                )

    sys.exit(report.finish())


if __name__ == "__main__":
    main()
