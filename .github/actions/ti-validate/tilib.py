import json
import os
import re
import sys

TEMPLATE_JSON = re.compile(r"^(TI[A-Za-z0-9]*Template)\.json$")
SCANNED_JSON = re.compile(r"\.jsonc?$", re.IGNORECASE)
SKIP_DIRS = {".git"}
LOC_FILE = re.compile(r"^(TI[A-Za-z0-9]*Template)\.(?!json$)([A-Za-z]{2,5})$")
LOC_LINE = re.compile(r"^([A-Za-z0-9_.\-]+)=(.*)$")
LOC_KEY = re.compile(r"^(TI[A-Za-z0-9]*Template)\.([A-Za-z0-9_]+)\.(.+)$")
PLACEHOLDER = re.compile(r"\{\d+\}")
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
GAME_VERSION = re.compile(r"^\d+(\.\d+)*$")

MODINFO = "ModInfo.json"

DEFAULT_IGNORED_REFERENCE_FIELDS = (
    "friendlyName",
    "scenarioPrefix",
    "scenarioLocalizationPostfix",
)


class Report:

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
    full = os.path.join(mod_root, MODINFO)
    if not os.path.isfile(full):
        return None
    try:
        return json.loads(read_text(full))
    except ValueError:
        return None


def id_prefixes(config, templates):
    declared = {prefix for prefix, _ in scenario_affixes(templates) if prefix}
    return sorted(set(config.get("id_prefixes") or ()) | declared)


def template_files(mod_root):
    for name in sorted(os.listdir(mod_root)):
        match = TEMPLATE_JSON.match(name)
        if match and os.path.isfile(os.path.join(mod_root, name)):
            yield match.group(1), name


def localization_files(mod_root):
    for name in sorted(os.listdir(mod_root)):
        match = LOC_FILE.match(name)
        if match and os.path.isfile(os.path.join(mod_root, name)):
            yield match.group(1), match.group(2), name


def load_templates(mod_root, report=None):
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
    return set().union(*data_names(templates).values()) if templates else set()


def scenario_affixes(templates):
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
    candidates = {name}
    for prefix, postfix in affixes:
        if postfix and name.endswith(postfix):
            candidates.add(prefix + name[:-len(postfix)])
        elif not postfix:
            candidates.add(prefix + name)
    return candidates


def parse_localization(path, file_name, report):
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
    if isinstance(value, str):
        yield field, value
    elif isinstance(value, list):
        for item in value:
            yield from walk_strings(item, field)
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from walk_strings(item, key)
