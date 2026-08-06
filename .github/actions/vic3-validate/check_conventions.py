"""Repository conventions for a Victoria 3 mod.

Each check is opt-in, since the two mods this runs against hold different rules.

  RANGE_BOUNDS    an ordered_ script list with no check_range_bounds = no, which
                  logs a capping warning from Jomini whenever position overshoots
  FILE_PREFIX     a script or localization file whose name does not carry the
                  mod's prefix, so its footprint is not greppable
  ADDED_COMMENT   a comment added by the change under review, where the mod's
                  rule is that script carries none. Only added lines are read,
                  because the same rule leaves every comment already there alone
"""

import argparse
import fnmatch
import os
import re
import subprocess
import sys

from vic3lib import Report, load_config, read_lines, walk_files

ORDERED = re.compile(r"\bordered_\w+\s*=\s*\{")
QUOTED = re.compile(r'"[^"]*"')
PREFIX_DIRS = ("common", "events", "localization")


def matches(rel, patterns):
    return any(fnmatch.fnmatch(rel, p) for p in patterns)


def check_range_bounds(mod_root, report):
    for full, rel in walk_files(mod_root, (".txt",), "common"):
        text = "".join(read_lines(full))
        lines = read_lines(full)
        offsets, running = [], 0
        for line in lines:
            offsets.append(running)
            running += len(line) + 1
        joined = "\n".join(lines)
        for match in ORDERED.finditer(joined):
            start = joined.index("{", match.start())
            depth, index = 0, start
            while index < len(joined):
                if joined[index] == "{":
                    depth += 1
                elif joined[index] == "}":
                    depth -= 1
                    if depth == 0:
                        break
                index += 1
            if "check_range_bounds" not in joined[start:index]:
                line_no = joined[:match.start()].count("\n") + 1
                report.error(
                    "RANGE_BOUNDS",
                    f"{match.group(0).strip()} carries no check_range_bounds = no. "
                    "Jomini caps the position and logs it every time the list is "
                    "shorter than the position asked for.",
                    rel, line_no,
                )


def check_file_prefix(mod_root, vanilla_root, config, report):
    prefix = config["file_prefix"]
    allow_number = config.get("file_prefix_allow_number", False)
    exempt = config.get("file_prefix_exempt", [])
    pattern = re.compile(rf"^(\d+_)?{re.escape(prefix)}" if allow_number
                         else rf"^{re.escape(prefix)}")
    for directory in PREFIX_DIRS:
        for full, rel in walk_files(mod_root, (".txt", ".yml"), directory):
            name = os.path.basename(rel)
            if matches(rel, exempt) or matches(name, exempt):
                continue
            if vanilla_root and os.path.isfile(os.path.join(vanilla_root, rel)):
                continue
            if not pattern.match(name):
                report.error(
                    "FILE_PREFIX",
                    f"'{name}' does not carry the '{prefix}' prefix, so it does not "
                    "read as the mod's own file. A file standing in for a vanilla one "
                    "keeps vanilla's name and belongs in file_prefix_exempt.",
                    rel, 1,
                )


def added_lines(mod_root, base):
    """Yields (rel_path, line_number, text) for lines the change adds."""
    def git(*args):
        return subprocess.run(("git",) + args, cwd=mod_root, capture_output=True,
                              text=True, check=False)

    merge_base = git("merge-base", base, "HEAD")
    if merge_base.returncode != 0:
        print(f"::notice::Cannot reach {base}, so the comment check is skipped.")
        return
    diff = git("diff", "--unified=0", merge_base.stdout.strip(), "HEAD",
               "--", "*.txt", "*.yml", "*.gui")
    if diff.returncode != 0:
        print("::notice::Cannot read the diff, so the comment check is skipped.")
        return

    rel, number = None, 0
    for line in diff.stdout.splitlines():
        if line.startswith("+++ b/"):
            rel = line[6:]
        elif line.startswith("@@"):
            match = re.search(r"\+(\d+)", line)
            number = int(match.group(1)) if match else 0
        elif line.startswith("+") and rel:
            yield rel, number, line[1:]
            number += 1


def check_added_comments(mod_root, base, report):
    for rel, number, text in added_lines(mod_root, base):
        if rel.startswith(".github/"):
            continue
        bare = QUOTED.sub("", text)
        if "#" in bare:
            report.error(
                "ADDED_COMMENT",
                "The change adds a comment. This mod's script carries none, and is "
                "kept readable by naming and arrangement instead.",
                rel, number,
            )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mod", default=".")
    parser.add_argument("--vanilla", default="")
    parser.add_argument("--config", default=".github/vic3-validate.json")
    parser.add_argument("--diff-base", default="")
    args = parser.parse_args()

    config = load_config(args.mod, args.config)
    report = Report("Conventions")
    vanilla = args.vanilla if args.vanilla and os.path.isdir(args.vanilla) else ""

    if config.get("require_check_range_bounds"):
        check_range_bounds(args.mod, report)

    if config.get("file_prefix"):
        if vanilla:
            check_file_prefix(args.mod, vanilla, config, report)
        else:
            print("::notice::No vanilla checkout available, so the file prefix check "
                  "is skipped. A file standing in for a vanilla one is told apart by "
                  "carrying vanilla's own path, which needs vanilla to see.")

    if config.get("forbid_added_comments"):
        if args.diff_base:
            check_added_comments(args.mod, args.diff_base, report)
        else:
            print("::notice::No base to diff against, so the comment check is skipped.")

    sys.exit(report.finish())


if __name__ == "__main__":
    main()
