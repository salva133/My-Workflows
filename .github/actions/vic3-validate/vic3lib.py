"""Shared helpers for the Victoria 3 mod validators."""

import json
import os
import re
import sys

SKIP_DIRS = {".git", ".github", ".vic3-vanilla", ".metadata"}

LOC_LINE = re.compile(r'^(\s*)([\w.\-]+):\s*(\d*)\s*"(.*)"\s*$')
LOC_KEY = re.compile(r"^\s*([\w.\-]+):\s*\d*\s*\"")
TOP_LEVEL_KEY = re.compile(r"^\s*((?:TRY_)?(?:REPLACE|INJECT):)?([\w.\-]+)\s*=\s*\{")

ENTRY_MODES = ("REPLACE:", "TRY_REPLACE:", "INJECT:", "TRY_INJECT:")


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


def walk_files(root, suffixes, subdir=""):
    base = os.path.join(root, subdir) if subdir else root
    if not os.path.isdir(base):
        return
    for current, dirs, files in os.walk(base):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for name in sorted(files):
            if name.endswith(suffixes):
                full = os.path.join(current, name)
                yield full, os.path.relpath(full, root).replace(os.sep, "/")


def load_config(mod_root, config_path):
    full = os.path.join(mod_root, config_path)
    if not os.path.isfile(full):
        return {}
    try:
        return json.loads(read_text(full))
    except ValueError as exc:
        print(f"::error file={config_path}::Config is not valid JSON: {exc}")
        sys.exit(1)


def load_replace_paths(mod_root):
    full = os.path.join(mod_root, ".metadata", "metadata.json")
    if not os.path.isfile(full):
        return set()
    data = json.loads(read_text(full))
    paths = data.get("game_custom_data", {}).get("replace_paths", [])
    return {p.strip("/") for p in paths}


def is_replaced(rel_path, replace_paths):
    directory = os.path.dirname(rel_path)
    while directory:
        if directory in replace_paths:
            return True
        directory = os.path.dirname(directory)
    return False


def collect_loc_keys(root):
    """Maps a localization key to a list of (rel_path, line, value)."""
    keys = {}
    for full, rel in walk_files(root, (".yml",), "localization"):
        for number, line in enumerate(read_lines(full), 1):
            match = LOC_LINE.match(line)
            if match:
                keys.setdefault(match.group(2), []).append((rel, number, match.group(4)))
                continue
            key = LOC_KEY.match(line)
            if key:
                keys.setdefault(key.group(1), []).append((rel, number, None))
    return keys


def collect_top_level_keys(root, subdir):
    """Maps a database key to a list of (rel_path, line, entry_mode_prefix)."""
    keys = {}
    for full, rel in walk_files(root, (".txt",), subdir):
        depth = 0
        for number, line in enumerate(read_lines(full), 1):
            stripped = line.split("#")[0]
            if depth == 0:
                match = TOP_LEVEL_KEY.match(stripped)
                if match:
                    keys.setdefault(match.group(2), []).append(
                        (rel, number, match.group(1) or "")
                    )
            depth += stripped.count("{") - stripped.count("}")
            if depth < 0:
                depth = 0
    return keys
