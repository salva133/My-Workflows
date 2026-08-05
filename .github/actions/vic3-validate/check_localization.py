"""Localization sweeps for a Victoria 3 mod.

Checks, in order:
  LOC_SHAPE          every value line reads key: "value" with a closing quote
  LOC_INNER_QUOTE    no value contains a quotation mark of its own, where the
                     mod's config asks for it
  LOC_DUPLICATE      no key is defined twice inside the mod
  LOC_VANILLA_KEY    a key vanilla also defines lives in the mod's override file
  LOC_MISSING_KEY    every key an event names is defined by the mod or by vanilla

The last two need a vanilla checkout and are skipped without one.
"""

import argparse
import os
import re
import sys

from vic3lib import (LOC_LINE, Report, collect_loc_keys, load_config,
                     read_lines, walk_files)

HEAD_FIELD = re.compile(r'^\s*(title|desc|flavor)\s*=\s*"?([\w.\-]+)"?\s*$')
OPTION_NAME = re.compile(r'^\s*name\s*=\s*"?([\w.\-]+)"?\s*$')
BLOCK_OPEN = re.compile(r"^\s*([\w.\-]+)\s*=\s*\{")


def check_lines(root, report, forbid_inner_quotes):
    for full, rel in walk_files(root, (".yml",), "localization"):
        for number, line in enumerate(read_lines(full), 1):
            text = line.strip()
            if not text or text.startswith("#") or text.startswith("l_"):
                continue
            match = LOC_LINE.match(line)
            if not match:
                report.error(
                    "LOC_SHAPE",
                    'Line does not read key: "value" with a closing quote.',
                    rel, number,
                )
                continue
            if forbid_inner_quotes and '"' in match.group(4):
                report.error(
                    "LOC_INNER_QUOTE",
                    "Value contains a quotation mark, which reopens the string. "
                    "Set direct speech in single quotes.",
                    rel, number,
                )


def check_duplicates(mod_keys, report):
    for key, entries in sorted(mod_keys.items()):
        if len(entries) < 2:
            continue
        first = entries[0]
        others = ", ".join(f"{rel}:{line}" for rel, line, _ in entries[1:])
        values = {value for _, _, value in entries}
        message = (f"Key '{key}' is also defined at {others}. "
                   "The first definition in load order wins; the rest are never read.")
        if len(values) == 1:
            report.warn("LOC_DUPLICATE", message + " All copies carry the same value.",
                        first[0], first[1])
        else:
            report.error("LOC_DUPLICATE", message + " The copies disagree.",
                         first[0], first[1])


def check_vanilla_keys(mod_keys, vanilla_keys, override_file, report):
    for key, entries in sorted(mod_keys.items()):
        if key not in vanilla_keys:
            continue
        vanilla_value = vanilla_keys[key][0][2]
        for rel, line, value in entries:
            if rel == override_file:
                continue
            message = (
                f"Key '{key}' is also defined by vanilla. It only overrides vanilla "
                f"from {override_file}, which sorts ahead of the vanilla file."
            )
            if value is not None and value == vanilla_value:
                report.warn("LOC_VANILLA_KEY",
                            message + " Its value matches vanilla's, so nothing changes on screen.",
                            rel, line)
            else:
                report.error("LOC_VANILLA_KEY", message, rel, line)


def collect_event_keys(root):
    """Yields (rel_path, line, key) for every localization key an event names."""
    for full, rel in walk_files(root, (".txt",), "events"):
        stack = []
        for number, line in enumerate(read_lines(full), 1):
            stripped = line.split("#")[0]
            head = HEAD_FIELD.match(stripped)
            if head:
                yield rel, number, head.group(2)
            elif stack and stack[-1] == "option":
                name = OPTION_NAME.match(stripped)
                if name:
                    yield rel, number, name.group(1)
            opener = BLOCK_OPEN.match(stripped)
            if opener:
                stack.append(opener.group(1))
            for _ in range(stripped.count("}")):
                if stack:
                    stack.pop()


def check_event_keys(root, mod_keys, vanilla_keys, report):
    for rel, line, key in collect_event_keys(root):
        if key in mod_keys or key in vanilla_keys:
            continue
        report.error(
            "LOC_MISSING_KEY",
            f"Event names localization key '{key}', which neither the mod nor vanilla defines.",
            rel, line,
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mod", default=".")
    parser.add_argument("--vanilla", default="")
    parser.add_argument("--config", default=".github/vic3-validate.json")
    args = parser.parse_args()

    config = load_config(args.mod, args.config)
    report = Report("Localization sweeps")

    check_lines(args.mod, report, config.get("forbid_inner_quotes", False))
    mod_keys = collect_loc_keys(args.mod)
    check_duplicates(mod_keys, report)

    if args.vanilla and os.path.isdir(args.vanilla):
        vanilla_keys = collect_loc_keys(args.vanilla)
        override_file = config.get("vanilla_override_localization_file")
        if override_file:
            check_vanilla_keys(mod_keys, vanilla_keys, override_file, report)
        else:
            print("::notice::No vanilla_override_localization_file configured, "
                  "so the vanilla key check is skipped.")
        check_event_keys(args.mod, mod_keys, vanilla_keys, report)
    else:
        print("::notice::No vanilla checkout available, so the vanilla-dependent "
              "localization checks are skipped.")

    sys.exit(report.finish())


if __name__ == "__main__":
    main()
