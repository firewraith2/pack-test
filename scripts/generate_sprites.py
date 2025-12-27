#!/usr/bin/env python3
"""
Generate sprite(s) from frame folder(s).

Usage:
    python generate_sprites.py <frames_folder>           # Single folder
    python generate_sprites.py <folder1> <folder2>       # Multiple folders
    python generate_sprites.py <parent_folder>           # All subfolders
    python generate_sprites.py <path> --as-wan           # Export as WAN
"""

import sys
import argparse
from pathlib import Path

# Add parent directory to path for imports
script_dir = Path(__file__).parent
if str(script_dir.parent) not in sys.path:
    sys.path.insert(0, str(script_dir.parent))

from generators import sg_process_single_folder, sg_process_multiple_folder


def is_frames_folder(folder: Path) -> bool:
    """Check if folder looks like a frames folder (contains Frame-*.png files)."""
    return any(folder.glob("Frame-*.png"))


def main():
    parser = argparse.ArgumentParser(
        description="Generate sprite(s) from frame folder(s)"
    )
    parser.add_argument(
        "paths",
        nargs="+",
        help="Frames folder(s) or parent folder containing frame folders",
    )
    parser.add_argument(
        "--as-wan",
        action="store_true",
        help="Export as WAN file instead of extracted folder",
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

        if is_frames_folder(input_path):
            # Single frames folder
            sg_process_single_folder(input_path, export_as_wan=args.as_wan)
        else:
            # Parent folder with multiple frame folders
            sg_process_multiple_folder(input_path, export_as_wan=args.as_wan)


if __name__ == "__main__":
    main()
