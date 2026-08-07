"""Shared helpers for the Terra Invicta mod validators.

A Terra Invicta mod is a flat folder: ModInfo.json names the template files,
each TIXxxTemplate.json holds an array of records keyed by dataName, and each
TIXxxTemplate.<lang> holds key=value localization lines. Everything the
validators need is read through this module so the checks agree on what a
template, a record and a localization key are.
"""

import json
import os
import re
import sys

TEMPLATE_JSON = re.compile(r"^(TI[A-Za-z0-9]*Template)\.json$")
# Terra Invicta's mod manager walks the whole mod folder and hands every file
# whose name ends this way to its JSON reader, wherever it sits.
SCANNED_JSON = re.compile(r"\.jsonc?$", re.IGNORECASE)
SKIP_DIRS = {".git"}
# The language part is anything but json, which is the template itself rather
# than a translation of it.
LOC_FILE = re.compile(r"^(TI[A-Za-z0-9]*Template)\.(?!json$)([A-Za-z]{2,5})$")
LOC_LINE = re.compile(r"^([A-Za-z0-9_.\-]+)=(.*)$")
LOC_KEY = re.compile(r"^(TI[A-Za-z0-9]*Template)\.([A-Za-z0-9_]+)\.(.+)$")
PLACEHOLDER = re.compile(r"\{\d+\}")
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
GAME_VERSION = re.compile(r"^\d+(\.\d+)*$")

MODINFO = "ModInfo.json"

# Fields whose string values look like identifiers but never point at another
# record. friendlyName is a display alias, and the two scenario fields carry
# the prefix itself rather than something the prefix is part of.
DEFAULT_IGNORED_REFERENCE_FIELDS = (
    "friendlyName",
    "scenarioPrefix",
    "scenarioLocalizationPostfix",
)


class Report:
    """Collects findings and prints them as GitHub Actions annotations."""

    def __init__(self, name):
        self.name = name
        self.errors = []
        self.warnings = []
        self.notices = []

    def _emit(self, level, code, message, path=None, line=None):
        loc = ""
        if path:
            loc = f" file={path}"
            if line:
                loc += f",line={line}"
        print(f"::{level}{loc},title={code}::{message}")

    def error(self, code, message, path=None, line=None):
        self.errors.append((code, message, path, line))
        self._emit("error", code, message, path, line)

    def warn(self, code, message, path=None, line=None):
        self.warnings.append((code, message, path, line))
        self._emit("warning", code, message, path, line)

    def notice(self, code, message, path=None, line=None):
        self.notices.append((code, message, path, line))
        self._emit("notice", code, message, path, line)

    def finish(self):
        print()
        print(f"{self.name}: {len(self.errors)} error(s), "
              f"{len(self.warnings)} warning(s), {len(self.notices)} notice(s)")
        summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary:
            with open(summary, "a", encoding="utf-8") as fh:
                fh.write(f"### {self.name}\n\n")
                if not self.errors and not self.warnings:
                    fh.write("No findings.\n\n")
                for code, message, path, line in self.errors + self.warnings:
                    where = f"`{path}:{line}` " if path else ""
                    fh.write(f"- **{code}** {where}{message}\n")
                fh.write("\n")
        return 1 if self.errors else 0


def read_text(path):
    with open(path, encoding="utf-8-sig", errors="replace") as fh:
        return fh.read()


def read_lines(path):
    return read_text(path).splitlines()


def walk_scanned_json(mod_root):
    """Yields (full, rel) for every file the game's mod manager parses as JSON.

    Recursive, because the mod manager is: a file under .github counts just as
    much as one beside ModInfo.json.
    """
    for current, dirs, files in os.walk(mod_root):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for name in sorted(files):
            if SCANNED_JSON.search(name):
                full = os.path.join(current, name)
                yield full, os.path.relpath(full, mod_root).replace(os.sep, "/")


def load_config(mod_root, config_path):
    if not config_path:
        return {}
    full = config_path if os.path.isabs(config_path) else os.path.join(mod_root, config_path)
    if not os.path.isfile(full):
        print(f"::notice::No validator config at {config_path}, so its defaults apply.")
        return {}
    try:
        return json.loads(read_text(full))
    except ValueError as exc:
        print(f"::error file={config_path}::Config is not valid JSON: {exc}")
        sys.exit(1)


