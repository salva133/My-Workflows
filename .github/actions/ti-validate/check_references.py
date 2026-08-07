"""Cross-reference checks for a Terra Invicta mod.

Records point at each other by dataName as plain strings, so a typo is not a
load error: the game reads the name, finds nothing, and carries on without the
army, the claim or the region. Names the mod's own prefixes mark have to
resolve inside the mod, which is what makes them checkable without a copy of
the vanilla data.

TIMetaTemplate is the second half. A scenario names the record sets it loads,
and each of those sets names its members, so a nation the meta template does
not list is a nation the scenario never sees.

  REF_UNRESOLVED  a prefixed name that no record in the mod defines
  META_UNLISTED   a record no TIMetaTemplate entry of its type lists
  META_TYPE       a meta entry whose templateType is not a template name
  META_AFFIX      a scenario prefix without the matching localization postfix
"""

import argparse
import sys

from tilib import (DEFAULT_IGNORED_REFERENCE_FIELDS, Report, all_data_names,
                   data_names, id_prefixes, load_config, load_templates,
                   walk_strings)


def check_references(templates, prefixes, ignored, report):
    known = all_data_names(templates)

    for template in sorted(templates):
        name = f"{template}.json"
        for record in templates[template]:
            if not isinstance(record, dict):
                continue
            owner = record.get("dataName", "<unnamed>")
            reported = set()
            for field, value in walk_strings(record):
                if field in ignored or field == "dataName":
                    continue
                if value in known or value in reported:
                    continue
                if not any(value.startswith(p) for p in prefixes):
                    continue
                reported.add(value)
                report.error(
                    "REF_UNRESOLVED",
                    f"Record '{owner}' points at '{value}' through {field}, and no "
                    "record in the mod carries that dataName. The game reads the "
                    "name, finds nothing and drops what it was for.",
                    name, 1,
                )


def check_membership(templates, prefixes, report):
    meta = templates.get("TIMetaTemplate")
    if meta is None:
        report.notice(
            "META_UNLISTED",
            "The mod ships no TIMetaTemplate.json, so its records load globally and "
            "the membership check does not apply.",
        )
        return

    listed = {}
    for record in meta:
        if not isinstance(record, dict):
            continue
        template_type = record.get("templateType")
        if not isinstance(template_type, str) or not template_type:
            continue
        if template_type != "TIMetaTemplate" and template_type not in templates:
            report.warn(
                "META_TYPE",
                f"Meta entry '{record.get('dataName', '<unnamed>')}' declares "
                f"templateType '{template_type}', which is not a template the mod "
                "ships. Its members have to come from vanilla.",
                "TIMetaTemplate.json", 1,
            )
        names = record.get("templateNames")
        if isinstance(names, list):
            listed.setdefault(template_type, set()).update(
                n for n in names if isinstance(n, str)
            )

        prefix = record.get("scenarioPrefix")
        postfix = record.get("scenarioLocalizationPostfix")
        if prefix and not postfix:
            report.warn(
                "META_AFFIX",
                f"Scenario '{record.get('dataName', '<unnamed>')}' sets scenarioPrefix "
                f"'{prefix}' but no scenarioLocalizationPostfix, so the game looks its "
                "strings up under names the localization files do not carry.",
                "TIMetaTemplate.json", 1,
            )

    defined = data_names(templates)
    for template in sorted(defined):
        if template == "TIMetaTemplate":
            continue
        members = listed.get(template)
        if members is None:
            report.notice(
                "META_UNLISTED",
                f"No meta entry declares templateType '{template}', so its records "
                "are taken to load globally.",
                f"{template}.json", 1,
            )
            continue
        for record_name in sorted(defined[template] - members):
            report.error(
                "META_UNLISTED",
                f"Record '{record_name}' is defined but no TIMetaTemplate entry of "
                f"type {template} lists it, so no scenario ever loads it.",
                f"{template}.json", 1,
            )

    # A meta entry that lists a prefixed name the mod does not define is caught by
    # REF_UNRESOLVED, which reads templateNames along with every other field.


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mod", default=".")
    parser.add_argument("--config", default=".github/ti-validate.json")
    args = parser.parse_args()

    config = load_config(args.mod, args.config)
    report = Report("Cross-references")

    templates = load_templates(args.mod)
    if not templates:
        report.notice("REF_UNRESOLVED", "The mod ships no readable templates.")
        sys.exit(report.finish())

    prefixes = id_prefixes(config, templates)
    ignored = set(DEFAULT_IGNORED_REFERENCE_FIELDS)
    ignored.update(config.get("ignore_reference_fields", []))

    if prefixes:
        check_references(templates, prefixes, ignored, report)
    else:
        report.notice(
            "REF_UNRESOLVED",
            "No id_prefixes configured and no scenarioPrefix declared, so a name "
            "cannot be told from a vanilla one and the reference check is skipped.",
        )

    check_membership(templates, prefixes, report)

    sys.exit(report.finish())


if __name__ == "__main__":
    main()
