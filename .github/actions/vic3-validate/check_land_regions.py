"""Land region assignment for a Victoria 3 mod that sets up its own map.

A land region is a state region in map_data/state_regions that carries a
subsistence_building. Every province of every land region has to be owned
through a create_state block in common/history/states, or the map shows it
white. Province ids are compared case-insensitively, because map_data writes
them in upper case, parts of a history can write them in lower, and the engine
reads both as the same hex value.

  LAND_REGION_FREE     a land region with provinces no create_state owns
  LAND_REGION_FOREIGN  a create_state names a province outside its region
  LAND_REGION_TWICE    a region's history names the same province twice
  LAND_REGION_UNKNOWN  the history sets up a state region map_data lacks

Both folders are read as the game reads them: the mod's files over vanilla's
of the same name, and the mod's alone where the folder is in replace_paths.
A '#' inside a province list ends the line for the engine and does here too.
"""

import argparse
import os
import re
import sys

from vic3lib import Report, load_config, load_replace_paths, read_text

TOKEN = re.compile(r'"[^"\n]*"|[{}=]|#[^\n]*|[^\s{}="#]+')
REGIONS = "map_data/state_regions"
HISTORY = "common/history/states"


def tokenize(text):
    return [token for token in TOKEN.findall(text) if not token.startswith("#")]


def parse_block(tokens, position=0):
    items = []
    while position < len(tokens):
        token = tokens[position]
        position += 1
        if token == "}":
            return items, position
        if token == "{":
            block, position = parse_block(tokens, position)
            items.append((None, block))
            continue
        if position < len(tokens) and tokens[position] == "=":
            position += 1
            if position < len(tokens) and tokens[position] == "{":
                value, position = parse_block(tokens, position + 1)
            else:
                value = tokens[position] if position < len(tokens) else ""
                position += 1
            items.append((token, value))
        else:
            items.append((None, token))
    return items, position


def parse_file(path):
    return parse_block(tokenize(read_text(path)))[0]


def bare_values(block):
    return [value for key, value in block if key is None and isinstance(value, str)]


def province_id(token):
    return token.strip('"').upper()


def layered_files(mod_root, vanilla_root, folder, replace_paths):
    """Maps a file name to (full_path, rel_path or None), the mod's over vanilla's."""
    files = {}
    vanilla_dir = os.path.join(vanilla_root, folder) if vanilla_root else ""
    if vanilla_dir and os.path.isdir(vanilla_dir) and folder not in replace_paths:
        for name in os.listdir(vanilla_dir):
            if name.endswith(".txt"):
                files[name] = (os.path.join(vanilla_dir, name), None)
    mod_dir = os.path.join(mod_root, folder)
    if os.path.isdir(mod_dir):
        for name in os.listdir(mod_dir):
            if name.endswith(".txt"):
                files[name] = (os.path.join(mod_dir, name), f"{folder}/{name}")
    return [files[name] for name in sorted(files)]


def load_regions(files):
    """Maps a state region to (rel_path, file_name, is_land, provinces)."""
    regions = {}
    for full, rel in files:
        for key, value in parse_file(full):
            if not key or not isinstance(value, list) or key in regions:
                continue
            provinces, land = [], False
            for field, content in value:
                if field == "provinces" and isinstance(content, list):
                    provinces = [province_id(token) for token in bare_values(content)]
                elif field == "subsistence_building":
                    land = True
            regions[key] = (rel, os.path.basename(full), land, provinces)
    return regions


def load_assignments(files):
    """Maps a state region to the (province, rel_path) pairs its history owns."""
    assigned = {}
    for full, rel in files:
        for key, value in parse_file(full):
            if key != "STATES" or not isinstance(value, list):
                continue
            for state, body in value:
                if not state or not isinstance(body, list):
                    continue
                region = state[2:] if state.startswith("s:") else state
                owned = assigned.setdefault(region, [])
                for field, content in body:
                    if field != "create_state" or not isinstance(content, list):
                        continue
                    for inner, provinces in content:
                        if inner == "owned_provinces" and isinstance(provinces, list):
                            owned.extend((province_id(token), rel)
                                         for token in bare_values(provinces))
    return assigned


def sample(provinces, size=8):
    shown = " ".join(provinces[:size])
    return shown + (f" and {len(provinces) - size} more" if len(provinces) > size else "")


def check_land_regions(mod_root, vanilla_root, report):
    replace_paths = load_replace_paths(mod_root)
    regions = load_regions(layered_files(mod_root, vanilla_root, REGIONS, replace_paths))
    assigned = load_assignments(layered_files(mod_root, vanilla_root, HISTORY, replace_paths))

    land = 0
    for region, (rel, name, is_land, provinces) in sorted(regions.items()):
        if not is_land:
            continue
        land += 1
        owned = {province for province, _ in assigned.get(region, [])}
        free = [province for province in provinces if province not in owned]
        if not free:
            continue
        where = "" if rel else f" (vanilla {REGIONS}/{name})"
        if owned:
            message = (f"{region}{where} has {len(free)} of {len(provinces)} provinces no "
                       f"create_state owns: {sample(free)}. They show white on the map.")
        else:
            message = (f"{region}{where} is set up by no create_state, so all "
                       f"{len(provinces)} of its provinces show white on the map.")
        report.error("LAND_REGION_FREE", message, rel, 1 if rel else None)

    for region, entries in sorted(assigned.items()):
        if not entries:
            continue
        rel = entries[0][1]
        if region not in regions:
            report.error("LAND_REGION_UNKNOWN",
                         f"s:{region} is not a state region in {REGIONS}.", rel)
            continue
        members = set(regions[region][3])
        foreign = [province for province, _ in entries if province not in members]
        if foreign:
            report.error("LAND_REGION_FOREIGN",
                         f"s:{region} names {len(foreign)} province(s) outside the region: "
                         f"{sample(foreign)}.", rel)
        seen, twice = set(), []
        for province, _ in entries:
            if province in seen and province in members:
                twice.append(province)
            seen.add(province)
        if twice:
            report.error("LAND_REGION_TWICE",
                         f"s:{region} names {len(twice)} province(s) twice: {sample(twice)}.",
                         rel)

    print(f"Read {land} land region(s).")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mod", default=".")
    parser.add_argument("--vanilla", default="")
    parser.add_argument("--config", default=".github/vic3-validate.json")
    args = parser.parse_args()

    config = load_config(args.mod, args.config)
    report = Report("Land regions")
    vanilla = args.vanilla if args.vanilla and os.path.isdir(args.vanilla) else ""

    if config.get("check_land_regions"):
        replace_paths = load_replace_paths(args.mod)
        if vanilla or REGIONS in replace_paths:
            check_land_regions(args.mod, vanilla, report)
        else:
            print("::notice::No vanilla checkout available, so the land region check is "
                  "skipped. The regions the mod does not ship come from vanilla.")

    sys.exit(report.finish())


if __name__ == "__main__":
    main()
