"""Localization checks for a Terra Invicta mod.

A localization file reads TIXxxTemplate.field.name=text, one line each. The
name part is the record's dataName, except under a scenario, where the game
takes the scenarioPrefix off and puts the scenarioLocalizationPostfix on, so
1898_AFG is addressed as AFG.1898.

  LOC_ENCODING     the file is not valid UTF-8
  LOC_SHAPE        a line does not read key=value
  LOC_KEY_SHAPE    a key does not read TIXxxTemplate.field.name
  LOC_FILE_MISMATCH a key names a template other than the file's own
  LOC_DUPLICATE    a key is defined twice in one file
  LOC_EMPTY        a key carries no text
  LOC_UNKNOWN_NAME a key addresses a record the mod does not define
  LOC_MISSING      a language is missing a key another language carries
  LOC_LANGUAGE     a template is localized in some of the mod's languages only
  LOC_PLACEHOLDER  translations of one key disagree on their {n} placeholders
"""

import argparse
import os
import sys

from tilib import (LOC_KEY, PLACEHOLDER, Report, data_names, load_config,
                   load_templates, localization_candidates, localization_files,
                   parse_localization, scenario_affixes)


def check_encoding(mod_root, files, report):
    """Reports files that are not valid UTF-8.

    A German localization saved as cp1252 reaches the game as mojibake rather
    than as an error, so the umlauts turn to noise on screen.
    """
    readable = []
    for template, language, name in files:
        with open(os.path.join(mod_root, name), "rb") as fh:
            raw = fh.read()
        try:
            raw.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            report.error(
                "LOC_ENCODING",
                f"File is not valid UTF-8 (byte {exc.start}). Save it as UTF-8, or "
                "the accented characters reach the game as mojibake.",
                name, 1,
            )
            continue
        readable.append((template, language, name))
    return readable


def collect(mod_root, files, report):
    """Maps (template, language) to {key: (line, value)}, reporting shape faults."""
    collected = {}
    for template, language, name in files:
        entries = parse_localization(os.path.join(mod_root, name), name, report)
        keys = {}
        for number, key, value in entries:
            match = LOC_KEY.match(key)
            if not match:
                report.error(
                    "LOC_KEY_SHAPE",
                    f"Key '{key}' does not read TIXxxTemplate.field.name.",
                    name, number,
                )
                continue
            if match.group(1) != template:
                report.warn(
                    "LOC_FILE_MISMATCH",
                    f"Key names {match.group(1)} but sits in {name}. Terra Invicta "
                    "expects a template's strings in that template's own file.",
                    name, number,
                )
            if key in keys:
                first_line, first_value = keys[key]
                message = (f"Key '{key}' is also defined at line {first_line}. "
                           "Only one of the two reaches the game.")
                if first_value == value:
                    report.warn("LOC_DUPLICATE", message + " Both carry the same text.",
                                name, number)
                else:
                    report.error("LOC_DUPLICATE", message + " The two disagree.",
                                 name, number)
                continue
            if not value.strip():
                report.warn(
                    "LOC_EMPTY",
                    f"Key '{key}' carries no text, so the game shows an empty string.",
                    name, number,
                )
            keys[key] = (number, value)
        collected[(template, language)] = (name, keys)
    return collected


def check_names(collected, templates, report):
    names = data_names(templates)
    affixes = scenario_affixes(templates)

    for (template, _), (file_name, keys) in sorted(collected.items()):
        defined = names.get(template)
        if defined is None:
            report.notice(
                "LOC_UNKNOWN_NAME",
                f"{file_name} localizes {template}, which the mod does not ship, so "
                "its keys are taken to be addressing vanilla records and left alone.",
                file_name, 1,
            )
            continue
        for key, (number, _) in sorted(keys.items(), key=lambda item: item[1][0]):
            match = LOC_KEY.match(key)
            if not match:
                continue
            if not (localization_candidates(match.group(3), affixes) & defined):
                report.error(
                    "LOC_UNKNOWN_NAME",
                    f"Key '{key}' addresses a record {template}.json does not define. "
                    "The game falls back to showing the raw key.",
                    file_name, number,
                )


def check_parity(collected, reference, report):
    """Holds every language to the same key set, template by template."""
    languages = sorted({language for _, language in collected})
    if len(languages) < 2:
        return

    templates = sorted({template for template, _ in collected})
    for template in templates:
        present = [lang for lang in languages if (template, lang) in collected]
        for language in languages:
            if language not in present:
                report.warn(
                    "LOC_LANGUAGE",
                    f"{template} is localized in {', '.join(present)} but not in "
                    f"{language}, which the mod ships for other templates.",
                    f"{template}.{present[0]}", 1,
                )

        base = reference if (template, reference) in collected else present[0]
        base_name, base_keys = collected[(template, base)]

        for language in present:
            if language == base:
                continue
            file_name, keys = collected[(template, language)]
            for key, (number, _) in sorted(base_keys.items(), key=lambda i: i[1][0]):
                if key not in keys:
                    report.warn(
                        "LOC_MISSING",
                        f"Key '{key}' is defined in {base_name} but not here, so the "
                        f"{language} game shows the raw key.",
                        file_name, 1,
                    )
            for key, (number, _) in sorted(keys.items(), key=lambda i: i[1][0]):
                if key not in base_keys:
                    report.warn(
                        "LOC_MISSING",
                        f"Key '{key}' is defined here but not in {base_name}, the "
                        "reference language.",
                        file_name, number,
                    )


def check_placeholders(collected, reference, report):
    """The {n} tokens are filled by the game, so every translation needs the same ones."""
    by_key = {}
    for (template, language), (file_name, keys) in collected.items():
        for key, (number, value) in keys.items():
            by_key.setdefault((template, key), []).append(
                (language, file_name, number, set(PLACEHOLDER.findall(value)))
            )

    for (_, key), entries in sorted(by_key.items()):
        if len(entries) < 2:
            continue
        base = next((e for e in entries if e[0] == reference), entries[0])
        for language, file_name, number, tokens in entries:
            if language == base[0]:
                continue
            if tokens != base[3]:
                missing = ", ".join(sorted(base[3] - tokens)) or "none"
                extra = ", ".join(sorted(tokens - base[3])) or "none"
                report.error(
                    "LOC_PLACEHOLDER",
                    f"Key '{key}' carries different placeholders than in {base[1]}. "
                    f"Missing: {missing}. Unexpected: {extra}. The game fills them by "
                    "position, so a translation has to carry the same set.",
                    file_name, number,
                )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mod", default=".")
    parser.add_argument("--config", default=".github/ti-validate.jsonc")
    args = parser.parse_args()

    config = load_config(args.mod, args.config)
    report = Report("Localization")

    files = list(localization_files(args.mod))
    if not files:
        report.notice("LOC_SHAPE", "The mod ships no localization files.")
        sys.exit(report.finish())

    files = check_encoding(args.mod, files, report)
    templates = load_templates(args.mod)
    collected = collect(args.mod, files, report)
    reference = config.get("reference_language", "en")

    check_names(collected, templates, report)
    check_parity(collected, reference, report)
    check_placeholders(collected, reference, report)

    sys.exit(report.finish())


if __name__ == "__main__":
    main()
