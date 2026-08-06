"""Vanilla drift check for a Victoria 3 mod.

A file the mod vendors from vanilla goes stale the moment a game patch edits
vanilla's copy, and nothing in the game says so. This records the hash of every
vanilla file the mod has forked and reports the ones that have moved since.

Two kinds of fork are tracked and neither is listed by hand:

  the same-path copies    a mod file at vanilla's own path shadows that file,
                          so the path is the source and the set is discovered
  the renamed monoliths   a file gathering several vanilla files under a name
                          of its own, whose sources are found by matching the
                          keys it carries against vanilla's files in the folder
                          the config names

  VANILLA_DRIFT      a tracked vanilla file has changed since the baseline
  VANILLA_GONE       a tracked vanilla file is no longer there
  VANILLA_NEW_SOURCE a monolith carries a key from a vanilla file the baseline
                     does not track, so the fork has grown a source

Run with --write-baseline after a deliberate re-sync to record the new state.
"""

import argparse
import hashlib
import json
import os
import sys

from vic3lib import Report, collect_top_level_keys, load_config, walk_files

CONTENT_DIRS = ("common", "events", "gui", "map_data", "localization", "gfx")
BASELINE = ".github/vanilla-baseline.json"


def digest(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def same_path_forks(mod_root, vanilla_root):
    forks = {}
    for directory in CONTENT_DIRS:
        base = os.path.join(mod_root, directory)
        if not os.path.isdir(base):
            continue
        for current, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if d != ".vic3-vanilla"]
            for name in files:
                rel = os.path.relpath(os.path.join(current, name), mod_root)
                rel = rel.replace(os.sep, "/")
                if os.path.isfile(os.path.join(vanilla_root, rel)):
                    forks[rel] = [rel]
    return forks


def monolith_forks(mod_root, vanilla_root, monoliths):
    forks = {}
    for monolith, folder in monoliths.items():
        full = os.path.join(mod_root, monolith)
        if not os.path.isfile(full):
            continue
        carried = set()
        for key, entries in collect_top_level_keys(mod_root, folder).items():
            if any(rel == monolith for rel, _, _ in entries):
                carried.add(key)
        sources = set()
        for key, entries in collect_top_level_keys(vanilla_root, folder).items():
            if key in carried:
                sources.update(rel for rel, _, _ in entries)
        forks[monolith] = sorted(sources)
    return forks


def collect(mod_root, vanilla_root, config):
    forks = same_path_forks(mod_root, vanilla_root)
    forks.update(monolith_forks(mod_root, vanilla_root,
                                config.get("vendored_monoliths", {})))
    for ignored in config.get("drift_ignore", []):
        forks.pop(ignored, None)
    return forks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mod", default=".")
    parser.add_argument("--vanilla", default="")
    parser.add_argument("--config", default=".github/vic3-validate.json")
    parser.add_argument("--write-baseline", action="store_true")
    args = parser.parse_args()

    report = Report("Vanilla drift")

    if not args.vanilla or not os.path.isdir(args.vanilla):
        print("::notice::No vanilla checkout available, so the drift check is skipped.")
        sys.exit(report.finish())

    config = load_config(args.mod, args.config)
    forks = collect(args.mod, args.vanilla, config)

    current = {}
    for vendored, sources in sorted(forks.items()):
        for source in sources:
            full = os.path.join(args.vanilla, source)
            current[source] = digest(full) if os.path.isfile(full) else None

    baseline_path = os.path.join(args.mod, BASELINE)

    if args.write_baseline:
        payload = {
            "vanilla_files": {k: v for k, v in sorted(current.items()) if v},
            "forks": {k: v for k, v in sorted(forks.items())},
        }
        os.makedirs(os.path.dirname(baseline_path), exist_ok=True)
        with open(baseline_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
            fh.write("\n")
        print(f"Wrote {BASELINE}: {len(payload['vanilla_files'])} vanilla files "
              f"behind {len(forks)} vendored copies.")
        sys.exit(0)

    if not os.path.isfile(baseline_path):
        print(f"::notice::No {BASELINE} in this repository, so there is nothing to "
              "compare against. Run the drift workflow with write_baseline to record one.")
        sys.exit(report.finish())

    with open(baseline_path, encoding="utf-8") as fh:
        baseline = json.load(fh)
    known = baseline.get("vanilla_files", {})
    owner = {}
    for vendored, sources in forks.items():
        for source in sources:
            owner.setdefault(source, []).append(vendored)

    for source, current_hash in sorted(current.items()):
        vendored = ", ".join(sorted(owner.get(source, [])))
        if source not in known:
            report.warn(
                "VANILLA_NEW_SOURCE",
                f"{vendored} carries a key from {source}, which the baseline does "
                "not track. Either the fork has grown a source or vanilla moved the "
                "key into another file.",
                vendored.split(", ")[0], 1,
            )
        elif current_hash is None:
            report.error(
                "VANILLA_GONE",
                f"{source} is no longer in vanilla, and {vendored} was forked from it.",
                vendored.split(", ")[0], 1,
            )
        elif current_hash != known[source]:
            report.error(
                "VANILLA_DRIFT",
                f"{source} has changed in vanilla since {vendored} was forked from it. "
                "Re-sync the copy, then record the new baseline.",
                vendored.split(", ")[0], 1,
            )

    for source in sorted(set(known) - set(current)):
        report.warn(
            "VANILLA_NEW_SOURCE",
            f"{source} is tracked by the baseline but no vendored copy names it any "
            "more. Record a new baseline to drop it.",
            BASELINE, 1,
        )

    sys.exit(report.finish())


if __name__ == "__main__":
    main()
