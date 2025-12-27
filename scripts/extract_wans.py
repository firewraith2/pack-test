#!/usr/bin/env python3
"""
Extract WAN file(s) to external files.

Usage:
    python scripts/extract_wans.py <wan_file>                    # Single WAN file
    python scripts/extract_wans.py <wan1> <wan2> <wan3>          # Multiple WAN files
    python scripts/extract_wans.py tests/demo-wans                # All WANs in folder
"""

import sys
import argparse
from pathlib import Path

# Add parent directory to path for imports
script_dir = Path(__file__).parent
if str(script_dir.parent) not in sys.path:
    sys.path.insert(0, str(script_dir.parent))

from generators import wan_transform_process_single, wan_transform_process_multiple


def main():
    parser = argparse.ArgumentParser(
        description="Extract WAN file(s) to external files"
    )
    parser.add_argument(
        "paths",
        nargs="+",
        help="WAN file(s) or folder containing WAN files",
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
            wan_transform_process_single(input_path)
        else:
            # Folder with WAN files
            wan_transform_process_multiple(input_path, generate=False)


if __name__ == "__main__":
    main()
