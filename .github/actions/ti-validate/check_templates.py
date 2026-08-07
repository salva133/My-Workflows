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
"""

import argparse
import sys

from tilib import (Report, id_prefixes, load_config, load_templates)

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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mod", default=".")
    parser.add_argument("--config", default=".github/ti-validate.jsonc")
    args = parser.parse_args()

    config = load_config(args.mod, args.config)
    report = Report("Template structure")

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
