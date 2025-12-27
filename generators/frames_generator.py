import numpy as np
from pathlib import Path
from typing import Optional
from PIL import Image
from data import (
    DEBUG,
    write_json_file,
    validate_path_exists_and_is_dir,
    SEPARATOR_LINE_LENGTH,
    enum_res_to_integer,
    normalize_string,
    TILE_SIZE,
    TILE_AREA,
)
from .constants import (
    COORDINATE_CENTER_X,
    COORDINATE_CENTER_Y,
    BASE_SPRITE_INFO,
)
from wan_files import (
    BaseSprite,
    PALETTE_OFFSET_BASE,
    PALETTE_SLOT_COLOR_COUNT,
    PALETTE_SLOT_RGB_COUNT,
    PALETTE_SLOT_4BPP_BASE,
    PALETTE_SLOT_8BPP_BASE,
)
from .utils import validate_external_input


def save_tile_map(tile_map, global_palette, debug_output_folder: Path):
    TILEMAP_WIDTH = 64
    TILEMAP_HEIGHT = 32
    TOTAL_TILES = TILEMAP_WIDTH * TILEMAP_HEIGHT

    # Create blank VRAM canvas (filled with 0)
    canvas = np.zeros(
        (TILEMAP_HEIGHT * TILE_SIZE, TILEMAP_WIDTH * TILE_SIZE), dtype=np.uint8
    )

    # Limit to TOTAL_TILES (ignore extras if any)
    for i, tile in enumerate(tile_map[:TOTAL_TILES]):
        row = i // TILEMAP_WIDTH
        col = i % TILEMAP_WIDTH
        y = row * TILE_SIZE
        x = col * TILE_SIZE
        canvas[y : y + TILE_SIZE, x : x + TILE_SIZE] = tile

    img = Image.fromarray(canvas)
    img.putpalette(global_palette)
    output_path = debug_output_folder / "tilemap.png"
    img.save(output_path)
    print(
        f"\n[OK] Saved tile map ({canvas.shape[1]}x{canvas.shape[0]}) "
        f"with {min(len(tile_map), TOTAL_TILES)} tiles."
    )


def build_tile_map(images_dict, is_8bpp_sprite=False):
    all_tiles = []

    # 8bpp: 2 tiles/block (8 bits/pixel), 4bpp: 4 tiles/block (4 bits/pixel)
    tiles_per_block = 2 if is_8bpp_sprite else 4

    for chunk_idx, chunk_data in enumerate(images_dict.values()):
        arr = chunk_data["numpy_array"]

        h, w = arr.shape
        tiles_y = h // TILE_SIZE
        tiles_x = w // TILE_SIZE
        raw_tile_count = tiles_y * tiles_x

        tiles = arr.reshape(tiles_y, TILE_SIZE, tiles_x, TILE_SIZE).swapaxes(1, 2)
        tiles = tiles.reshape(-1, TILE_SIZE, TILE_SIZE)

        # Align to tile blocks (4 tiles for 4bpp, 2 tiles for 8bpp)
        pixels = raw_tile_count * TILE_AREA
        block_pixels = TILE_AREA * tiles_per_block
        aligned_tile_count = (
            (pixels + block_pixels - 1) // block_pixels
        ) * tiles_per_block

        # Add padding tiles if needed
        padding_needed = aligned_tile_count - len(tiles)
        if padding_needed > 0:
            padding_tiles = np.zeros(
                (padding_needed, TILE_SIZE, TILE_SIZE), dtype=np.uint8
            )
            tiles = np.concatenate([tiles, padding_tiles], axis=0)

        all_tiles.append(tiles)

    tile_map = np.concatenate(all_tiles, axis=0)

    return tile_map


def build_chunk_from_tilemap(tile_map, start_tile_index, chunk_width, chunk_height):
    tiles_x = chunk_width // TILE_SIZE
    tiles_y = chunk_height // TILE_SIZE
    total_needed = tiles_x * tiles_y

    tiles = tile_map[start_tile_index : start_tile_index + total_needed]

    tiles = tiles.reshape(tiles_y, tiles_x, TILE_SIZE, TILE_SIZE)

    img_array = tiles.transpose(0, 2, 1, 3).reshape(chunk_height, chunk_width)

    return img_array


