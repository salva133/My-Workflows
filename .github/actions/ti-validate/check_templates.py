"""Template structure checks for a Terra Invicta mod.

Every TIXxxTemplate.json holds an array of records, and the game addresses a
record by its dataName. A record without one is unreachable, and two records
sharing one are a single record with the later one winning.

  JSON_PARSE          the file does not parse
  JSON_SHAPE          the file does not hold an array
  TEMPLATE_EMPTY      the array is empty
  RECORD_SHAPE        an element of the array is not an object
  RECORD_NO_DATANAME  a record carries no usable dataName
  RECORD_DUPLICATE    a dataName is defined twice in the same template
  RECORD_PREFIX       a dataName carries none of the mod's prefixes
  RECORD_FIELD        a record is missing a field every one of its siblings has
  JSON_STRAY          a .json the mod manager parses but no template array

JSON_STRAY is the one that bites hardest. The mod manager walks the whole mod
folder, hands every .json and .jsonc it finds to its reader, and expects an
array of records back. One that holds an object instead — a tool's config, a
schema, anything — stops the load with "MOD MANAGER FAILED TO LOAD JSON" and
the mod does not install at all. Renaming it .jsonc does not help; that is
scanned too.
"""

import argparse
import json
import os
import sys

from tilib import (MODINFO, TEMPLATE_JSON, Report, id_prefixes, load_config,
                   load_templates, read_text, walk_scanned_json)

# Below this many records, "every sibling has it" says more about the sample
# size than about the field.
FIELD_QUORUM = 4


def check_records(templates, prefixes, report):
    for template in sorted(templates):
        records = templates[template]
        name = f"{template}.json"

        if not records:
            report.warn(
                "TEMPLATE_EMPTY",
                "Template holds no records, so the file only costs load time.",
                name, 1,
            )
            continue

        seen = {}
        for index, record in enumerate(records):
            if not isinstance(record, dict):
                report.error(
                    "RECORD_SHAPE",
                    f"Entry {index} is not an object.",
                    name, 1,
                )
                continue

            data_name = record.get("dataName")
            if not isinstance(data_name, str) or not data_name.strip():
                report.error(
                    "RECORD_NO_DATANAME",
                    f"Entry {index} carries no dataName, so nothing can address it.",
                    name, 1,
                )
                continue

            if data_name in seen:
                report.error(
                    "RECORD_DUPLICATE",
                    f"dataName '{data_name}' is also defined by entry {seen[data_name]}. "
                    "One of the two records is dead weight.",
                    name, 1,
                )
            else:
                seen[data_name] = index

            if prefixes and not any(data_name.startswith(p) for p in prefixes):
                report.warn(
                    "RECORD_PREFIX",
                    f"dataName '{data_name}' carries none of the mod's prefixes "
                    f"({', '.join(prefixes)}). Unprefixed names collide with vanilla "
                    "and with other mods.",
                    name, 1,
                )


def check_fields(templates, report):
    """A field every sibling carries and one record does not is usually an omission."""
    for template in sorted(templates):
        records = [r for r in templates[template] if isinstance(r, dict)]
        if len(records) < FIELD_QUORUM:
            continue
        name = f"{template}.json"

        counts = {}
        for record in records:
            for field in record:
                counts[field] = counts.get(field, 0) + 1

        universal = {f for f, c in counts.items() if c == len(records) - 1}
        if not universal:
            continue

        for record in records:
            missing = sorted(universal - set(record))
            if not missing:
                continue
            data_name = record.get("dataName", "<unnamed>")
            report.warn(
                "RECORD_FIELD",
                f"Record '{data_name}' is missing {', '.join(missing)}, which every "
                "other record in the template carries.",
                name, 1,
            )


def check_stray_json(mod_root, listed, report):
    """Holds every .json the mod manager will open to what it can actually read."""
    for full, rel in walk_scanned_json(mod_root):
        if rel == MODINFO or TEMPLATE_JSON.match(rel):
            continue

        try:
            data = json.loads(read_text(full))
        except ValueError as exc:
            report.error(
                "JSON_STRAY",
                f"The mod manager parses every .json under the mod folder, and this "
                f"one does not parse: {exc}. The mod fails to install.",
                rel, 1,
            )
            continue

        if not isinstance(data, list):
            report.error(
                "JSON_STRAY",
                "The mod manager parses every .json under the mod folder and expects "
                "an array of records. This file holds "
                f"{'an object' if isinstance(data, dict) else type(data).__name__}, so "
                "the load stops and the mod does not install. Give the file an "
                "extension the mod manager does not read, or keep it out of the mod "
                "folder — .jsonc is scanned as well.",
                rel, 1,
            )
        elif rel not in listed:
            report.warn(
                "JSON_STRAY",
                "File holds a template array but ModInfo.json does not list it, so "
                "the mod manager parses it and then ignores what is in it.",
                rel, 1,
            )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mod", default=".")
    parser.add_argument("--config", default="")
    args = parser.parse_args()

    config = load_config(args.mod, args.config)
    report = Report("Template structure")

    modinfo_path = os.path.join(args.mod, MODINFO)
    listed = set()
    if os.path.isfile(modinfo_path):
        try:
            entries = json.loads(read_text(modinfo_path)).get("TemplatesToConcatArrays")
            listed = {e for e in entries or [] if isinstance(e, str)}
        except (ValueError, AttributeError):
            pass  # check_modinfo reports a broken ModInfo.json
    check_stray_json(args.mod, listed, report)

    templates = load_templates(args.mod, report)
    if not templates:
        report.warn(
            "TEMPLATE_EMPTY",
            "The mod ships no readable TIXxxTemplate.json file.",
        )
        sys.exit(report.finish())

    prefixes = id_prefixes(config, templates)
    if not prefixes:
        report.notice(
            "RECORD_PREFIX",
            "No id_prefixes configured and no scenarioPrefix declared, so the "
            "dataName prefix check is skipped.",
        )

    check_records(templates, prefixes, report)
    if config.get("check_missing_fields", True):
        check_fields(templates, report)

    sys.exit(report.finish())


if __name__ == "__main__":
    main()
