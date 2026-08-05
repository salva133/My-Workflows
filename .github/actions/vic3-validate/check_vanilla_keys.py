"""Vanilla key collision checks for a Victoria 3 mod.

A game-database key the mod declares that vanilla also declares is refused at
load unless it carries a database entry mode (REPLACE:, TRY_REPLACE:, INJECT:,
TRY_INJECT:). The game says so once in debug.log and behaves as though the
block were not there, so the block is checked here instead.

  VANILLA_KEY_BARE   the mod redeclares a vanilla key with no entry mode
  SCRIPT_NAME_TAKEN  a scripted effect or trigger carries a vanilla name, where
                     an entry mode does not help and only a rename does
  ENTRY_MODE_TARGET  a bare REPLACE:/INJECT: names a key vanilla does not carry

Files the mod ships at vanilla's own path shadow the whole file and are skipped,
and so is everything under replace_paths and the folders the engine merges.
"""

import argparse
import os
import sys

from vic3lib import (Report, collect_top_level_keys, is_replaced, load_config,
                     load_replace_paths, walk_files)

MERGE_FOLDERS = ("common/on_actions", "common/defines", "common/named_colors")
SCRIPT_FOLDERS = ("common/scripted_effects", "common/scripted_triggers")


def vanilla_file_paths(vanilla_root):
    return {rel for _, rel in walk_files(vanilla_root, (".txt",), "common")}


def in_folders(rel_path, folders):
    return any(rel_path.startswith(folder + "/") for folder in folders)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mod", default=".")
    parser.add_argument("--vanilla", default="")
    parser.add_argument("--config", default=".github/vic3-validate.json")
    args = parser.parse_args()

    report = Report("Vanilla key collisions")

    if not args.vanilla or not os.path.isdir(args.vanilla):
        print("::notice::No vanilla checkout available, so the vanilla key checks "
              "are skipped. Set the vanilla_repo_token secret to run them.")
        sys.exit(report.finish())

    config = load_config(args.mod, args.config)
    known = set(config.get("known_bare_vanilla_keys", []))
    extra_merge = tuple(config.get("merge_folders", []))

    replace_paths = load_replace_paths(args.mod)
    shadowed = vanilla_file_paths(args.vanilla)
    mod_keys = collect_top_level_keys(args.mod, "common")
    vanilla_keys = collect_top_level_keys(args.vanilla, "common")

    for key, entries in sorted(mod_keys.items()):
        for rel, line, prefix in entries:
            if rel in shadowed:
                continue
            if is_replaced(rel, replace_paths):
                continue
            if in_folders(rel, MERGE_FOLDERS + extra_merge):
                continue

            if prefix:
                if prefix in ("REPLACE:", "INJECT:") and key not in vanilla_keys:
                    report.warn(
                        "ENTRY_MODE_TARGET",
                        f"{prefix}{key} names a key vanilla does not declare. "
                        "The bare form errors when there is nothing to answer; "
                        "take the TRY_ form where the key may be absent or comes "
                        "from a dependency.",
                        rel, line,
                    )
                continue

            if key not in vanilla_keys:
                continue

            source = vanilla_keys[key][0][0]
            if in_folders(rel, SCRIPT_FOLDERS):
                code = "SCRIPT_NAME_TAKEN"
                message = (
                    f"'{key}' is also defined by vanilla in {source}. These resolve "
                    "first-definition-wins, so vanilla's definition stands and this "
                    "one is discarded. Rename it; an entry mode does not help here."
                )
            else:
                code = "VANILLA_KEY_BARE"
                message = (
                    f"'{key}' is also declared by vanilla in {source}. Without an "
                    "entry mode the block is discarded at load. Use INJECT: to add "
                    "to what vanilla has, REPLACE: to rewrite it."
                )

            if key in known:
                report.warn(code, message + " Listed as a known finding in the "
                            "validator config.", rel, line)
            else:
                report.error(code, message, rel, line)

    sys.exit(report.finish())


if __name__ == "__main__":
    main()
