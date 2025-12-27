#!/usr/bin/env python3
"""
Test script for Wanimation Studio generators.

Tests the round-trip conversions (each tests all 4 sprite modes):
- External Files Based: frames -> external files -> frames
- WAN Files Based: frames -> WAN -> frames

Sprite Modes Tested:
  - 4bpp: Standard 4-bit per pixel sprites
  - 4bpp+tiles: 4bpp with tiles mode enabled
  - 8bpp: 8-bit per pixel sprites (256 colors)
  - 8bpp+tiles: 8bpp with tiles mode enabled

Usage:
    # Run all tests (both external files and WAN based with all modes)
    python tests/test_generators.py

    # Run only external files based test (all 4 modes)
    python tests/test_generators.py --test-files

    # Run only WAN files based test (all 4 modes)
    python tests/test_generators.py --test-wan

    # Run only specific sprite modes
    python tests/test_generators.py --4bpp --8bpp

    # Combine options (test only 4bpp mode for WAN files)
    python tests/test_generators.py --test-wan --4bpp

    # Keep output folders for manual inspection (skip cleanup)
    python tests/test_generators.py --keep-output

Test Data:
    The test uses demo frames from tests/demo-frames/ directory.
    Each subfolder represents a separate test case with PNG images and config.json.

Exit Codes:
    0 - All tests passed
    1 - One or more tests failed
"""

import sys
import shutil
import argparse
from pathlib import Path
from PIL import Image
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from generators import sg_process_multiple_folder, fg_process_multiple_folder
from data import read_file_to_bytes, read_json_file, SEPARATOR_LINE_LENGTH

STEP_SEPARATOR = "-" * SEPARATOR_LINE_LENGTH
SECTION_SEPARATOR = "=" * SEPARATOR_LINE_LENGTH


def print_step_header(step_num, title):
    print(STEP_SEPARATOR)
    print(f"[STEP {step_num}] {title}...")
    print(STEP_SEPARATOR)
    print()


def safe_remove_folder(folder_path: Path, description=""):
    if not folder_path.exists():
        return False

    try:
        shutil.rmtree(folder_path)
        if description:
            print(f"[OK] Removed {description}")
        return True
    except Exception as e:
        if description:
            print(f"[WARNING] Failed to remove {description}: {e}")
        return False


def get_subfolders(base_dir: Path):
    return sorted(entry.name for entry in base_dir.iterdir() if entry.is_dir())


def compare_images(img1_path: Path, img2_path: Path):
    try:
        with Image.open(img1_path) as img1, Image.open(img2_path) as img2:
            if img1.size != img2.size:
                return False

            if img1.mode != "P":
                img1 = img1.convert("P")
            if img2.mode != "P":
                img2 = img2.convert("P")

            arr1 = np.array(img1, dtype=np.uint8)
            arr2 = np.array(img2, dtype=np.uint8)
            if not np.array_equal(arr1, arr2):
                return False

            return img1.getpalette() == img2.getpalette()
    except Exception as e:
        print(f"    [ERROR] Failed to compare {img1_path} and {img2_path}: {e}")
        return False


def find_all_files(folder: Path, exclude_dirs=None):
    exclude_dirs = exclude_dirs or set()
    files = {}
    folder_path = folder

    if not folder_path.exists():
        return files

    for file_path in folder_path.rglob("*"):
        if file_path.is_file():
            # Check if file is inside any excluded directory
            relative_path = file_path.relative_to(folder_path)
            path_parts = relative_path.parts
            if any(excluded_dir in path_parts for excluded_dir in exclude_dirs):
                continue
            files[relative_path.as_posix()] = file_path

    return files


def compare_json_files(json1_path: Path, json2_path: Path):
    try:
        data1 = read_json_file(json1_path)
        data2 = read_json_file(json2_path)

        if data1 is None or data2 is None:
            return False

        if isinstance(data1, dict) and isinstance(data2, dict):
            data1_normalized = {k: v for k, v in data1.items() if k != "frames_folder"}
            data2_normalized = {k: v for k, v in data2.items() if k != "frames_folder"}
            return data1_normalized == data2_normalized

        return data1 == data2
    except Exception as e:
        print(
            f"    [ERROR] Failed to compare JSON files {json1_path} and {json2_path}: {e}"
        )
        return False


