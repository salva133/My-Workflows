"""File-level lint for the localization of a Victoria 3 mod.

The game picks a localization file by its name and header and drops it whole
when either is off, logging one line to error.log. Inside a value, a bracket or
substitution left open does not fail the load either; it shows up on screen as
raw script text.

  LOC_FILENAME   a file whose name does not end in _l_<language>.yml, which the
                 game never reads
  LOC_BOM        a file with no byte order mark, which the game refuses. Skipped
                 when require_bom is set, since BOM_MISSING says it already
  LOC_HEADER     a first line other than l_<language>:, or one naming another
                 language than the file name does
  LOC_FOLDER     a file under localization/<language>/ for another language
  LOC_BRACKET    a [ with no ] or the other way round, so a data function is
                 printed as text
  LOC_DOLLAR     an odd number of $, so a substitution never closes

Formatting tags are left alone: vanilla closes a #tag opened by the string it
is substituted into as often as its own, so a count per value proves nothing.

Files matched by lint_exempt are skipped.
"""

import argparse
import fnmatch
import os
import re
import sys

from vic3lib import LOC_LINE, Report, load_config, read_lines, walk_files

LANGUAGES = ("english", "french", "german", "polish", "russian", "spanish",
             "braz_por", "japanese", "simp_chinese", "korean", "turkish")
FILENAME = re.compile(r"_l_(\w+?)\.yml$")
HEADER = re.compile(r"^l_(\w+):\s*(#.*)?$")
BRACKET = re.compile(r"\[[^\[\]]*\]")
BOM = b"\xef\xbb\xbf"


def matches(rel, patterns):
    return any(fnmatch.fnmatch(rel, p) for p in patterns)


def has_bom(path):
    with open(path, "rb") as fh:
        return fh.read(3) == BOM


def folder_language(rel):
    for part in rel.split("/")[1:-1]:
        if part in LANGUAGES:
            return part
    return None


def check_file(full, rel, check_bom, report):
    name = os.path.basename(rel)
    found = FILENAME.search(name)
    language = found.group(1) if found else None
    if language not in LANGUAGES:
        report.error(
            "LOC_FILENAME",
            f"'{name}' does not end in _l_<language>.yml with a language the game "
            f"knows ({', '.join(LANGUAGES)}), so the game never reads it.",
            rel, 1,
        )
        language = None

    if check_bom and not has_bom(full):
        report.error(
            "LOC_BOM",
            "Localization file carries no byte order mark, and the game refuses it.",
            rel, 1,
        )

    folder = folder_language(rel)
    if language and folder and folder != language:
        report.warn(
            "LOC_FOLDER",
            f"File is named for {language} but sits in the {folder} folder.",
            rel, 1,
        )

    lines = read_lines(full)
    header_seen = False
    for number, line in enumerate(lines, 1):
        text = line.strip()
        if not header_seen:
            if not text or text.startswith("#"):
                continue
            header_seen = True
            head = HEADER.match(text)
            if not head:
                report.error(
                    "LOC_HEADER",
                    "First line is not the l_<language>: header, so the game reads "
                    "none of the keys below it.",
                    rel, number,
                )
            elif language and head.group(1) != language:
                report.error(
                    "LOC_HEADER",
                    f"Header reads l_{head.group(1)}: while the file name says "
                    f"{language}. The game files the keys under the header's language.",
                    rel, number,
                )
            continue

        match = LOC_LINE.match(line)
        if match:
            check_value(match.group(2), match.group(4), rel, number, report)

    if not header_seen:
        report.error("LOC_HEADER", "File carries no l_<language>: header.", rel, 1)


def check_value(key, value, rel, number, report):
    if value.strip() in ("", "[", "]"):
        return

    outside = value
    while True:
        reduced = BRACKET.sub(" ", outside)
        if reduced == outside:
            break
        outside = reduced
    if "[" in outside or "]" in outside:
        report.error(
            "LOC_BRACKET",
            f"'{key}' carries a bracket with no partner, so the data function in it "
            "is printed as text.",
            rel, number,
        )

    if value.count("$") % 2:
        report.warn(
            "LOC_DOLLAR",
            f"'{key}' carries an odd number of $, so a substitution never closes.",
            rel, number,
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mod", default=".")
    parser.add_argument("--config", default=".github/vic3-validate.json")
    args = parser.parse_args()

    config = load_config(args.mod, args.config)
    report = Report("Localization lint")
    exempt = config.get("lint_exempt", [])
    check_bom = not config.get("require_bom")

    for full, rel in walk_files(args.mod, (".yml",), "localization"):
        if matches(rel, exempt):
            continue
        check_file(full, rel, check_bom, report)

    sys.exit(report.finish())


if __name__ == "__main__":
    main()
