"""Localization sweeps for a Victoria 3 mod.

Checks, in order:
  LOC_SHAPE          every value line reads key: "value" with a closing quote
  LOC_INNER_QUOTE    no value contains a quotation mark of its own, where the
                     mod's config asks for it
  LOC_DUPLICATE      no key is defined twice inside one language of the mod
  LOC_VANILLA_KEY    a key vanilla also defines lives in the mod's override file
                     for that language
  LOC_MISSING_KEY    every key an event names is defined by the mod or by vanilla
  LOC_TRANSLATION_GAP every key of an english file is defined in each other
                     language the mod ships, and no language defines a key the
                     english does not

Each language is a database of its own, so a key defined once per language is
a translation rather than a duplicate. The override file configured for english
stands for the same path in every other language.

LOC_VANILLA_KEY and LOC_MISSING_KEY need a vanilla checkout and are skipped
without one.
"""

import argparse
import os
import re
import sys

from vic3lib import (LOC_LINE, Report, collect_loc_keys,
                     collect_loc_keys_by_language, load_config, read_lines,
                     walk_files)

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


def override_for(override_file, language):
    """The english override path as it reads for another language."""
    parts = override_file.split("/")
    parts = [language if part == "english" else part for part in parts[:-1]] + [
        re.sub(r"_l_english\.yml$", f"_l_{language}.yml", parts[-1])]
    return "/".join(parts)


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


def check_vanilla_keys(mod_languages, vanilla_languages, override_file, report):
    vanilla_all = {}
    for keys in vanilla_languages.values():
        for key, entries in keys.items():
            vanilla_all.setdefault(key, entries)
    for language, keys in sorted(mod_languages.items(), key=lambda item: item[0] or ""):
        if not language:
            continue
        own = vanilla_languages.get(language, {})
        for key, entries in sorted(keys.items()):
            if key not in vanilla_all:
                continue
            vanilla_value = (own.get(key) or vanilla_all[key])[0][2]
            target = override_for(override_file, language)
            for rel, line, value in entries:
                if rel == target:
                    continue
                message = (
                    f"Key '{key}' is also defined by vanilla. It only overrides vanilla "
                    f"from {target}, which sorts ahead of the vanilla file."
                )
                if value is not None and value == vanilla_value:
                    report.warn("LOC_VANILLA_KEY",
                                message + " Its value matches vanilla's, so nothing changes on screen.",
                                rel, line)
                else:
                    report.error("LOC_VANILLA_KEY", message, rel, line)


def check_translation_gaps(mod_languages, report, override_file=None):
    english = mod_languages.get("english", {})
    if not english:
        return
    if override_file:
        english = {key: entries for key, entries in english.items()
                   if entries[0][0] != override_file}
    for language, keys in sorted(mod_languages.items(), key=lambda item: item[0] or ""):
        if language in (None, "english") or not keys:
            continue
        gaps = {}
        for key, entries in english.items():
            if key not in keys:
                gaps.setdefault(entries[0][0], []).append(key)
        for rel, missing in sorted(gaps.items()):
            shown = ", ".join(missing[:5]) + (", ..." if len(missing) > 5 else "")
            report.warn(
                "LOC_TRANSLATION_GAP",
                f"{len(missing)} key(s) of this file have no {language} translation, "
                f"so a {language} player sees the raw key: {shown}",
                rel, 1,
            )
        extra = {}
        for key, entries in keys.items():
            if key not in english and not (
                    override_file and entries[0][0] == override_for(override_file, language)):
                extra.setdefault(entries[0][0], []).append(key)
        for rel, stale in sorted(extra.items()):
            shown = ", ".join(stale[:5]) + (", ..." if len(stale) > 5 else "")
            report.warn(
                "LOC_TRANSLATION_GAP",
                f"{len(stale)} key(s) here are defined in {language} but not in english, "
                f"so they are left over from a key the english renamed or dropped: {shown}",
                rel, 1,
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
    mod_languages = collect_loc_keys_by_language(args.mod)
    for language_keys in mod_languages.values():
        check_duplicates(language_keys, report)
    check_translation_gaps(mod_languages, report,
                           config.get("vanilla_override_localization_file"))
    mod_keys = collect_loc_keys(args.mod)

    if args.vanilla and os.path.isdir(args.vanilla):
        vanilla_keys = collect_loc_keys(args.vanilla)
        override_file = config.get("vanilla_override_localization_file")
        if override_file:
            check_vanilla_keys(mod_languages, collect_loc_keys_by_language(args.vanilla),
                               override_file, report)
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
