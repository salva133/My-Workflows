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

With --fix, the findings that have exactly one reading are repaired before the
report is drawn. A missing byte order mark is added. A file name without a
known language suffix is given the one its header names, or failing that its
folder, and one whose header and folder agree on another language is renamed
to match them. A missing header is inserted from the file name when the first line
is already a key. A header naming no known language is corrected to the file
name's, and so is one naming another language when the folder sides with the
file name. Brackets and substitutions are left for a person.

Files matched by lint_exempt are skipped.
"""

import argparse
import fnmatch
import os
import re
import sys

from vic3lib import (BOM, LOC_LINE, Report, load_config, read_lines, read_raw,
                     walk_files, write_raw)

LANGUAGES = ("english", "french", "german", "polish", "russian", "spanish",
             "braz_por", "japanese", "simp_chinese", "korean", "turkish")
FILENAME = re.compile(r"_l_(\w+?)\.yml$")
HEADER = re.compile(r"^l_(\w+):\s*(#.*)?$")
BRACKET = re.compile(r"\[[^\[\]]*\]")


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


def first_content_line(lines):
    for index, line in enumerate(lines):
        text = line.strip()
        if text and not text.startswith("#"):
            return index, text
    return None, ""


def rename(full, rel, report, language):
    name = os.path.basename(rel)
    found = FILENAME.search(name)
    stem = name[:found.start()] if found else name[:-len(".yml")]
    new_name = f"{stem}_l_{language}.yml"
    new_full = os.path.join(os.path.dirname(full), new_name)
    if os.path.exists(new_full):
        return full, rel
    os.rename(full, new_full)
    new_rel = f"{os.path.dirname(rel)}/{new_name}"
    report.notice("LOC_FIXED", f"Renamed '{name}' to '{new_name}'.", new_rel, 1)
    return new_full, new_rel


def fix_file(full, rel, report):
    raw = read_raw(full)
    if raw is None:
        return full, rel
    bom, text = raw
    lines = text.splitlines(keepends=True)
    index, first = first_content_line(lines)
    head = HEADER.match(first)
    header_language = head.group(1) if head and head.group(1) in LANGUAGES else None
    folder = folder_language(rel)

    found = FILENAME.search(os.path.basename(rel))
    language = found.group(1) if found and found.group(1) in LANGUAGES else None
    if not language and (header_language or folder):
        full, rel = rename(full, rel, report, header_language or folder)
    elif language and header_language == folder and folder not in (None, language):
        full, rel = rename(full, rel, report, folder)
    found = FILENAME.search(os.path.basename(rel))
    language = found.group(1) if found and found.group(1) in LANGUAGES else None

    changed = False
    newline = "\r\n" if "\r\n" in text else "\n"
    if language:
        wanted = f"l_{language}:"
        if index is None or (not head and LOC_LINE.match(lines[index])):
            lines.insert(0, wanted + newline)
            report.notice("LOC_FIXED", f"Inserted the {wanted} header.", rel, 1)
            changed = True
        elif head and head.group(1) != language and (
                head.group(1) not in LANGUAGES or folder == language):
            comment = f" {head.group(2)}" if head.group(2) else ""
            ending = lines[index][len(lines[index].rstrip("\r\n")):]
            lines[index] = wanted + comment + ending
            report.notice("LOC_FIXED",
                          f"Corrected the header from l_{head.group(1)}: to {wanted}",
                          rel, index + 1)
            changed = True

    if not bom:
        report.notice("LOC_FIXED", "Added the byte order mark.", rel, 1)
        bom, changed = True, True

    if changed:
        write_raw(full, bom, "".join(lines))
    return full, rel


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
    parser.add_argument("--fix", action="store_true")
    args = parser.parse_args()

    config = load_config(args.mod, args.config)
    report = Report("Localization lint")
    exempt = config.get("lint_exempt", [])
    check_bom = not config.get("require_bom")

    for full, rel in list(walk_files(args.mod, (".yml",), "localization")):
        if matches(rel, exempt):
            continue
        if args.fix:
            full, rel = fix_file(full, rel, report)
        check_file(full, rel, check_bom, report)

    sys.exit(report.finish())


if __name__ == "__main__":
    main()
