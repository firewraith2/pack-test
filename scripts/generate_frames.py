#!/usr/bin/env python3
"""
Generate frames from WAN file(s) or extracted folder(s).

Usage:
    python generate_frames.py <wan_file>                 # Single WAN file
    python generate_frames.py <wan1> <wan2>              # Multiple WAN files
    python generate_frames.py <extracted_folder>         # Single extracted folder
    python generate_frames.py <parent_folder>            # All items in folder
"""

import sys
import argparse
from pathlib import Path

# Add parent directory to path for imports
script_dir = Path(__file__).parent
if str(script_dir.parent) not in sys.path:
    sys.path.insert(0, str(script_dir.parent))

from generators import fg_process_single_folder, fg_process_multiple_folder


def is_extracted_folder(folder: Path) -> bool:
    """Check if folder looks like an extracted WAN folder."""
    return (folder / "spriteinfo.xml").exists() or (folder / "frames.xml").exists()


def main():
    parser = argparse.ArgumentParser(
        description="Generate frames from WAN file(s) or extracted folder(s)"
    )
    parser.add_argument(
        "paths",
        nargs="+",
        help="WAN file(s), extracted folder(s), or parent folder",
    )
    parser.add_argument(
        "--avoid-overlap",
        choices=["none", "palette", "chunk"],
        default="none",
        help="Overlap handling mode (default: none)",
    )

    args = parser.parse_args()

    for path_str in args.paths:
        input_path = Path(path_str).resolve()

        if not input_path.exists():
            print(f"[ERROR] Path does not exist: {input_path}")
            continue

        if input_path.is_file():
            # Single WAN file
            if not input_path.suffix.lower() == ".wan":
                print(f"[ERROR] File is not a WAN file: {input_path}")
                continue
            fg_process_single_folder(input_path, avoid_overlap=args.avoid_overlap)
        elif is_extracted_folder(input_path):
            # Single extracted folder
            fg_process_single_folder(input_path, avoid_overlap=args.avoid_overlap)
        else:
            # Parent folder with multiple items
            fg_process_multiple_folder(input_path, avoid_overlap=args.avoid_overlap)


if __name__ == "__main__":
    main()