def compare_file(original_path: Path, generated_path: Path, relative_path: str):
    ext = relative_path.lower()

    if ext.endswith(".png"):
        matches = compare_images(original_path, generated_path)
    elif ext.endswith(".json"):
        matches = compare_json_files(original_path, generated_path)
    else:
        try:
            matches = read_file_to_bytes(original_path) == read_file_to_bytes(
                generated_path
            )
        except Exception as e:
            return False, f"    [ERROR] Failed to compare {relative_path}: {e}"

    status = "matches" if matches else "does not match"
    return matches, f"    [{'OK' if matches else 'FAIL'}] {relative_path} {status}"


def compare_folders(original_folder: Path, generated_folder: Path, folder_name):
    # Exclude DEBUG folders from comparison
    original_files = find_all_files(original_folder, exclude_dirs={"DEBUG"})
    generated_files = find_all_files(generated_folder, exclude_dirs={"DEBUG"})

    details = []
    all_match = True

    original_keys = set(original_files.keys())
    generated_keys = set(generated_files.keys())

    missing_in_generated = original_keys - generated_keys
    extra_in_generated = generated_keys - original_keys

    if missing_in_generated:
        details.append(
            f"    [ERROR] Missing files in generated: {sorted(missing_in_generated)}"
        )
        all_match = False

    if extra_in_generated:
        details.append(
            f"    [WARNING] Extra files in generated: {sorted(extra_in_generated)}"
        )

    common_files = original_keys & generated_keys
    details.append(f"    [INFO] Comparing {len(common_files)} Files")

    for relative_path in sorted(common_files):
        matches, message = compare_file(
            original_files[relative_path], generated_files[relative_path], relative_path
        )
        details.append(message)
        if not matches:
            all_match = False

    return all_match, details


def run_process_with_error_handling(
    process_func, *args, error_message="Process failed", **kwargs
):
    try:
        process_func(*args, **kwargs)
        return True
    except Exception as e:
        print(f"[ERROR] {error_message}: {e}")
        return False


# Test mode configurations: (mode_name, use_tiles_mode, is_8bpp_sprite, sprite_type)
# sprite_type: 0 for 4bpp, 2 for 8bpp
TEST_MODE_CONFIGS = [
    ("4bpp", False, False, 0),
    ("4bpp+tiles", True, False, 0),
    ("8bpp", False, True, 2),
    ("8bpp+tiles", True, True, 2),
]

# All available test mode names (derived from TEST_MODE_CONFIGS)
ALL_MODES = [m[0] for m in TEST_MODE_CONFIGS]


def get_custom_properties(mode_config):
    """Convert mode config tuple to custom_properties dict."""
    _, use_tiles_mode, is_8bpp_sprite, sprite_type = mode_config
    return {
        "use_tiles_mode": use_tiles_mode,
        "is_8bpp_sprite": is_8bpp_sprite,
        "sprite_type": sprite_type,
    }


