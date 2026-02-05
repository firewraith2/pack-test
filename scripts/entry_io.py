#!/usr/bin/env python3
"""
Export or import a single entry from/to a pack file.

Usage:
    # Export single entry from ROM
    python scripts/entry.py export game.nds 42 output.wan --pack EFFECT/effect.bin

    # Export single entry from .bin file
    python scripts/entry.py export effect.bin 42 output.wan

    # Import single entry (overwrites pack)
    python scripts/entry.py import game.nds 42 modified.wan --pack EFFECT/effect.bin

    # Import single entry with separate output
    python scripts/entry.py import game.nds 42 modified.wan -o new.nds --pack EFFECT/effect.bin
"""

import argparse
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))
from bin_pack import PackManager, KNOWN_PACK_FILES


def export_entry(
    pack_file: Path,
    index: int,
    output_path: Path,
    pack_path: str = "EFFECT/effect.bin",
) -> None:
    manager = PackManager()

    if pack_file.suffix.lower() == ".nds":
        manager.load_from_rom(pack_file, pack_path)
    else:
        manager.load_from_file(pack_file)

    if index < 0 or index >= len(manager):
        raise ValueError(f"Index {index} out of range (0-{len(manager)-1})")

    manager.export_entry(index, output_path)
    print(f"Exported entry {index:04d} to {output_path.name}")


def import_entry(
    pack_file: Path,
    index: int,
    input_path: Path,
    output_path: Optional[Path] = None,
    pack_path: str = "EFFECT/effect.bin",
) -> None:
    if output_path is None:
        output_path = pack_file

    manager = PackManager()

    if pack_file.suffix.lower() == ".nds":
        manager.load_from_rom(pack_file, pack_path)
    else:
        manager.load_from_file(pack_file)

    if index < 0 or index >= len(manager):
        raise ValueError(f"Index {index} out of range (0-{len(manager)-1})")

    manager.import_entry(index, input_path)

    save_rom = (
        pack_file.suffix.lower() == ".nds" and output_path.suffix.lower() == ".nds"
    )
    manager.save_as(output_path, save_rom=save_rom)
    print(
        f"Imported {input_path.name} to entry {index:04d}, saved to {output_path.name}"
    )


def main():
    parser = argparse.ArgumentParser(
        description="Export or import a single entry from/to a pack file."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    export_parser = subparsers.add_parser("export", help="Export a single entry")
    export_parser.add_argument("pack_file", help="Pack file (.nds ROM or .bin)")
    export_parser.add_argument("index", type=int, help="Entry index to export")
    export_parser.add_argument("output", help="Output file path")
    export_parser.add_argument(
        "--pack",
        default="EFFECT/effect.bin",
        choices=KNOWN_PACK_FILES,
        help="Pack file path in ROM",
    )

    import_parser = subparsers.add_parser("import", help="Import a single entry")
    import_parser.add_argument("pack_file", help="Pack file (.nds ROM or .bin)")
    import_parser.add_argument("index", type=int, help="Entry index to replace")
    import_parser.add_argument("input", help="Input file to import")
    import_parser.add_argument(
        "--pack",
        default="EFFECT/effect.bin",
        choices=KNOWN_PACK_FILES,
        help="Pack file path in ROM",
    )
    import_parser.add_argument(
        "--output",
        "-o",
        help="Output file (defaults to overwriting input pack)",
    )

    args = parser.parse_args()

    pack_file = Path(args.pack_file)
    if not pack_file.exists():
        print(f"Error: Pack file not found: {pack_file}")
        sys.exit(1)

    try:
        if args.command == "export":
            export_entry(pack_file, args.index, Path(args.output), args.pack)

        elif args.command == "import":
            input_path = Path(args.input)
            if not input_path.exists():
                print(f"Error: Input file not found: {input_path}")
                sys.exit(1)

            output_path = Path(args.output) if args.output else None
            import_entry(pack_file, args.index, input_path, output_path, args.pack)

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
