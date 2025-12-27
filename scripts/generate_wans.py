#!/usr/bin/env python3
"""
Generate WAN file(s) from extracted folder(s).

Usage:
    python generate_wans.py <extracted_folder>           # Single folder
    python generate_wans.py <folder1> <folder2>          # Multiple folders
    python generate_wans.py <parent_folder>              # All subfolders
"""

import sys
import argparse
from pathlib import Path

# Add parent directory to path for imports
script_dir = Path(__file__).parent
if str(script_dir.parent) not in sys.path:
    sys.path.insert(0, str(script_dir.parent))

from generators import wan_transform_process_single, wan_transform_process_multiple


def is_extracted_folder(folder: Path) -> bool:
    """Check if folder looks like an extracted WAN folder."""
    return (folder / "spriteinfo.xml").exists() or (folder / "frames.xml").exists()


def main():
    parser = argparse.ArgumentParser(
        description="Generate WAN file(s) from extracted folder(s)"
    )
    parser.add_argument(
        "paths",
        nargs="+",
        help="Extracted folder(s) or parent folder containing extracted folders",
    )

    args = parser.parse_args()

    for path_str in args.paths:
        input_path = Path(path_str).resolve()

        if not input_path.exists():
            print(f"[ERROR] Path does not exist: {input_path}")
            continue

        if not input_path.is_dir():
            print(f"[ERROR] Path is not a directory: {input_path}")
            continue

        if is_extracted_folder(input_path):
            # Single extracted folder
            wan_transform_process_single(input_path)
        else:
            # Parent folder with multiple extracted folders
            wan_transform_process_multiple(input_path, generate=True)


if __name__ == "__main__":
    main()