def reconstruct_frames(
    sprite: BaseSprite,
    normal_mode,
    output_folder: Optional[Path],
    avoid_overlap,
    global_palette,
    uses_base_sprite: bool = False,
):
    # Build images_dict from sprite.frames
    images_dict = {}
    for idx, frame in enumerate(sprite.frames):
        if frame.pixels.size > 0:
            height, width = frame.pixels.shape
            images_dict[idx] = {
                "numpy_array": frame.pixels,
                "chunk_width": width,
                "chunk_height": height,
            }

    # Compute global bounds and build frames_dict from metaframe_groups
    global_min_x, global_min_y = float("inf"), float("inf")
    global_max_x, global_max_y = float("-inf"), float("-inf")
    frames_dict = {}

    for frame_id, group in enumerate(sprite.metaframe_groups):
        chunks_info = []
        # Reverse order: later metaframes render on top
        for mf_idx in reversed(group.metaframes):
            if mf_idx >= len(sprite.metaframes):
                continue

            mf = sprite.metaframes[mf_idx]
            chunk_id = mf.image_index
            chunk_x = mf.offset_x
            chunk_y = mf.offset_y
            chunk_palette_offset = mf.palette_offset
            chunk_memory_offset = mf.memory_offset
            width, height = enum_res_to_integer(mf.resolution)
            chunk_width = width
            chunk_height = height
            chunk_vflip = mf.v_flip
            chunk_hflip = mf.h_flip

            chunk_is_absolute_palette = mf.is_absolute_palette

            chunks_info.append(
                (
                    chunk_id,
                    chunk_x,
                    chunk_y,
                    chunk_memory_offset,
                    chunk_width,
                    chunk_height,
                    chunk_vflip,
                    chunk_hflip,
                    chunk_palette_offset,
                    chunk_is_absolute_palette,
                )
            )

            # Update global bounds
            global_min_x = min(global_min_x, chunk_x)
            global_min_y = min(global_min_y, chunk_y)
            global_max_x = max(global_max_x, chunk_x + chunk_width)
            global_max_y = max(global_max_y, chunk_y + chunk_height)

        frames_dict[frame_id] = chunks_info

    if global_min_x == float("inf") or global_min_y == float("inf"):
        global_min_x = global_min_y = 0
        global_max_x = global_max_y = TILE_SIZE

    layer_width = global_max_x - global_min_x
    layer_height = global_max_y - global_min_y

    if DEBUG:
        print(
            f"\n[INFO] Bounds:"
            f"  min=({global_min_x}, {global_min_y})"
            f"  max=({global_max_x}, {global_max_y})"
        )

        center_x = (global_min_x + global_max_x) / 2
        center_y = (global_min_y + global_max_y) / 2

        print(
            f"[INFO] Sprite Center: ({center_x:.2f}, {center_y:.2f})\n"
            f"[INFO] The coordinate origin is at ({COORDINATE_CENTER_X}, {COORDINATE_CENTER_Y})"
        )

        offcenter_x = center_x - COORDINATE_CENTER_X
        offcenter_y = center_y - COORDINATE_CENTER_Y
        offcenter_distance = (offcenter_x**2 + offcenter_y**2) ** 0.5

        print(
            f"[INFO] Offset from Origin:"
            f"  Δx={offcenter_x:.2f}, Δy={offcenter_y:.2f}, "
            f"distance={offcenter_distance:.2f}"
        )

    chunk_orientation_dict = {}

    def get_oriented_chunk(chunk_id, hflip, vflip):
        key = (chunk_id, hflip, vflip)
        if key in chunk_orientation_dict:
            return chunk_orientation_dict[key]

        # Load base image if not already cached
        base_key = (chunk_id, 0, 0)
        if base_key not in chunk_orientation_dict:
            chunk_orientation_dict[base_key] = images_dict[chunk_id]["numpy_array"]

        arr = chunk_orientation_dict[base_key]

        # Compute the requested orientation
        if hflip and vflip:
            arr = np.flip(arr, axis=(0, 1))
        elif hflip:
            arr = np.flip(arr, axis=1)
        elif vflip:
            arr = np.flip(arr, axis=0)

        chunk_orientation_dict[key] = arr
        return arr

    tile_map = None
    all_layers_list = []

    # Reconstruct frames
    for frame_id, chunks_info in frames_dict.items():
        print(f"\n[PROCESSING] Generating Frame {frame_id+1}...")
        layers_list = []

        if not chunks_info:
            blank_layer = np.zeros((layer_height, layer_width), dtype=np.uint8)
            blank_mask = np.zeros((layer_height, layer_width), dtype=bool)
            layers_list.append((blank_layer, blank_mask, 0))

        for chunk_info in chunks_info:
            (
                chunk_id,
                chunk_x,
                chunk_y,
                chunk_memory_offset,
                chunk_width,
                chunk_height,
                chunk_vflip,
                chunk_hflip,
                chunk_palette_offset,
                chunk_is_absolute_palette,
            ) = chunk_info

            if normal_mode:
                chunk_id = (
                    next(
                        (
                            chunk_info[0]
                            for chunk_info in chunks_info
                            if chunk_info[3] == chunk_memory_offset
                            and not chunk_info[0] < 0
                        ),
                        None,
                    )
                    if chunk_id < 0
                    else chunk_id
                )

                piece = get_oriented_chunk(chunk_id, chunk_hflip, chunk_vflip)

                if piece is None:
                    continue

            elif chunk_id < 0:
                # Build chunk directly from tile_map
                if tile_map is None:
                    is_8bpp_sprite = sprite.spr_info.is_8bpp_sprite == 1
                    tile_map = build_tile_map(images_dict, is_8bpp_sprite)

                # For 8bpp, memory offset maps to 2 tiles instead of 4
                tiles_per_block = 2 if is_8bpp_sprite else 4
                start_tile_index = chunk_memory_offset * tiles_per_block

                piece = build_chunk_from_tilemap(
                    tile_map,
                    start_tile_index,
                    chunk_width,
                    chunk_height,
                )

                # Flip the assembled chunk (not individual tiles)
                if chunk_hflip and chunk_vflip:
                    piece = np.flip(piece, (0, 1))
                elif chunk_hflip:
                    piece = np.flip(piece, axis=1)
                elif chunk_vflip:
                    piece = np.flip(piece, axis=0)

            # Map to palette slot (8bpp uses 16 colors per slot)
            is_8bpp_sprite = sprite.spr_info.is_8bpp_sprite == 1
            if is_8bpp_sprite:
                piece = piece % PALETTE_SLOT_COLOR_COUNT

            # Calculate palette slot from palette_offset
            palette_slot = (
                chunk_palette_offset - PALETTE_OFFSET_BASE
            ) // PALETTE_SLOT_COLOR_COUNT

            # Palette slot adjustment for base sprite layout
            palette_slot_base = (
                PALETTE_SLOT_8BPP_BASE if is_8bpp_sprite else PALETTE_SLOT_4BPP_BASE
            )

            uses_absolute_palette = is_8bpp_sprite or chunk_is_absolute_palette == 1

            if uses_absolute_palette:
                if not uses_base_sprite:
                    palette_slot -= palette_slot_base
            else:
                if uses_base_sprite:
                    palette_slot += palette_slot_base

            palette_slot = max(0, palette_slot)

            start_index = palette_slot * PALETTE_SLOT_COLOR_COUNT
            mapped_data = np.where(piece != 0, start_index + piece, 0)

            paint_mask = mapped_data != 0

            if avoid_overlap == "chunk":
                overlap_check_mask = np.ones_like(mapped_data, dtype=bool)
            elif avoid_overlap == "palette" or avoid_overlap == "none":
                overlap_check_mask = np.zeros_like(mapped_data, dtype=bool)
            else:
                overlap_check_mask = paint_mask

            # Chunk position in frame
            y_slice = slice(
                chunk_y - global_min_y, chunk_y - global_min_y + chunk_height
            )
            x_slice = slice(
                chunk_x - global_min_x, chunk_x - global_min_x + chunk_width
            )

            placed = False
            for layer_array, layer_mask, layer_palette_slot in layers_list:
                palette_matches = (avoid_overlap == "none") or (
                    layer_palette_slot == palette_slot
                )
                if palette_matches and not np.any(
                    layer_mask[y_slice, x_slice] & overlap_check_mask
                ):
                    layer_array[y_slice, x_slice] = np.where(
                        paint_mask, mapped_data, layer_array[y_slice, x_slice]
                    )
                    layer_mask[y_slice, x_slice] |= paint_mask
                    placed = True
                    break

            if not placed:
                new_layer = np.zeros((layer_height, layer_width), dtype=np.uint8)
                new_mask = np.zeros((layer_height, layer_width), dtype=bool)
                new_layer[y_slice, x_slice] = np.where(paint_mask, mapped_data, 0)
                new_mask[y_slice, x_slice] = paint_mask
                layers_list.append((new_layer, new_mask, palette_slot))

        # Save all layers (only if output_folder provided)
        if output_folder is not None:
            for layer_id, (layer_array, _, layer_palette_slot) in enumerate(
                layers_list
            ):
                layer_img = Image.fromarray(layer_array)
                layer_img.putpalette(global_palette)
                out_path = (
                    output_folder / f"Frame-{frame_id + 1}-Layer-{layer_id + 1}.png"
                )
                layer_img.save(out_path, transparency=0)
                if DEBUG:
                    print(
                        f"[OK] Saved: Frame-{frame_id + 1}-Layer-{layer_id + 1}.png",
                        f"Palette-{layer_palette_slot}",
                    )

        all_layers_list.append(layers_list)

    if output_folder is not None:
        print(f"\n[OK] Frames saved to: {output_folder}")

    return tile_map, all_layers_list


