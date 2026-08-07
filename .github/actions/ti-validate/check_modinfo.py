import argparse
import json
import os
import sys

from tilib import (GAME_VERSION, MODINFO, SEMVER, Report, load_config,
                   localization_files, read_text, template_files)

REQUIRED = ("Title", "Author", "Version", "GameVersion", "TemplatesToConcatArrays")


def check_fields(modinfo, report):
    for field in REQUIRED:
        value = modinfo.get(field)
        if value is None or value == "" or value == []:
            report.error(
                "MODINFO_FIELD",
                f"Field '{field}' is missing or empty. The mod menu reads it.",
                MODINFO, 1,
            )

    version = modinfo.get("Version")
    if isinstance(version, str) and version and not SEMVER.match(version):
        report.error(
            "MODINFO_VERSION",
            f"Version '{version}' does not read X.Y.Z, so releases cannot be "
            "ordered by it.",
            MODINFO, 1,
        )

    game_version = modinfo.get("GameVersion")
    if isinstance(game_version, str) and game_version and not GAME_VERSION.match(game_version):
        report.error(
            "MODINFO_GAME_VERSION",
            f"GameVersion '{game_version}' is not a dotted number such as 1.0.26.",
            MODINFO, 1,
        )

    if not modinfo.get("Description"):
        report.warn(
            "MODINFO_FIELD",
            "Description is empty, so the mod menu shows the mod with no text.",
            MODINFO, 1,
        )


def check_listing(mod_root, modinfo, report):
    listed = modinfo.get("TemplatesToConcatArrays")
    if not isinstance(listed, list):
        report.error(
            "MODINFO_FIELD",
            "TemplatesToConcatArrays is not an array.",
            MODINFO, 1,
        )
        return

    seen = set()
    for entry in listed:
        if not isinstance(entry, str):
            report.error(
                "MODINFO_FIELD",
                f"TemplatesToConcatArrays holds {entry!r}, which is not a file name.",
                MODINFO, 1,
            )
            continue
        if entry in seen:
            report.error(
                "MODINFO_DUPLICATE",
                f"'{entry}' is listed twice. The game concatenates the file twice, "
                "so every record in it is defined twice.",
                MODINFO, 1,
            )
        seen.add(entry)
        if not os.path.isfile(os.path.join(mod_root, entry)):
            report.error(
                "MODINFO_MISSING_FILE",
                f"'{entry}' is listed but not present in the mod.",
                MODINFO, 1,
            )

    on_disk = {name for _, name in template_files(mod_root)}
    on_disk |= {name for _, _, name in localization_files(mod_root)}
    for name in sorted(on_disk - seen):
        report.error(
            "MODINFO_UNLISTED",
            f"'{name}' is not listed in TemplatesToConcatArrays, so the game "
            "never reads it and everything it defines is silently absent.",
            name, 1,
        )


def check_readme(mod_root, modinfo, report):
    version = modinfo.get("Version")
    if not isinstance(version, str) or not version:
        return
    readme = os.path.join(mod_root, "README.md")
    if not os.path.isfile(readme):
        return
    if version not in read_text(readme):
        report.warn(
            "README_VERSION",
            f"README.md does not mention version {version}, so it is describing "
            "a different release than the one ModInfo.json ships.",
            "README.md", 1,
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mod", default=".")
    parser.add_argument("--config", default="")
    args = parser.parse_args()

    load_config(args.mod, args.config)
    report = Report("Mod metadata")

    full = os.path.join(args.mod, MODINFO)
    if not os.path.isfile(full):
        report.error(
            "MODINFO_MISSING",
            "The mod ships no ModInfo.json, so the game does not list it at all.",
            MODINFO, 1,
        )
        sys.exit(report.finish())

    try:
        modinfo = json.loads(read_text(full))
    except ValueError as exc:
        report.error("MODINFO_JSON", f"ModInfo.json is not valid JSON: {exc}", MODINFO, 1)
        sys.exit(report.finish())

    if not isinstance(modinfo, dict):
        report.error("MODINFO_JSON", "ModInfo.json does not hold an object.", MODINFO, 1)
        sys.exit(report.finish())

    check_fields(modinfo, report)
    check_listing(args.mod, modinfo, report)
    check_readme(args.mod, modinfo, report)

    sys.exit(report.finish())


if __name__ == "__main__":
    main()
