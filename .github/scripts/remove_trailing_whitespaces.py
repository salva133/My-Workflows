import argparse
from pathlib import Path
import re

def remove_trailing_whitespace(file_path: Path):
    try:
        # Read file
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Remove one or more spaces/tabs immediately before line ending or end of file
        new_content = re.sub(r'[ \t]+(\r?\n|$)', r'\1', content)
        
        # Only write if changes were made
        if new_content != content:
            with open(file_path, 'w', encoding='utf-8', newline='') as f:
                f.write(new_content)
            print(f"✓ Cleaned: {file_path}")
            return True
        return False
            
    except UnicodeDecodeError:
        print(f"✗ Encoding error (not UTF-8): {file_path}")
    except Exception as e:
        print(f"✗ Error processing {file_path}: {e}")
    return False


def main():
    parser = argparse.ArgumentParser(
        description="Recursively remove trailing whitespace from all .txt, .yml and .yaml files"
    )
    parser.add_argument(
        'directory', 
        nargs='?', 
        default='.',
        help='Starting directory (default: current directory)'
    )
    parser.add_argument(
        '-v', '--verbose', 
        action='store_true',
        help='Also show unchanged files'
    )
    
    args = parser.parse_args()
    root = Path(args.directory).resolve()

    if not root.exists():
        print(f"Error: Directory '{root}' does not exist.")
        return

    print(f"Searching in: {root}\n")
    
    processed = 0
    changed = 0

    for file_path in root.rglob("*"):
        if file_path.is_file() and file_path.suffix.lower() in {'.txt', '.yml', '.yaml'}:
            processed += 1
            if remove_trailing_whitespace(file_path):
                changed += 1

    print(f"\nDone! Cleaned {changed} of {processed} files.")


if __name__ == "__main__":
    main()