def create_json_from_animation(sprite: BaseSprite, output_folder: Path):
    animation_group = []

    for seq in sprite.anim_sequences:
        group = []
        for anim_frame in seq.frames:
            frame_no = anim_frame.meta_frm_grp_index + 1
            duration = anim_frame.frame_duration
            group.append({"frame": frame_no, "duration": duration})
        animation_group.append(group)

    json_output_path = output_folder / "config.json"

    data = {
        "frames_folder": str(output_folder.resolve()),
        "animation_group": animation_group,
    }

    write_json_file(json_output_path, data)

    print(f"\n[OK] Config JSON saved to: {json_output_path}")


def generate_frames_main(data):
    """Generate frames from BaseSprite data.

    Args:
        data: Tuple containing (sprite, base_sprite, folder_or_wan_path,
              avoid_overlap, validation_info, base_validation_info)
    """
    (
        sprite,
        base_sprite,
        folder_or_wan_path,
        avoid_overlap,
        validation_info,
        base_validation_info,
    ) = data

    avoid_overlap = normalize_string(avoid_overlap)
    print("[START] Starting Frames Generation...")

    normal_mode = validation_info.get("is_normal_mode", True)

    output_folder = None

    if folder_or_wan_path is not None:
        if folder_or_wan_path.is_file():
            wan_name = folder_or_wan_path.stem
            output_folder = folder_or_wan_path.parent / f"{wan_name}_frames"
        else:
            folder_name = folder_or_wan_path.name
            output_folder = folder_or_wan_path / f"{folder_name}_frames"
        output_folder.mkdir(parents=True, exist_ok=True)

    # Merge split 8bpp base files (animation-only + image-only)
    input_base_type = validation_info.get("base_type")

    if (
        base_sprite
        and base_validation_info
        and input_base_type in ("animation", "image")
    ):
        base_type = base_validation_info.get("base_type")
        if input_base_type == "animation" and base_type == "image":
            print("[INFO] Using images/palette from 8bpp image base sprite")
            max_memory_used = sprite.spr_info.max_memory_used
            sprite.frames = base_sprite.frames
            sprite.palette = base_sprite.palette
            sprite.spr_info = base_sprite.spr_info
            sprite.spr_info.max_memory_used = max_memory_used
            validation_info["requires_base_sprite"] = None
        elif input_base_type == "image" and base_type == "animation":
            print("[INFO] Using animations from 8bpp animation base sprite")
            sprite.metaframes = base_sprite.metaframes
            sprite.metaframe_groups = base_sprite.metaframe_groups
            sprite.anim_sequences = base_sprite.anim_sequences
            sprite.anim_groups = base_sprite.anim_groups
            sprite.spr_info.max_memory_used = base_sprite.spr_info.max_memory_used
            normal_mode = any(mf.image_index >= 0 for mf in sprite.metaframes)
            validation_info["requires_base_sprite"] = None

    requires_base_sprite = validation_info.get("requires_base_sprite")
    uses_base_sprite = (
        requires_base_sprite in ("image", "4bpp") and base_sprite is not None
    )

    # Palette layout: with base=[base|unique], without base=[unique only]
    shared_palette = base_sprite.palette if base_sprite else None
    is_8bpp_sprite = sprite.spr_info.is_8bpp_sprite == 1

    if uses_base_sprite and shared_palette is not None and len(shared_palette) > 0:
        global_palette = np.array(shared_palette, dtype=np.uint8)

        if sprite.palette.size > 0:
            palette_slot_base = (
                PALETTE_SLOT_8BPP_BASE if is_8bpp_sprite else PALETTE_SLOT_4BPP_BASE
            )
            unique_palette_start = palette_slot_base * PALETTE_SLOT_COLOR_COUNT * 3
            unique_palette_size = len(sprite.palette)
            unique_palette_end = unique_palette_start + unique_palette_size

            if unique_palette_end > 768:  # 256 colors * 3 bytes
                raise ValueError(
                    f"Merged palette uses {unique_palette_end // 3} colors, "
                    "exceeding the 256 color limit (Base + Unique combined)."
                )

            if unique_palette_end <= len(global_palette):
                global_palette[unique_palette_start:unique_palette_end] = sprite.palette
            else:
                extended_palette = np.zeros(unique_palette_end, dtype=np.uint8)
                extended_palette[: len(global_palette)] = global_palette
                extended_palette[unique_palette_start:unique_palette_end] = (
                    sprite.palette
                )
                global_palette = extended_palette
    elif sprite.palette.size > 0:
        global_palette = sprite.palette
    else:
        global_palette = np.zeros(PALETTE_SLOT_RGB_COUNT, dtype=np.uint8)

    tile_map, all_layers_list = reconstruct_frames(
        sprite,
        normal_mode,
        output_folder,
        avoid_overlap,
        global_palette,
        uses_base_sprite,
    )

    if output_folder is not None:
        if DEBUG:
            debug_output_folder = output_folder / "DEBUG"
            debug_output_folder.mkdir(parents=True, exist_ok=True)
            if not normal_mode and tile_map is not None:
                save_tile_map(tile_map, global_palette, debug_output_folder)

        create_json_from_animation(sprite, output_folder)

    print(f"\n[OK] Frames Generated Successfully")

    return all_layers_list, global_palette


