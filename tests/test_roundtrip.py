#!/usr/bin/env python3
"""Test round-trip export/import for all pack files using script functions."""

import hashlib
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from pack_io import export_pack, create_pack
from bin_pack import KNOWN_PACK_FILES

TEST_ROM = Path(__file__).parent / "test_files/rom.nds"


def get_pack_checksum(rom_path: Path, pack_path: str) -> str:
    from ndspy.rom import NintendoDSRom

    rom = NintendoDSRom.fromFile(str(rom_path))
    data = rom.getFileByName(pack_path)
    return hashlib.md5(data).hexdigest()


def test_pack_roundtrip(pack_path: str, work_dir: Path) -> bool:
    """Test export -> create pack -> inject round-trip for a pack file."""
    export_dir = work_dir / "exported"
    modified_rom = work_dir / "modified.nds"

    export_dir.mkdir(exist_ok=True)
    shutil.copy(TEST_ROM, modified_rom)

    original_checksum = get_pack_checksum(TEST_ROM, pack_path)

    export_pack(TEST_ROM, export_dir, pack_path)

    create_pack(export_dir, modified_rom, pack_path, modified_rom)

    modified_checksum = get_pack_checksum(modified_rom, pack_path)

    return original_checksum == modified_checksum


def main():
    if not TEST_ROM.exists():
        print(f"Error: Test ROM not found: {TEST_ROM}")
        sys.exit(1)

    print("=== Pack Round-Trip Test ===\n")

    passed = 0
    failed = 0

    for pack_path in KNOWN_PACK_FILES:
        with tempfile.TemporaryDirectory() as tmp:
            work_dir = Path(tmp)
            result = test_pack_roundtrip(pack_path, work_dir)

            status = "✓ PASS" if result else "✗ FAIL"
            print(f"{status}  {pack_path}")

            if result:
                passed += 1
            else:
                failed += 1

    print(f"\n{passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