def run_tests(keep_output=False, test_files=True, test_wan=True, modes_to_test=None):
    if modes_to_test is None:
        modes_to_test = ALL_MODES
    test_dir = Path(__file__).parent
    frames_files_dir = test_dir / "demo-frames"

    if not frames_files_dir.exists():
        print(f"[ERROR] Test directory not found: {frames_files_dir}")
        return False

    print(SECTION_SEPARATOR)
    print("Testing Generators...")
    print(SECTION_SEPARATOR)
    print()

    # Initialize result tracking
    test_results = []
    wan_test_results = []
    all_files_tests_passed = True
    all_wan_tests_passed = True
    subfolders = []

    # ===================================================================
    # External Files Based Round-Trip Test: frames -> external files -> frames
    # Test all modes: 4bpp, 4bpp+tiles, 8bpp, 8bpp+tiles
    # ===================================================================

    if test_files:
        # Filter to only requested modes
        test_modes = [m for m in TEST_MODE_CONFIGS if m[0] in modes_to_test]

        for mode_config in test_modes:
            mode_name = mode_config[0]
            print(SECTION_SEPARATOR)
            print(
                f"Testing External Files Round-Trip [{mode_name}]: frames -> files -> frames"
            )
            print(SECTION_SEPARATOR)
            print()

            print_step_header(1, f"Generating external files from frames ({mode_name})")

            if not run_process_with_error_handling(
                sg_process_multiple_folder,
                frames_files_dir,
                sprite_category="custom",
                custom_properties=get_custom_properties(mode_config),
                error_message=f"External files generation failed ({mode_name})",
            ):
                return False

            print()

            print_step_header(2, "Cleaning up DEBUG folders")

            subfolders_for_cleanup = get_subfolders(frames_files_dir)

            for subfolder_name in subfolders_for_cleanup:
                debug_folder = frames_files_dir / subfolder_name / "DEBUG"
                safe_remove_folder(debug_folder, f"DEBUG folder from {subfolder_name}")

            print()

            print_step_header(
                3, f"Moving external files folders to separate location ({mode_name})"
            )

            subfolders = get_subfolders(frames_files_dir)
            if not subfolders:
                print("[ERROR] No subfolders found in demo-frames")
                return False

            generated_sprites_dir = (
                test_dir / f"generated_sprites_{mode_name.replace('+', '_')}"
            )

            if generated_sprites_dir.exists():
                print(f"[INFO] Cleaning up existing {generated_sprites_dir}...")
                safe_remove_folder(generated_sprites_dir)

            generated_sprites_dir.mkdir(parents=True, exist_ok=True)

            moved_folders = []
            for subfolder_name in subfolders:
                # New naming: {subfolder_name}_sprite folder
                source_sprite_folder = (
                    frames_files_dir / subfolder_name / f"{subfolder_name}_sprite"
                )
                dest_sprite_folder = generated_sprites_dir / f"{subfolder_name}_sprite"

                if source_sprite_folder.exists():
                    print(
                        f"[INFO] Moving {subfolder_name}/{subfolder_name}_sprite to {generated_sprites_dir.name}/{subfolder_name}_sprite..."
                    )
                    shutil.move(source_sprite_folder, dest_sprite_folder)
                    moved_folders.append(subfolder_name)
                else:
                    print(
                        f"    [WARNING] Sprite folder not found for {subfolder_name}, skipping..."
                    )

            if not moved_folders:
                print(f"[ERROR] No sprite folders were moved for {mode_name}")
                return False

            print(
                f"[OK] Moved {len(moved_folders)} sprite folder(s) to {generated_sprites_dir}"
            )
            print()

            print_step_header(4, f"Generating frames from external files ({mode_name})")

            if not run_process_with_error_handling(
                fg_process_multiple_folder,
                generated_sprites_dir,
                error_message=f"Frame generation failed ({mode_name})",
            ):
                return False

            print()

            print_step_header(
                5, f"Comparing generated frames with original frames ({mode_name})"
            )

            for subfolder_name in sorted(moved_folders):
                print(f"[TEST] Testing {subfolder_name} ({mode_name})...")

                original_folder = frames_files_dir / subfolder_name
                # Frames are generated inside the sprite folder as {sprite_folder_name}_frames
                sprite_folder_name = f"{subfolder_name}_sprite"
                generated_frames_folder = (
                    generated_sprites_dir
                    / sprite_folder_name
                    / f"{sprite_folder_name}_frames"
                )

                if not generated_frames_folder.exists():
                    print(
                        f"    [ERROR] Generated frames folder not found: {generated_frames_folder}"
                    )
                    all_files_tests_passed = False
                    test_results.append(
                        (
                            f"{subfolder_name} ({mode_name})",
                            False,
                            ["Generated frames folder not found"],
                        )
                    )
                    continue

                success, details = compare_folders(
                    original_folder, generated_frames_folder, subfolder_name
                )

                for detail in details:
                    print(detail)

                status_msg = "All Files Match!" if success else "Files Do Not Match"
                print(
                    f"    [{'SUCCESS' if success else 'FAIL'}] {subfolder_name} ({mode_name}) - {status_msg}"
                )

                if not success:
                    all_files_tests_passed = False

                test_results.append(
                    (f"{subfolder_name} ({mode_name})", success, details)
                )

            print()
            if keep_output:
                print_step_header(
                    6, f"Skipping cleanup of {mode_name} folder (--keep-output)"
                )
                print(f"[INFO] Keeping {generated_sprites_dir} for manual inspection")
            else:
                print_step_header(6, f"Cleaning up {mode_name} folder")
                if not safe_remove_folder(
                    generated_sprites_dir, str(generated_sprites_dir)
                ):
                    print(
                        f"[INFO] {generated_sprites_dir} does not exist, skipping cleanup"
                    )

            print()

    # ===================================================================
    # WAN Files Based Round-Trip Test: frames -> WAN -> frames
    # Test all modes: 4bpp, 4bpp+tiles, 8bpp, 8bpp+tiles
    # ===================================================================

    if test_wan:
        # Get subfolders if not already retrieved
        if not subfolders:
            subfolders = get_subfolders(frames_files_dir)

        # Filter to only requested modes
        test_modes = [m for m in TEST_MODE_CONFIGS if m[0] in modes_to_test]

        for mode_config in test_modes:
            mode_name = mode_config[0]
            print(SECTION_SEPARATOR)
            print(f"Testing WAN Round-Trip [{mode_name}]: frames -> WAN -> frames")
            print(SECTION_SEPARATOR)
            print()

            print_step_header(1, f"Generating WAN Files from frames ({mode_name})")

            if not run_process_with_error_handling(
                sg_process_multiple_folder,
                frames_files_dir,
                export_as_wan=True,
                sprite_category="custom",
                custom_properties=get_custom_properties(mode_config),
                error_message=f"WAN file generation failed ({mode_name})",
            ):
                return False

            print()

            print_step_header(2, "Cleaning up DEBUG folders after WAN generation")

            subfolders_for_cleanup = get_subfolders(frames_files_dir)

            for subfolder_name in subfolders_for_cleanup:
                debug_folder = frames_files_dir / subfolder_name / "DEBUG"
                safe_remove_folder(debug_folder, f"DEBUG folder from {subfolder_name}")

            print()

            print_step_header(3, f"Moving WAN Files to isolated folder ({mode_name})")

            isolated_wan_dir = test_dir / f"isolated_wan_{mode_name.replace('+', '_')}"

            if isolated_wan_dir.exists():
                print(f"[INFO] Cleaning up existing {isolated_wan_dir}...")
                safe_remove_folder(isolated_wan_dir)

            isolated_wan_dir.mkdir(parents=True, exist_ok=True)

            wan_folders = []
            for subfolder_name in subfolders:
                # New naming: {subfolder_name}_sprite.wan
                wan_file = (
                    frames_files_dir / subfolder_name / f"{subfolder_name}_sprite.wan"
                )
                dest_wan_file = isolated_wan_dir / f"{subfolder_name}_sprite.wan"

                if wan_file.exists():
                    # Just move as-is, no renaming needed
                    shutil.move(wan_file, dest_wan_file)
                    print(
                        f"[INFO] Moved {subfolder_name}/{subfolder_name}_sprite.wan to {isolated_wan_dir.name}/{dest_wan_file.name}"
                    )
                    wan_folders.append(subfolder_name)
                else:
                    print(
                        f"    [WARNING] WAN file not found for {subfolder_name}, skipping..."
                    )

            if not wan_folders:
                print(f"[ERROR] No WAN files were found for {mode_name}")
                return False

            print(f"[OK] Moved {len(wan_folders)} WAN file(s) to {isolated_wan_dir}")
            print()

            print_step_header(4, f"Generating frames from WAN Files ({mode_name})")

            if not run_process_with_error_handling(
                fg_process_multiple_folder,
                isolated_wan_dir,
                error_message=f"Frame generation from WAN files failed ({mode_name})",
            ):
                return False

            print()

            print_step_header(
                5, f"Comparing generated frames with original frames ({mode_name})"
            )

            for subfolder_name in sorted(wan_folders):
                print(
                    f"[TEST] Testing WAN round-trip for {subfolder_name} ({mode_name})..."
                )

                original_folder = frames_files_dir / subfolder_name
                # WAN files generate frames to {wan_name}_frames folder
                wan_file_name = f"{subfolder_name}_sprite"
                generated_frames_folder = isolated_wan_dir / f"{wan_file_name}_frames"

                if not generated_frames_folder.exists():
                    print(
                        f"    [ERROR] Generated frames folder not found: {generated_frames_folder}"
                    )
                    all_wan_tests_passed = False
                    wan_test_results.append(
                        (
                            f"{subfolder_name} ({mode_name})",
                            False,
                            ["Generated frames folder not found"],
                        )
                    )
                    continue

                success, details = compare_folders(
                    original_folder, generated_frames_folder, subfolder_name
                )

                for detail in details:
                    print(detail)

                status_msg = "All Files Match!" if success else "Files Do Not Match"
                print(
                    f"    [{'SUCCESS' if success else 'FAIL'}] {subfolder_name} ({mode_name}) - {status_msg}"
                )

                if not success:
                    all_wan_tests_passed = False

                wan_test_results.append(
                    (f"{subfolder_name} ({mode_name})", success, details)
                )

            print()
            if keep_output:
                print_step_header(
                    6, f"Skipping cleanup of {mode_name} folder (--keep-output)"
                )
                print(f"[INFO] Keeping {isolated_wan_dir} for manual inspection")
            else:
                print_step_header(6, f"Cleaning up {mode_name} folder")
                if not safe_remove_folder(isolated_wan_dir, str(isolated_wan_dir)):
                    print(f"[INFO] {isolated_wan_dir} does not exist, skipping cleanup")

            print()

    # ===================================================================
    # Final Test Summary
    # ===================================================================

    print(SECTION_SEPARATOR)
    print("Test Summary")
    print(SECTION_SEPARATOR)

    all_tests_passed = True
    total_passed = 0
    total_tests = 0

    # External Files Based test results
    if test_files:
        passed_count = sum(1 for _, success, _ in test_results if success)
        total_count = len(test_results)

        print("\nExternal Files Based Round-Trip (frames -> external files -> frames):")
        for subfolder_name, success, _ in test_results:
            status = "PASS" if success else "FAIL"
            print(f"  {status}: {subfolder_name}")

        print(f"\nResults: {passed_count}/{total_count} tests passed")

        if not all_files_tests_passed:
            all_tests_passed = False
        total_passed += passed_count
        total_tests += total_count

    # WAN Files Based test results
    if test_wan:
        wan_passed_count = sum(1 for _, success, _ in wan_test_results if success)
        wan_total_count = len(wan_test_results)

        print("\nWAN Files Based Round-Trip (frames -> WAN -> frames):")
        for subfolder_name, success, _ in wan_test_results:
            status = "PASS" if success else "FAIL"
            print(f"  {status}: {subfolder_name}")

        print(f"\nResults: {wan_passed_count}/{wan_total_count} tests passed")

        if not all_wan_tests_passed:
            all_tests_passed = False
        total_passed += wan_passed_count
        total_tests += wan_total_count

    print()

    print(f"Overall Results: {total_passed}/{total_tests} tests passed")

    if all_tests_passed:
        print("[SUCCESS] All tests passed!")
        return True
    else:
        print("[FAIL] Some tests failed")
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Test script for Wanimation Studio generators. Tests round-trip conversions."
    )
    parser.add_argument(
        "--keep-output",
        action="store_true",
        help="Keep generated output folders (generated-sprites and isolated_wan_files) for manual inspection. Skips cleanup steps.",
    )
    parser.add_argument(
        "--test-files",
        action="store_true",
        help="Run only the external files based test (frames -> external files -> frames).",
    )
    parser.add_argument(
        "--test-wan",
        action="store_true",
        help="Run only the WAN files based test (frames -> WAN -> frames).",
    )
    parser.add_argument(
        "--4bpp",
        dest="mode_4bpp",
        action="store_true",
        help="Test 4bpp mode (standard 4-bit sprites).",
    )
    parser.add_argument(
        "--8bpp",
        dest="mode_8bpp",
        action="store_true",
        help="Test 8bpp mode (256 color sprites).",
    )
    parser.add_argument(
        "--4bpp-tiles",
        dest="mode_4bpp_tiles",
        action="store_true",
        help="Test 4bpp+tiles mode (4bpp with tiles mode enabled).",
    )
    parser.add_argument(
        "--8bpp-tiles",
        dest="mode_8bpp_tiles",
        action="store_true",
        help="Test 8bpp+tiles mode (8bpp with tiles mode enabled).",
    )
    args = parser.parse_args()

    # If neither --test-files nor --test-wan is specified, run both
    if not args.test_files and not args.test_wan:
        run_files = True
        run_wan = True
    else:
        run_files = args.test_files
        run_wan = args.test_wan

    # Build modes list from flags (default is all if none specified)
    modes = []
    if args.mode_4bpp:
        modes.append("4bpp")
    if args.mode_4bpp_tiles:
        modes.append("4bpp+tiles")
    if args.mode_8bpp:
        modes.append("8bpp")
    if args.mode_8bpp_tiles:
        modes.append("8bpp+tiles")
    if not modes:
        modes = ALL_MODES

    success = run_tests(
        keep_output=args.keep_output,
        test_files=run_files,
        test_wan=run_wan,
        modes_to_test=modes,
    )
    sys.exit(0 if success else 1)