def fg_process_single_folder(
    folder_or_wan_path: Path, avoid_overlap="none", base_sprite_path=None
):
    """Process a single folder (with external files) or WAN file.

    Args:
        folder_or_wan_path: Path object to either a folder (with external files) or a .wan file
        avoid_overlap: Overlap handling mode ("none", "palette", "chunk")
        base_sprite_path: Optional path to load base_sprite for shared palette

    Returns:
        True if successful, False otherwise
    """
    if not folder_or_wan_path.exists():
        print(f"[ERROR] Path does not exist: {folder_or_wan_path}")
        return False

    print("=" * SEPARATOR_LINE_LENGTH)
    if folder_or_wan_path.is_file():
        print(f"[INFO] Processing WAN file: {folder_or_wan_path}")
    else:
        print(f"[INFO] Processing folder: {folder_or_wan_path}")

    print("=" * SEPARATOR_LINE_LENGTH)
    print()

    # Validate and load sprite
    try:
        sprite, validation_info = validate_external_input(
            folder_or_wan_path, raise_on_errors=False
        )
    except Exception as e:
        print(f"[ERROR] Validation error:\n{str(e)}")
        return False

    # Warn if base sprite is needed but not provided
    requires_base_sprite = validation_info["requires_base_sprite"]
    if requires_base_sprite and base_sprite_path is None:
        base_name, hint = BASE_SPRITE_INFO.get(
            requires_base_sprite, (requires_base_sprite, "")
        )
        print(
            f"[WARNING] Needs {base_name} base sprite — frames may be incomplete without it.\n"
        )
        if hint:
            print(f"[HINT] The {base_name} base is the {hint}.\n")

    # Load base_sprite if path provided
    base_sprite = None
    base_validation_info = None
    if base_sprite_path is not None:
        try:
            base_sprite, base_validation_info = validate_external_input(
                base_sprite_path, raise_on_errors=False
            )
            # Check if correct type of base sprite is provided
            # requires_base_sprite tells what type is needed, base_type tells what it IS
            base_type = base_validation_info.get("base_type")
            if requires_base_sprite and base_type != requires_base_sprite:
                expected_name, hint = BASE_SPRITE_INFO.get(
                    requires_base_sprite, (requires_base_sprite, "")
                )
                loaded_name, _ = (
                    BASE_SPRITE_INFO.get(base_type, ("not a base file", ""))
                    if base_type
                    else ("not a base file", "")
                )
                print(
                    f"[WARNING] Expected {expected_name} base sprite — provided file is {loaded_name}."
                )
                if hint:
                    print(f"[HINT] The {expected_name} base is the {hint}.\n")
                elif base_type is None:
                    hint_lines = [
                        f"  • {name} base — {loc}"
                        for name, loc in BASE_SPRITE_INFO.values()
                    ]
                    print(
                        "[HINT] Valid base sprites are:\n"
                        + "\n".join(hint_lines)
                        + "\n"
                    )
        except Exception as e:
            print(f"[WARNING] Could not load base_sprite from {base_sprite_path}: {e}")

    try:
        data = (
            sprite,
            base_sprite,
            folder_or_wan_path,
            avoid_overlap,
            validation_info,
            base_validation_info if base_sprite else None,
        )
        generate_frames_main(data)

        return True
    except Exception as e:
        print(f"[ERROR] Error during processing: {str(e)}")
        return False


