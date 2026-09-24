"""Syntax lint for the script files of a Victoria 3 mod.

A script file the parser cannot read is not refused at load. Jomini logs the
first token it trips over to error.log and carries on with whatever it made of
the rest, so a lost brace swallows every block after it without a word on
screen. These checks read the files the way the parser does and say where.

  SCRIPT_BRACE      a closing brace with nothing open, or a block still open at
                    the end of the file
  SCRIPT_STRING     a quoted string that never closes
  SCRIPT_NEWLINE    a quoted string running over a line break in a .txt file,
                    which is legal but usually a quote left open. GUI files
                    are spared, since they wrap data-binding expressions so
  SCRIPT_OPERATOR   an operator Jomini does not know, such as =< or =>, or one
                    with no value after it
  SCRIPT_INDENT     indentation in the other style than the one the config
                    asks for through lint_indent (tab or space)

Files matched by lint_exempt, and the vendored monoliths, are skipped.
"""

import argparse
import fnmatch
import sys

from vic3lib import Report, load_config, read_text, walk_files

SCRIPT_DIRS = ("common", "events", "gui", "map_data")
SUFFIXES = (".txt", ".gui")
OPERATORS = {"=", "==", "!=", "<", "<=", ">", ">=", "?="}
OPERATOR_CHARS = "=<>!?"
WORD_STOP = set(OPERATOR_CHARS) | set('{}#"')


def matches(rel, patterns):
    return any(fnmatch.fnmatch(rel, p) for p in patterns)


def tokenize(text, rel, report):
    """Yields (kind, value, line) with kind one of {, }, op, word, abort."""
    index, line, size = 0, 1, len(text)
    while index < size:
        char = text[index]
        if char == "\n":
            line += 1
            index += 1
        elif char.isspace():
            index += 1
        elif char == "#":
            end = text.find("\n", index)
            index = size if end < 0 else end
        elif char == '"':
            start_line, cursor = line, index + 1
            while cursor < size and text[cursor] != '"':
                if text[cursor] == "\\":
                    cursor += 1
                elif text[cursor] == "\n":
                    line += 1
                cursor += 1
            if cursor >= size:
                report.error(
                    "SCRIPT_STRING",
                    "Quoted string never closes. The parser reads the rest of the "
                    "file as its content.",
                    rel, start_line,
                )
                yield "abort", None, start_line
                return
            if line != start_line and rel.endswith(".txt"):
                report.warn(
                    "SCRIPT_NEWLINE",
                    f"Quoted string runs on to line {line}. A quote is most likely "
                    "left open here.",
                    rel, start_line,
                )
            yield "word", text[index:cursor + 1], start_line
            index = cursor + 1
        elif char in "{}":
            yield char, char, line
            index += 1
        elif char in OPERATOR_CHARS:
            cursor = index
            while cursor < size and text[cursor] in OPERATOR_CHARS:
                cursor += 1
            yield "op", text[index:cursor], line
            index = cursor
        elif text.startswith("@[", index):
            end = text.find("]", index)
            end = size if end < 0 else end + 1
            yield "word", text[index:end], line
            line += text.count("\n", index, end)
            index = end
        else:
            cursor = index
            while (cursor < size and not text[cursor].isspace()
                   and text[cursor] not in WORD_STOP):
                cursor += 1
            yield "word", text[index:cursor], line
            index = cursor


def check_structure(text, rel, report):
    stack, pending = [], None
    for kind, value, line in tokenize(text, rel, report):
        if kind == "abort":
            return
        if pending and kind in ("}", "op"):
            report.error(
                "SCRIPT_OPERATOR",
                f"'{pending[0]}' carries no value on its right-hand side.",
                rel, pending[1],
            )
        pending = None

        if kind == "{":
            stack.append(line)
        elif kind == "}":
            if stack:
                stack.pop()
            else:
                report.error(
                    "SCRIPT_BRACE",
                    "Closing brace with no block open. Everything after it is read "
                    "at the top level of the file.",
                    rel, line,
                )
        elif kind == "op":
            if value not in OPERATORS:
                report.error(
                    "SCRIPT_OPERATOR",
                    f"'{value}' is no operator Jomini knows. It reads "
                    f"{', '.join(sorted(OPERATORS))}.",
                    rel, line,
                )
            pending = (value, line)

    if pending:
        report.error(
            "SCRIPT_OPERATOR",
            f"'{pending[0]}' carries no value on its right-hand side.",
            rel, pending[1],
        )
    for line in stack:
        report.error(
            "SCRIPT_BRACE",
            "Block opened here is never closed. The parser folds every block after "
            "it into this one.",
            rel, line,
        )


def check_indent(text, rel, style, report):
    wrong = " " if style == "tab" else "\t"
    offenders = []
    for number, line in enumerate(text.splitlines(), 1):
        stripped = line.lstrip(" \t")
        if stripped and wrong in line[:len(line) - len(stripped)]:
            offenders.append(number)
    if offenders:
        report.warn(
            "SCRIPT_INDENT",
            f"{len(offenders)} line(s) indent with {'spaces' if style == 'tab' else 'tabs'}, "
            f"where lint_indent asks for {style}s. The first is flagged here.",
            rel, offenders[0],
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mod", default=".")
    parser.add_argument("--config", default=".github/vic3-validate.json")
    args = parser.parse_args()

    config = load_config(args.mod, args.config)
    report = Report("Script lint")

    exempt = list(config.get("lint_exempt", []))
    exempt += list(config.get("vendored_monoliths", {}))
    style = config.get("lint_indent", "")
    if style not in ("", "tab", "space"):
        print(f"::error file={args.config}::lint_indent reads '{style}', "
              "where it takes tab or space.")
        sys.exit(1)

    for directory in SCRIPT_DIRS:
        for full, rel in walk_files(args.mod, SUFFIXES, directory):
            if matches(rel, exempt):
                continue
            text = read_text(full)
            check_structure(text, rel, report)
            if style:
                check_indent(text, rel, style, report)

    sys.exit(report.finish())


if __name__ == "__main__":
    main()
