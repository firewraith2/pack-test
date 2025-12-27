from pathlib import Path
from wan_files import generate_wan
from external_files import write_external_files
from data import SEPARATOR_LINE_LENGTH, validate_path_exists_and_is_dir
from .utils import validate_external_input


def wan_transform_main(data) -> Path:
    """Transform between WAN file and external files.

    Args:
        data: Tuple containing (sprite, path)
    """
    sprite, path = data

    if path.is_dir():
        # Generate WAN from folder
        print("[START] Generating WAN file...")
        folder_name = path.name
        output_path = path / f"{folder_name}.wan"
        generate_wan(sprite, output_path)
        print(f"\n[OK] WAN file generated successfully at: {output_path}")
        return output_path
    else:
        # Extract WAN to folder
        print("[START] Extracting WAN file...")
        output_dir = path.parent / f"{path.stem}_extracted"
        write_external_files(sprite, output_dir)
        print(f"\n[OK] WAN file extracted successfully to: {output_dir}")
        return output_dir


def wan_transform_process_single(path: Path, generate: bool = True) -> bool:
    """Process a single folder or WAN file.

    Args:
        path: Path to folder (for WAN generation) or .wan file (for extraction)
        generate: Ignored, operation auto-detected from path type

    Returns:
        True if successful, False otherwise
    """
    if not path.exists():
        print(f"[ERROR] Path does not exist: {path}")
        return False

    # Auto-detect operation based on path type
    is_folder = path.is_dir()
    is_wan_file = path.is_file() and path.suffix.lower() == ".wan"

    if not is_folder and not is_wan_file:
        print(f"[ERROR] Path must be a folder or .wan file: {path}")
        return False

    print("=" * SEPARATOR_LINE_LENGTH)
    if is_folder:
        print(f"[INFO] Processing folder: {path}")
        print(f"[INFO] Operation: Generate WAN")
    else:
        print(f"[INFO] Processing WAN file: {path}")
        print(f"[INFO] Operation: Extract WAN")
    print("=" * SEPARATOR_LINE_LENGTH)
    print()

    try:
        # Validate and load sprite
        # For extraction: allow errors so user can fix the extracted files
        # For generation: raise on errors to prevent generating invalid WAN
        if is_wan_file:
            sprite, _ = validate_external_input(path, raise_on_errors=False)
        else:
            sprite, _ = validate_external_input(path, raise_on_errors=True)

        data = (sprite, path)
        wan_transform_main(data)

        return True

    except Exception as e:
        print(f"[ERROR] Error during processing: {str(e)}")
        return False


def wan_transform_process_multiple(parent_folder: Path, generate: bool = True) -> None:
    """Process multiple folders or WAN files in a parent folder.

    Args:
        parent_folder: Folder containing subfolders or WAN files
        generate: If True, generate WAN from folders; if False, extract WAN files
    """
    if not validate_path_exists_and_is_dir(parent_folder, "Parent folder"):
        return

    if generate:
        # Find all subfolders (exclude common output folders)
        items = [
            f
            for f in parent_folder.iterdir()
            if f.is_dir() and not f.name.endswith(("_extracted", "_sprite", "_frames"))
        ]
        operation = "Generate WAN"
    else:
        # Find all WAN files
        items = list(parent_folder.glob("*.wan"))
        operation = "Extract WAN"

    if not items:
        item_type = "subfolders" if generate else "WAN files"
        print(f"[ERROR] No {item_type} found in: {parent_folder}")
        return

    print("=" * SEPARATOR_LINE_LENGTH)
    print(f"[INFO] Found {len(items)} item(s) to process")
    print(f"[INFO] Operation: {operation}")
    print("=" * SEPARATOR_LINE_LENGTH)
    print()

    success_count = 0
    failed_items = []

    for idx, item_path in enumerate(items):
        if idx > 0:
            print()

        success = wan_transform_process_single(item_path, generate=generate)

        if success:
            success_count += 1
        else:
            failed_items.append(item_path.name)

    print()
    print("=" * SEPARATOR_LINE_LENGTH)
    print("[SUMMARY] PROCESSING SUMMARY")
    print("=" * SEPARATOR_LINE_LENGTH)
    print(f"[INFO] Total: {len(items)}")
    print(f"[INFO] Successful: {success_count}")
    print(f"[INFO] Failed: {len(failed_items)}")

    if failed_items:
        print("\n[ERROR] Failed items:")
        for item in failed_items:
            print(f"   • {item}")

    print("=" * SEPARATOR_LINE_LENGTH)