def fg_process_multiple_folder(
    parent_folder: Path, avoid_overlap="none", base_sprite_path=None
):
    """Process multiple folders or WAN files in a parent folder.

    Args:
        parent_folder: Folder containing either:
            - Subfolders (each with external files or WAN files)
            - WAN files directly
        avoid_overlap: Overlap handling mode ("none", "palette", "chunk")
        base_sprite_path: Optional path to load base_sprite for shared palette
    """
    if not validate_path_exists_and_is_dir(parent_folder, "Parent folder"):
        return

    parent_path = parent_folder

    # Get all WAN files in parent folder
    all_wan_files = list(parent_path.glob("*.wan"))

    # Get all subfolders (exclude common output folders)
    subfolders = [
        f
        for f in parent_path.iterdir()
        if f.is_dir() and f.name not in {"frames", "DEBUG", "sprite"}
    ]

    items_to_process = []
    items_to_process.extend(all_wan_files)
    items_to_process.extend(subfolders)

    if not items_to_process:
        print(f"[ERROR] No WAN files or subfolders found in: {parent_path}")
        return

    print("=" * SEPARATOR_LINE_LENGTH)
    print(f"[INFO] Found {len(items_to_process)} item(s) to process")
    print("=" * SEPARATOR_LINE_LENGTH)
    print()

    success_count = 0
    failed_items = []

    for idx, item_path in enumerate(items_to_process):

        if idx > 0:
            print()

        success = fg_process_single_folder(
            folder_or_wan_path=item_path,
            avoid_overlap=avoid_overlap,
            base_sprite_path=base_sprite_path,
        )

        if success:
            success_count += 1
        else:
            failed_items.append(item_path.name)

    print()
    print("=" * SEPARATOR_LINE_LENGTH)
    print("[SUMMARY] PROCESSING SUMMARY")
    print("=" * SEPARATOR_LINE_LENGTH)
    print(f"[INFO] Total: {len(items_to_process)}")
    print(f"[INFO] Successful: {success_count}")
    print(f"[INFO] Failed: {len(failed_items)}")

    if failed_items:
        print("\n[ERROR] Failed items:")
        for item in failed_items:
            print(f"   • {item}")

    print("=" * SEPARATOR_LINE_LENGTH)