def load_modinfo(mod_root):
    """Returns the parsed ModInfo.json, or None when it is missing or broken."""
    full = os.path.join(mod_root, MODINFO)
    if not os.path.isfile(full):
        return None
    try:
        return json.loads(read_text(full))
    except ValueError:
        return None


def id_prefixes(config, templates):
    """The prefixes the mod's own dataNames carry.

    Configured prefixes win. Without any, the scenarioPrefix values declared in
    TIMetaTemplate.json are the next best thing, and a mod that declares
    neither is simply not held to the prefix-dependent checks.
    """
    configured = config.get("id_prefixes")
    if configured:
        return sorted(set(configured))
    return sorted({prefix for prefix, _ in scenario_affixes(templates) if prefix})


def template_files(mod_root):
    """Yields (template_name, file_name) for every TIXxxTemplate.json present."""
    for name in sorted(os.listdir(mod_root)):
        match = TEMPLATE_JSON.match(name)
        if match and os.path.isfile(os.path.join(mod_root, name)):
            yield match.group(1), name


def localization_files(mod_root):
    """Yields (template_name, language, file_name) for every localization file."""
    for name in sorted(os.listdir(mod_root)):
        match = LOC_FILE.match(name)
        if match and os.path.isfile(os.path.join(mod_root, name)):
            yield match.group(1), match.group(2), name


def load_templates(mod_root, report=None):
    """Maps a template name to its list of records.

    A file that does not parse, or that does not hold an array, is reported
    and left out, so the later checks work on what is readable.
    """
    templates = {}
    for template, name in template_files(mod_root):
        try:
            data = json.loads(read_text(os.path.join(mod_root, name)))
        except ValueError as exc:
            if report:
                report.error("JSON_PARSE", f"File is not valid JSON: {exc}", name, 1)
            continue
        if not isinstance(data, list):
            if report:
                report.error(
                    "JSON_SHAPE",
                    "Top level is not an array. Terra Invicta concatenates template "
                    "arrays, so the file has to hold one.",
                    name, 1,
                )
            continue
        templates[template] = data
    return templates


def data_names(templates):
    """Maps a template name to the set of dataNames it defines."""
    names = {}
    for template, records in templates.items():
        found = set()
        for record in records:
            if isinstance(record, dict):
                value = record.get("dataName")
                if isinstance(value, str) and value:
                    found.add(value)
        names[template] = found
    return names


def all_data_names(templates):
    """Every dataName the mod defines, across all of its templates."""
    return set().union(*data_names(templates).values()) if templates else set()


def scenario_affixes(templates):
    """The (prefix, postfix) pairs the scenarios rename records by.

    A scenario declares scenarioPrefix and scenarioLocalizationPostfix, and the
    game looks a record's strings up under the dataName with the prefix taken
    off and the postfix put on: 1898_AFG is localized as AFG.1898.
    """
    pairs = set()
    for record in templates.get("TIMetaTemplate", []):
        if not isinstance(record, dict):
            continue
        prefix = record.get("scenarioPrefix") or ""
        postfix = record.get("scenarioLocalizationPostfix") or ""
        if prefix or postfix:
            pairs.add((prefix, postfix))
    return pairs


def localization_candidates(name, affixes):
    """Every dataName a localization key's name part could be addressing."""
    candidates = {name}
    for prefix, postfix in affixes:
        if postfix and name.endswith(postfix):
            candidates.add(prefix + name[:-len(postfix)])
        elif not postfix:
            candidates.add(prefix + name)
    return candidates


def parse_localization(path, file_name, report):
    """Reads a localization file into [(line_number, key, value)].

    Blank lines and // comments are skipped. Anything else has to read
    key=value, and a line that does not is reported and dropped.
    """
    entries = []
    for number, line in enumerate(read_lines(path), 1):
        text = line.strip()
        if not text or text.startswith("//"):
            continue
        match = LOC_LINE.match(text)
        if not match:
            report.error(
                "LOC_SHAPE",
                "Line does not read key=value. The game skips the line and shows "
                "the raw key in its place.",
                file_name, number,
            )
            continue
        entries.append((number, match.group(1), match.group(2)))
    return entries


def walk_strings(value, field=""):
    """Yields (field_name, string) for every string inside a record.

    The field name is the key the string sits under, with list nesting seen
    through, so a value in "templateNames": [...] is reported as templateNames.
    """
    if isinstance(value, str):
        yield field, value
    elif isinstance(value, list):
        for item in value:
            yield from walk_strings(item, field)
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from walk_strings(item, key)
