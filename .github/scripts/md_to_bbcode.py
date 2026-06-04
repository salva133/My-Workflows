#!/usr/bin/env python3
"""Convert README.md to steam_desc.txt (Steam BBCode).

Called without arguments; reads README.md in the CWD and writes steam_desc.txt.
Standard library only, no setup-python required.
"""
import os
import re
import sys


def convert(md: str) -> str:
    # Remove comments
    md = re.sub(r"<!--.*?-->", "", md, flags=re.DOTALL)

    # Headings
    md = re.sub(r"^# (.*)$", r"[h1]\1[/h1]", md, flags=re.M)
    md = re.sub(r"^## (.*)$", r"[h2]\1[/h2]", md, flags=re.M)
    md = re.sub(r"^### (.*)$", r"[h3]\1[/h3]", md, flags=re.M)
    md = re.sub(r"^#### (.*)$", r"[h3]\1[/h3]", md, flags=re.M)  # Deeper levels to h3

    # Bold (before italic)
    md = re.sub(r"\*\*(.*?)\*\*", r"[b]\1[/b]", md)

    # Italic: single asterisks, no adjacent asterisks (more robust against **)
    md = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"[i]\1[/i]", md)

    # Lists: - or * to [*], and wrap in [list]...[/list]
    md = re.sub(r"^(\s*)- (.*)$", r"\1[*]\2", md, flags=re.M)
    md = re.sub(r"^(\s*)\d+\. (.*)$", r"\1[*]\2", md, flags=re.M)  # Ordered to unordered
    lines = md.splitlines()
    in_list = False
    new_lines = []
    for line in lines:
        if line.strip().startswith("[*]"):
            if not in_list:
                new_lines.append("[list]")
                in_list = True
            new_lines.append(line)
        else:
            if in_list:
                new_lines.append("[/list]")
                in_list = False
            new_lines.append(line)
    if in_list:
        new_lines.append("[/list]")
    md = "\n".join(new_lines)

    # Images -> alt text (since [img] is often broken)
    md = re.sub(r"!\[([^\[]*?)\]\(([^)]*?)\)", r"[i]\1 (image)[/i]", md)

    # Links
    md = re.sub(r"\[([^\[]+?)\]\(([^)]+?)\)", r"[url=\2]\1[/url]", md)

    # Code
    md = re.sub(r"`(.*?)`", r"[code]\1[/code]", md)

    # Blockquotes
    md = re.sub(r"^> (.*)$", r"[quote]\1[/quote]", md, flags=re.M)

    # Horizontal rules
    md = re.sub(r"^-{3,}$", r"[hr]", md, flags=re.M)

    # Collapse blank lines
    md = re.sub(r"\n{3,}", "\n\n", md)

    return md.strip()


def main() -> int:
    if not os.path.exists("README.md"):
        print("README.md not found - nothing to do.")
        return 0

    with open("README.md", encoding="utf-8") as f:
        md = f.read().strip()

    if not md:
        print("README.md is empty - nothing to do.")
        return 0

    result = convert(md)

    with open("steam_desc.txt", "w", encoding="utf-8") as f:
        f.write(result)

    print("steam_desc.txt created.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
