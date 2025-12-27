#!/usr/bin/env python3
"""
Test WAN files with round-trip checksum verification.

This script tests WAN file integrity by:
1. Extracting WAN -> external files folder
2. Regenerating WAN from external files
3. Comparing checksums (original vs regenerated)

Usage:
    # Test all WAN files in tests/demo-wans/
    python tests/test_wan_files.py

    # Test specific WAN file(s)
    python tests/test_wan_files.py d51p41a2.wan
    python tests/test_wan_files.py entry_0001.wan entry_0002.wan

Test Data:
    WAN files should be placed in tests/demo-wans/ directory.
    The test creates temporary files in tests/temp_test_output/ (auto-cleaned).

Exit Codes:
    0 - All tests passed (checksums match)
    1 - One or more tests failed (checksums differ)
"""

import hashlib
import sys
import shutil
import argparse
from pathlib import Path

script_dir = Path(__file__).parent
if str(script_dir.parent) not in sys.path:
    sys.path.insert(0, str(script_dir.parent))

from generators import wan_transform_process_single
from data import read_file_to_bytes


def get_file_checksum(file_path: Path) -> str:
    """Get SHA256 checksum of a file."""
    data = read_file_to_bytes(file_path)
    return hashlib.sha256(data).hexdigest()


def test_file_checksum(wan_file: Path) -> bool:
    """Test a single WAN file with round-trip checksum verification.

    WAN -> extract -> folder -> generate -> WAN, then compare checksums.
    """
    temp_dir = script_dir / "temp_test_output"
    temp_dir.mkdir(parents=True, exist_ok=True)

    # Copy WAN file to temp dir for processing
    temp_wan = temp_dir / wan_file.name
    shutil.copy(wan_file, temp_wan)

    try:
        orig_hash = get_file_checksum(wan_file)

        # Extract WAN to folder (creates {wan_stem}_extracted/)
        success = wan_transform_process_single(temp_wan)
        if not success:
            return False

        extracted_folder = temp_dir / f"{wan_file.stem}_extracted"
        if not extracted_folder.exists():
            print(f"  ERROR: Extracted folder not found: {extracted_folder}")
            return False

        # Generate WAN from extracted folder (creates {folder_name}.wan)
        success = wan_transform_process_single(extracted_folder)
        if not success:
            return False

        regenerated_wan = extracted_folder / f"{extracted_folder.name}.wan"
        if not regenerated_wan.exists():
            print(f"  ERROR: Regenerated WAN not found: {regenerated_wan}")
            return False

        gen_hash = get_file_checksum(regenerated_wan)

        return orig_hash == gen_hash

    except Exception as e:
        print(f"  ERROR: {e}")
        import traceback

        traceback.print_exc()
        return False

    finally:
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)


def test_specific_files(file_names: list) -> dict:
    """Test specific WAN files by name."""
    test_data_dir = script_dir / "demo-wans"
    results = {}

    for wan_name in file_names:
        wan_file = test_data_dir / wan_name
        if not wan_file.exists():
            print(f"File not found: {wan_file}")
            results[wan_name] = False
            continue

        print(f"\nTesting {wan_name}...")

        result = test_file_checksum(wan_file)
        results[wan_name] = result
        status = "PASS" if result else "FAIL"
        print(status)

    return results


def test_all_files() -> dict:
    """Test all WAN files in tests/demo-wans folder."""
    test_data_dir = script_dir / "demo-wans"
    all_wan_files = sorted(test_data_dir.glob("*.wan"))

    if not all_wan_files:
        print(f"No WAN files found in {test_data_dir}")
        return {}

    print(f"Testing {len(all_wan_files)} WAN file(s):\n")
    results = {}

    for wan_file in all_wan_files:
        print(f"Testing {wan_file.name}...")

        result = test_file_checksum(wan_file)
        results[wan_file.name] = result
        status = "PASS" if result else "FAIL"
        print(status)

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Test WAN files with round-trip checksum verification"
    )
    parser.add_argument(
        "files",
        nargs="*",
        help="Specific WAN files to test (e.g., d51p41a2.wan). If not specified, tests all files in tests/demo-wans",
    )

    args = parser.parse_args()

    temp_dir = script_dir / "temp_test_output"
    if temp_dir.exists():
        shutil.rmtree(temp_dir, ignore_errors=True)

    try:
        if args.files:
            results = test_specific_files(args.files)
        else:
            results = test_all_files()
    finally:
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)

    print(f"\n{'='*60}")
    print("Summary:")
    passed = sum(1 for r in results.values() if r)
    total = len(results)
    print(f"Passed: {passed}/{total}")
    if passed < total:
        print(f"Failed: {total - passed}/{total}")

    if total <= 20:
        for name, result in results.items():
            status = "PASS" if result else "FAIL"
            print(f"  {status} - {name}")
    else:
        failed = [name for name, result in results.items() if not result]
        if failed:
            print("\nFailed files:")
            for name in failed:
                print(f"  FAIL - {name}")

    print(f"{'='*60}")

    sys.exit(0 if passed == total else 1)
