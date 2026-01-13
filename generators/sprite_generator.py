import json
import xxhash
import colorsys
import numpy as np
from pathlib import Path
from PIL import Image, ImageDraw
from data import (
    DEBUG,
    read_json_file,
    validate_path_exists_and_is_dir,
    SEPARATOR_LINE_LENGTH,
    DEFAULT_ANIMATION_DURATION,
    TILE_SIZE,
    normalize_string,
)
from wan_files import (
    generate_wan,
    BaseSprite,
    MetaFrame,
    MetaFrameGroup,
    AnimFrame,
    AnimationSequence,
    SpriteAnimationGroup,
    ImageInfo,
    MetaFrameRes,
    TiledImage,
    CHUNK_SIZES,
    ORIENTATION_VALUES,
    WanFormat,
    PALETTE_SLOT_COLOR_COUNT,
    PALETTE_SLOT_RGB_COUNT,
    PALETTE_OFFSET_BASE,
    PALETTE_SLOT_4BPP_BASE,
    PALETTE_SLOT_8BPP_BASE,
)
from external_files import write_external_files
from .constants import (
    SPRITE_CATEGORY_LIMITS,
    TRANSPARENT_CHUNK_ID,
    COORDINATE_CENTER_X,
    COORDINATE_CENTER_Y,
    DEFAULT_UNK_VALUE,
    SPRITE_CATEGORY_CONFIGS,
)


def validate_sg_input_folder(folder: Path):
    """Validate sprite generator input folder and load images.

    Args:
        folder: Path to folder containing PNG frame images

    Returns:
        Tuple of (images_dict, common_image_size, original_shared_palette,
        max_colors_used, available_frames)
    """
    print("[VALIDATING] Validating images in folder...\n")

    images_dict = {}
    common_image_size = None
    should_pad = False
    padding_height = 0
    padding_width = 0
    original_shared_palette = None
    max_colors_used = None
    available_frames = set()

    png_files = [
        f for f in folder.iterdir() if f.is_file() and f.suffix.lower() == ".png"
    ]

    if not png_files:
        print("[ERROR] No png images found")
        return (
            images_dict,
            common_image_size,
            original_shared_palette,
            max_colors_used,
            available_frames,
        )

    for file_name in png_files:
        name_without_ext = file_name.stem
        parts = name_without_ext.split("-")
        errors_for_file = []

        # Validate filename format: Frame-N-Layer-M
        if (
            len(parts) != 4
            or parts[0].lower() != "frame"
            or not parts[1].isdigit()
            or parts[2].lower() != "layer"
            or not parts[3].isdigit()
        ):
            print(f"[WARNING] {file_name.name}:")
            print(f"    • Invalid name format")
            continue

        frame_num = int(parts[1])
        layer_num = int(parts[3])

        image_path = folder / file_name

        try:
            with Image.open(image_path) as img:
                # Validate indexed palette mode
                if img.mode != "P":
                    errors_for_file.append("Not an indexed image")
                else:
                    if original_shared_palette is None:
                        original_shared_palette = img.getpalette()

                        max_colors_used = len(original_shared_palette) // 3

                    if img.getpalette() != original_shared_palette:
                        errors_for_file.append("Palette differs from other images.")

                # Validate 8x8 tile alignment
                width, height = img.size
                if common_image_size is None:
                    common_image_size = (width, height)
                    padding_width = (width + 7) // 8 * 8 - width
                    padding_height = (height + 7) // 8 * 8 - height
                    should_pad = padding_width > 0 or padding_height > 0
                    if DEBUG and should_pad:
                        print(
                            f"Padding from {width}x{height} to "
                            f"{width+padding_width}x{height+padding_height}\n"
                        )
                elif (width, height) != common_image_size:
                    errors_for_file.append(
                        f"Size {width}x{height}. Expected: {common_image_size[0]}x{common_image_size[1]}"
                    )

                # Print all errors for this file
                if errors_for_file:
                    print(f"[ERROR] {file_name.name}:")
                    for error in errors_for_file:
                        print(f"    • {error}")
                    print()
                else:
                    numpy_array = np.asarray(img, dtype=np.uint8)

                    if should_pad:
                        numpy_array = np.pad(
                            numpy_array,
                            ((0, padding_height), (0, padding_width)),
                            mode="constant",
                            constant_values=0,
                        )

                        img = Image.fromarray(numpy_array, mode="P")
                        img.putpalette(original_shared_palette)
                        img.info["transparency"] = 0

                    reduced_numpy = numpy_array % PALETTE_SLOT_COLOR_COUNT
                    mask = reduced_numpy != 0
                    groups_used = np.unique(
                        numpy_array[mask] // PALETTE_SLOT_COLOR_COUNT
                    )

                    if groups_used.size > 1:
                        print(
                            f"[INFO] {file_name.name}: Splitting into palette layers {groups_used.tolist()}\n"
                        )

                        for palette_group in groups_used:
                            group_mask = (
                                numpy_array // PALETTE_SLOT_COLOR_COUNT
                            ) == palette_group

                            split_array = np.where(group_mask, numpy_array, 0)
                            split_reduced = split_array % PALETTE_SLOT_COLOR_COUNT

                            sub_layer_name = f"frame-{frame_num}-layer-{layer_num}.{palette_group}.png"

                            split_img = Image.fromarray(split_array, mode="P")
                            split_img.putpalette(img.getpalette())

                            split_img.info["transparency"] = 0

                            images_dict[sub_layer_name] = {
                                "image_data": split_img.convert("RGBA"),
                                "tile_hash_dict": create_tile_hash_dict(
                                    split_reduced, False
                                ),
                                "frame_layer_palette_tuple": (
                                    frame_num,
                                    layer_num,
                                    int(palette_group),
                                ),
                                "is_transparent": False,
                            }
                    else:
                        is_transparent = False

                        if groups_used.size == 0:
                            groups_used = np.array([0], dtype=np.uint8)
                            is_transparent = True

                        images_dict[file_name.name] = {
                            "image_data": img.convert("RGBA"),
                            "tile_hash_dict": create_tile_hash_dict(
                                reduced_numpy, is_transparent
                            ),
                            "frame_layer_palette_tuple": (
                                frame_num,
                                layer_num,
                                int(groups_used[0]),
                            ),
                            "is_transparent": is_transparent,
                        }

                    available_frames.add(frame_num)

        except Exception as e:
            print(f"[ERROR] {file_name.name}: Error reading file - {str(e)}")
            continue

    if not images_dict:
        print("\n[ERROR] No valid images found")
    else:
        common_image_size = (
            common_image_size[0] + padding_width,
            common_image_size[1] + padding_height,
        )

    return (
        images_dict,
        common_image_size,
        original_shared_palette,
        max_colors_used,
        sorted(available_frames),
    )


def create_tile_hash_dict(image_array, is_transparent):
    tile_hash_dict = {}

    if is_transparent:
        return tile_hash_dict

    image_height, image_width = image_array.shape
    tiles_y = image_height // TILE_SIZE
    tiles_x = image_width // TILE_SIZE

    cropped = image_array[: tiles_y * TILE_SIZE, : tiles_x * TILE_SIZE]
    tiles = cropped.reshape(tiles_y, TILE_SIZE, tiles_x, TILE_SIZE)
    tiles = np.ascontiguousarray(tiles.transpose(0, 2, 1, 3))

    variants = {
        "original": tiles,
        "flip_h": np.flip(tiles, axis=3),
        "flip_v": np.flip(tiles, axis=2),
        "flip_both": np.flip(tiles, (2, 3)),
    }

    for orient_name, tile_array in variants.items():
        flat_tiles = tile_array.reshape(-1, TILE_SIZE * TILE_SIZE)
        flat_tiles = np.ascontiguousarray(flat_tiles)

        buf = flat_tiles.tobytes()
        tile_size_bytes = TILE_SIZE * TILE_SIZE * flat_tiles.itemsize

        orientation_hashes = np.fromiter(
            (
                xxhash.xxh3_64(buf[i : i + tile_size_bytes]).intdigest()
                for i in range(0, len(buf), tile_size_bytes)
            ),
            dtype=np.uint64,
            count=flat_tiles.shape[0],
        )

        orientation_hashes = orientation_hashes.reshape(tiles_y, tiles_x)

        orientation_numpy = tile_array.transpose(0, 2, 1, 3).reshape(
            tiles_y * TILE_SIZE, tiles_x * TILE_SIZE
        )

        tile_hash_dict[orient_name] = {
            "tile_hashes": orientation_hashes,
            "numpy_array": orientation_numpy,
        }

    return tile_hash_dict


def get_oriented_chunks_data(
    tile_hash_dict,
    chunk_x,
    chunk_y,
    chunk_width,
    chunk_height,
    min_density,
):
    unique_hashes = {}
    seen_hashes = set()

    tiles_height, tiles_width = chunk_height // TILE_SIZE, chunk_width // TILE_SIZE

    image_numpy = tile_hash_dict["original"]["numpy_array"]
    chunk_numpy = image_numpy[
        chunk_y : chunk_y + chunk_height, chunk_x : chunk_x + chunk_width
    ]

    # Reshape to tile grid for density check
    tiles = chunk_numpy[: tiles_height * TILE_SIZE, : tiles_width * TILE_SIZE]
    tiles = tiles.reshape(tiles_height, TILE_SIZE, tiles_width, TILE_SIZE).swapaxes(
        1, 2
    )

    filled_mask = (tiles != 0).any(axis=(2, 3))
    row_density = filled_mask.sum(axis=1) / tiles_width
    col_density = filled_mask.sum(axis=0) / tiles_height

    if not ((row_density >= min_density).all() and (col_density >= min_density).all()):
        return None

    # Compute chunk hashes for all orientations
    tiles_x, tiles_y = chunk_x // TILE_SIZE, chunk_y // TILE_SIZE

    for orient_name, orient_data in tile_hash_dict.items():
        numpy_array = orient_data["numpy_array"]
        tile_hashes = orient_data["tile_hashes"]

        sub_hashes = tile_hashes[
            tiles_y : tiles_y + tiles_height,
            tiles_x : tiles_x + tiles_width,
        ]

        hash_obj = xxhash.xxh3_64()
        hash_obj.update(np.asarray(sub_hashes.shape, dtype=np.int32).tobytes())
        hash_obj.update(sub_hashes.tobytes())
        chunk_hash = hash_obj.intdigest()

        if chunk_hash not in seen_hashes:
            chunk_numpy_orient = numpy_array[
                chunk_y : chunk_y + chunk_height,
                chunk_x : chunk_x + chunk_width,
            ]
            unique_hashes[orient_name] = (chunk_hash, chunk_numpy_orient.copy())
            seen_hashes.add(chunk_hash)

    return unique_hashes


def get_relative_orientation(match_orient, saved_orient):
    FLAGS_ORIENT = {v: k for k, v in ORIENTATION_VALUES.items()}

    mh, mv = ORIENTATION_VALUES[match_orient]
    sh, sv = ORIENTATION_VALUES[saved_orient]

    oh = mh ^ sh
    ov = mv ^ sv

    return FLAGS_ORIENT[(oh, ov)]


def get_inside_coordinates(x, y, chunk_width, chunk_height):
    used_coords = set()
    for cy in range(y, y + chunk_height, TILE_SIZE):
        for cx in range(x, x + chunk_width, TILE_SIZE):
            used_coords.add((cx, cy))
    return used_coords


def populate_frames_data(sprite: BaseSprite, chunk_track_dict, is_8bpp=False):
    for chunk_info in chunk_track_dict.values():
        frame = TiledImage()
        pixels = chunk_info["chunk_numpy_array"].copy()
        if is_8bpp:
            # Shift non-zero pixel indices to 2nd palette slot (add 16), keep 0 as transparent
            pixels = np.where(pixels > 0, pixels + PALETTE_SLOT_COLOR_COUNT, pixels)
        frame.pixels = pixels
        sprite.frames.append(frame)

        info = ImageInfo()
        info.zindex = 0
        sprite.imgs_info.append(info)


def format_chunk_track_dict(chunk_track_dict):
    grouped_chunks = {}

    for chunk_id, chunk_data in enumerate(chunk_track_dict.values()):
        # Parse main chunk info
        frame_num, layer_num, palette_num = chunk_data["frame_layer_palette_tuple"]
        coords = chunk_data["coordinates"]
        dim = chunk_data["dimension"]
        orientation_original = ORIENTATION_VALUES.get("original", (0, 0))

        # Main chunk with precomputed sort key
        main_chunk = {
            "chunk_id": chunk_id,
            "coordinates": coords,
            "dimension": dim,
            "orientation": orientation_original,
            "layer": layer_num,
            "palette": palette_num,
            "_sort_key": (-layer_num, coords[0], coords[1]),
        }

        grouped_chunks.setdefault(frame_num, []).append(main_chunk)

        # Duplicates
        for dup in chunk_data.get("duplicates", []):
            dup_frame, dup_layer, dup_palette = dup["frame_layer_palette_tuple"]
            dup_chunk = {
                "chunk_id": chunk_id,
                "coordinates": dup["coordinates"],
                "dimension": dim,
                "orientation": ORIENTATION_VALUES.get(dup["orientation"], (0, 0)),
                "layer": dup_layer,
                "palette": dup_palette,
                "_sort_key": (-dup_layer, dup["coordinates"][0], dup["coordinates"][1]),
            }

            grouped_chunks.setdefault(dup_frame, []).append(dup_chunk)

    # Build final dict sorted by frame and chunk
    formatted_dict = {}
    for frame_num in sorted(grouped_chunks):
        chunks = grouped_chunks[frame_num]
        chunks.sort(key=lambda c: c["_sort_key"])
        formatted_dict[f"Frame-{frame_num}"] = chunks

    return formatted_dict


def pad_palette_to_slots(palette_data, target_rgb_len):
    """Pad palette to fill complete slots (multiples of PALETTE_SLOT_RGB_COUNT)."""
    palette_list = list(palette_data)
    # Pad to at least target_rgb_len, then to complete slot
    if len(palette_list) < target_rgb_len:
        palette_list += [0] * (target_rgb_len - len(palette_list))
    remainder = len(palette_list) % PALETTE_SLOT_RGB_COUNT
    if remainder:
        palette_list += [0] * (PALETTE_SLOT_RGB_COUNT - remainder)
    return np.array(palette_list, dtype=np.uint8)


def populate_palette(
    sprite: BaseSprite,
    original_shared_palette,
    used_base_palette=False,
    is_8bpp_sprite=False,
    is_base_sprite=False,
):
    base_rgb = (
        PALETTE_SLOT_8BPP_BASE if is_8bpp_sprite else PALETTE_SLOT_4BPP_BASE
    ) * PALETTE_SLOT_RGB_COUNT

    if is_base_sprite:
        # Base sprites: use [0:base_rgb], pad to fill all base slots
        sprite.palette = pad_palette_to_slots(
            original_shared_palette[:base_rgb], base_rgb
        )
    elif used_base_palette:
        # Standalone with base palette: use [base_rgb:], pad to complete slot
        sprite.palette = pad_palette_to_slots(original_shared_palette[base_rgb:], 0)
    else:
        # Standalone: use full palette, pad to complete slot
        sprite.palette = pad_palette_to_slots(original_shared_palette, 0)


def calc_memory_blocks(width, height, is_8bpp):
    # 4bpp: 256 pixels per block, 8bpp: 128 pixels per block
    block_size = 128 if is_8bpp else 256
    return ((height * width) + block_size - 1) // block_size


def build_global_chunk_offsets(formatted_chunk_track_dict, is_8bpp):
    chunk_dimensions = {}
    for chunks in formatted_chunk_track_dict.values():
        for chunk in chunks:
            chunk_id = chunk["chunk_id"]
            if chunk_id not in chunk_dimensions:
                chunk_dimensions[chunk_id] = chunk["dimension"]

    offsets = {}
    current = 0
    for chunk_id in sorted(chunk_dimensions.keys()):
        offsets[chunk_id] = current
        w, h = chunk_dimensions[chunk_id]
        current += calc_memory_blocks(w, h, is_8bpp)

    return offsets, current


def populate_metaframes_data(
    sprite: BaseSprite,
    sprite_category,
    formatted_chunk_track_dict,
    initial_coordinate,
    use_tiles_mode=False,
    is_8bpp_sprite=False,
    used_base_palette=False,
):
    frame_memory_usage = []

    # For tiles mode: pre-calculate global chunk memory offsets
    global_offsets = {}
    total_memory = 0
    if use_tiles_mode:
        global_offsets, total_memory = build_global_chunk_offsets(
            formatted_chunk_track_dict, is_8bpp_sprite
        )

    for chunks in formatted_chunk_track_dict.values():
        group = MetaFrameGroup()
        local_offsets = {}
        local_memory = 0

        for chunk in chunks:
            chunk_id = chunk["chunk_id"]
            coords = chunk["coordinates"]
            dim = chunk["dimension"]

            # Determine image_index and memory_offset
            if use_tiles_mode:
                image_index = WanFormat.SPECIAL_META_FRAME_ID
                memory_offset = global_offsets[chunk_id]
            elif chunk_id in local_offsets:
                image_index = WanFormat.SPECIAL_META_FRAME_ID
                memory_offset = local_offsets[chunk_id]
            else:
                image_index = chunk_id
                memory_offset = local_memory
                local_offsets[chunk_id] = memory_offset
                local_memory += calc_memory_blocks(dim[0], dim[1], is_8bpp_sprite)

            # Create metaframe
            mf = MetaFrame()
            mf.unk0 = DEFAULT_UNK_VALUE
            mf.image_index = image_index
            mf.offset_x = initial_coordinate[0] + coords[0]
            mf.offset_y = initial_coordinate[1] + coords[1]

            palette_slot_base = 0

            if not used_base_palette:
                palette_slot_base = (
                    PALETTE_SLOT_8BPP_BASE if is_8bpp_sprite else PALETTE_SLOT_4BPP_BASE
                )

            mf.palette_offset = (
                PALETTE_OFFSET_BASE
                + (chunk["palette"] + palette_slot_base) * PALETTE_SLOT_COLOR_COUNT
            )

            mf.memory_offset = memory_offset
            mf.resolution = MetaFrameRes.RESOLUTION_TO_ENUM.get(
                tuple(dim), MetaFrameRes._INVALID
            )
            mf.v_flip = chunk["orientation"][0]
            mf.h_flip = chunk["orientation"][1]
            mf.mosaic = 0
            mf.is_absolute_palette = 1
            mf.bool_y_off_bit3 = int(is_8bpp_sprite)
            mf.const0_x_off_bit7 = mf.const0_y_off_bit5 = mf.const0_y_off_bit6 = 0

            sprite.metaframes.append(mf)
            group.metaframes.append(len(sprite.metaframes) - 1)

        sprite.metaframe_groups.append(group)
        frame_memory_usage.append(total_memory if use_tiles_mode else local_memory)

    return frame_memory_usage


def populate_animations_data(sprite: BaseSprite, available_frames, animation_group):
    # Create animation sequences
    for anim in animation_group:
        seq = AnimationSequence()
        for frame_data in anim:
            image_no = frame_data["frame"]
            image_index = available_frames.index(image_no)
            duration = frame_data["duration"]

            af = AnimFrame()
            af.frame_duration = duration
            af.meta_frm_grp_index = image_index
            af.spr_offset_x = 0
            af.spr_offset_y = 0
            af.shadow_offset_x = 0
            af.shadow_offset_y = 0

            seq.frames.append(af)

        sprite.anim_sequences.append(seq)

    # Create animation group
    group = SpriteAnimationGroup()
    for i in range(len(animation_group)):
        group.seqs_indexes.append(i)
    sprite.anim_groups.append(group)


def populate_sprite_info(
    sprite: BaseSprite,
    max_memory_used,
    use_tiles_mode=False,
    is_8bpp_sprite=False,
    sprite_type=DEFAULT_UNK_VALUE,
    is_bool_unk3_true=False,
    unk4=DEFAULT_UNK_VALUE,
    unk5=DEFAULT_UNK_VALUE,
    is_bool_unk9_true=False,
):
    colors_in_palette = sprite.palette.shape[0] // 3
    info = sprite.spr_info
    info.bool_unk3 = int(is_bool_unk3_true)  # Boolean Flag
    info.max_colors_used = colors_in_palette
    info.unk4 = unk4  # ['0x0', '0x10']
    info.unk5 = unk5  # ['0x0', '0xFF', '0x10D']
    info.max_memory_used = max_memory_used
    info.const0_unk7 = DEFAULT_UNK_VALUE  # Always 0
    info.const0_unk8 = DEFAULT_UNK_VALUE  # Always 0
    info.bool_unk9 = int(is_bool_unk9_true)  # Boolean Flag
    info.const0_unk10 = DEFAULT_UNK_VALUE  # Always 0
    info.sprite_type = sprite_type  # ['0x0', '0x1', '0x2']
    info.is_8bpp_sprite = int(is_8bpp_sprite)
    info.tiles_mode = int(use_tiles_mode)
    info.palette_slots_used = (
        1 if is_8bpp_sprite else colors_in_palette // PALETTE_SLOT_COLOR_COUNT
    )
    info.const0_unk12 = DEFAULT_UNK_VALUE  # Always 0


def save_unique_chunk_in_dict(
    chunk_track_dict,
    hash_key,
    chunk_x,
    chunk_y,
    chunk_width,
    chunk_height,
    image_name,
    flp_tuple,
    numpy_array,
    coords_inside_chunk,
):

    chunk_track_dict[hash_key] = {
        "coordinates": (chunk_x, chunk_y),
        "dimension": (chunk_width, chunk_height),
        "source_image": image_name,
        "frame_layer_palette_tuple": flp_tuple,
        "duplicates": [],
        "chunk_numpy_array": numpy_array,
        "inside_coordinates": coords_inside_chunk,
    }

    if DEBUG:
        print(
            f"[SAVE] Unique Chunk {hash_key} from {image_name} at ({chunk_x}, {chunk_y})"
        )


def save_duplicate_chunk_in_dict(
    chunk_track_dict,
    hash_key,
    chunk_x,
    chunk_y,
    orient_name,
    image_name,
    flp_tuple,
):
    chunk_track_dict[hash_key]["duplicates"].append(
        {
            "coordinates": (chunk_x, chunk_y),
            "orientation": orient_name,
            "source_image": image_name,
            "frame_layer_palette_tuple": flp_tuple,
        }
    )

    if DEBUG:
        print(
            f"[APPEND] Duplicate Chunk of {hash_key} in {image_name} at "
            f"({chunk_x}, {chunk_y}) orientation={orient_name}"
        )


def save_transparent_frames_chunk(chunk_track_dict, frame_layes_name_dict):

    transparent_frames = [
        (frame, layers[0][0])
        for frame, layers in frame_layes_name_dict.items()
        if all(is_transparent for _, is_transparent in layers)
    ]

    numpy_array = np.zeros((TILE_SIZE, TILE_SIZE), dtype=np.uint8)
    for frame, layer_name in transparent_frames:
        if not chunk_track_dict.get(TRANSPARENT_CHUNK_ID):
            save_unique_chunk_in_dict(
                chunk_track_dict,
                TRANSPARENT_CHUNK_ID,
                0,
                0,
                TILE_SIZE,
                TILE_SIZE,
                layer_name,
                (frame, 0, 0),
                numpy_array,
                (0, 0),
            )
        else:
            save_duplicate_chunk_in_dict(
                chunk_track_dict,
                TRANSPARENT_CHUNK_ID,
                0,
                0,
                "original",
                layer_name,
                (frame, 0, 0),
            )


def save_remaining_chunks(
    images_dict, chunk_track_dict, image_height, image_width, min_row_column_density
):
    unique_chunk_counter = 0
    for chunk_width, chunk_height in CHUNK_SIZES:
        if chunk_height > image_height or chunk_width > image_width:
            continue

        print(
            f"\n[SCANNING] Scanning for remaining chunks of size ({chunk_width}x{chunk_height})..."
        )

        for image_name, image_info in images_dict.items():
            current_image_tile_hash_dict = image_info["tile_hash_dict"]
            current_image_valid_coordinates = image_info["valid_coordinates"]
            current_image_flp_tuple = image_info["frame_layer_palette_tuple"]

            sorted_valid_coordinates = sorted(
                current_image_valid_coordinates, key=lambda coord: (coord[1], coord[0])
            )

            for x, y in sorted_valid_coordinates:
                if x + chunk_width > image_width or y + chunk_height > image_height:
                    continue

                # check for used area
                coordinates_inside_current_chunk = get_inside_coordinates(
                    x, y, chunk_width, chunk_height
                )

                if not coordinates_inside_current_chunk.issubset(
                    current_image_valid_coordinates
                ):
                    continue

                current_chunk_oriented_data = get_oriented_chunks_data(
                    current_image_tile_hash_dict,
                    x,
                    y,
                    chunk_width,
                    chunk_height,
                    min_row_column_density,
                )

                if not current_chunk_oriented_data:
                    continue

                coords_inside_chunk = get_inside_coordinates(
                    x, y, chunk_width, chunk_height
                )

                current_image_valid_coordinates.difference_update(coords_inside_chunk)

                matched = False

                original_hash = current_chunk_oriented_data["original"][0]
                original_numpy = current_chunk_oriented_data["original"][1]

                for orient_name, (
                    oriented_chunk_hash,
                    oriented_chunk_numpy,
                ) in current_chunk_oriented_data.items():

                    existing_entry = chunk_track_dict.get(oriented_chunk_hash)

                    if existing_entry is not None:
                        if np.array_equal(
                            existing_entry["chunk_numpy_array"], oriented_chunk_numpy
                        ):
                            save_duplicate_chunk_in_dict(
                                chunk_track_dict,
                                oriented_chunk_hash,
                                x,
                                y,
                                orient_name,
                                image_name,
                                current_image_flp_tuple,
                            )
                        else:
                            # Hash collision - save as unique
                            save_unique_chunk_in_dict(
                                chunk_track_dict,
                                unique_chunk_counter,
                                x,
                                y,
                                chunk_width,
                                chunk_height,
                                image_name,
                                current_image_flp_tuple,
                                original_numpy,
                                coords_inside_chunk,
                            )
                            unique_chunk_counter += 1
                        matched = True
                        break

                if not matched:
                    save_unique_chunk_in_dict(
                        chunk_track_dict,
                        original_hash,
                        x,
                        y,
                        chunk_width,
                        chunk_height,
                        image_name,
                        current_image_flp_tuple,
                        original_numpy,
                        coords_inside_chunk,
                    )


def scan_for_repeated_chunks(
    images_dict,
    chunk_track_dict,
    image_height,
    image_width,
    min_row_column_density,
    current_image_name,
    chunk_width,
    chunk_height,
    tracking_hash_map,
    loop_no,
):
    current_image_info = images_dict[current_image_name]
    current_image_tile_hash_dict = current_image_info["tile_hash_dict"]
    current_image_flp_tuple = current_image_info["frame_layer_palette_tuple"]
    current_image_valid_coords = current_image_info["valid_coordinates"]

    sorted_valid_coordinates = sorted(
        current_image_valid_coords, key=lambda coord: (coord[1], coord[0])
    )

    for x, y in sorted_valid_coordinates:
        if x + chunk_width > image_width or y + chunk_height > image_height:
            continue

        coords_inside_current_chunk = get_inside_coordinates(
            x, y, chunk_width, chunk_height
        )

        if not coords_inside_current_chunk.issubset(current_image_valid_coords):
            continue

        current_chunk_oriented_data = get_oriented_chunks_data(
            current_image_tile_hash_dict,
            x,
            y,
            chunk_width,
            chunk_height,
            min_row_column_density,
        )

        if not current_chunk_oriented_data:
            continue

        matched = False

        for orient_name, (
            oriented_chunk_hash,
            oriented_chunk_numpy,
        ) in current_chunk_oriented_data.items():

            if loop_no == 1 and oriented_chunk_hash not in tracking_hash_map:
                continue

            if loop_no == 2 and (
                oriented_chunk_hash not in tracking_hash_map
                and oriented_chunk_hash not in chunk_track_dict
            ):
                continue

            # Retrieve the original chunk entry
            if oriented_chunk_hash in tracking_hash_map:
                original_chunk_entry = tracking_hash_map[oriented_chunk_hash]
            else:
                original_chunk_entry = chunk_track_dict[oriented_chunk_hash]
            original_chunk_numpy = original_chunk_entry["chunk_numpy_array"]
            original_chunk_image_name = original_chunk_entry["source_image"]
            ox, oy = original_chunk_entry["coordinates"]
            original_chunk_flp_tuple = original_chunk_entry["frame_layer_palette_tuple"]
            coords_inside_original_chunk = original_chunk_entry["inside_coordinates"]

            original_image_valid_coords = images_dict[original_chunk_image_name][
                "valid_coordinates"
            ]

            # Skip overlapping or invalid regions
            if (
                original_chunk_image_name == current_image_name
                and coords_inside_original_chunk & coords_inside_current_chunk
            ):
                continue

            if not np.array_equal(original_chunk_numpy, oriented_chunk_numpy):
                continue

            # Valid duplicate found
            matched = True

            # Check if ANY orientation of this chunk is already in chunk_track_dict
            saved_orient_hash = None
            saved_orient_name = None
            original_orient_name = None
            for o_orient_name, (o_chunk_hash, _) in current_chunk_oriented_data.items():
                if o_chunk_hash in chunk_track_dict:
                    saved_orient_hash = o_chunk_hash
                    saved_orient_name = o_orient_name
                    original_orient_name = get_relative_orientation(
                        orient_name, saved_orient_name
                    )
                    break

            if saved_orient_hash is None:
                # No orientation saved yet - save the original chunk as unique
                original_image_valid_coords.difference_update(
                    coords_inside_original_chunk
                )
                save_unique_chunk_in_dict(
                    chunk_track_dict,
                    oriented_chunk_hash,
                    ox,
                    oy,
                    chunk_width,
                    chunk_height,
                    original_chunk_image_name,
                    original_chunk_flp_tuple,
                    original_chunk_numpy,
                    coords_inside_original_chunk,
                )
            else:
                # Some orientation already saved
                # Check if the original chunk is the saved entry itself
                saved_entry = chunk_track_dict[saved_orient_hash]
                is_original_the_saved_entry = saved_entry[
                    "source_image"
                ] == original_chunk_image_name and saved_entry["coordinates"] == (
                    ox,
                    oy,
                )

                if not is_original_the_saved_entry:
                    original_already_added = False
                    if "duplicates" in saved_entry:
                        for dup in saved_entry["duplicates"]:
                            if dup["source_image"] == original_chunk_image_name and dup[
                                "coordinates"
                            ] == (ox, oy):
                                original_already_added = True
                                break

                    if not original_already_added:
                        original_image_valid_coords.difference_update(
                            coords_inside_original_chunk
                        )
                        save_duplicate_chunk_in_dict(
                            chunk_track_dict,
                            saved_orient_hash,
                            ox,
                            oy,
                            original_orient_name,
                            original_chunk_image_name,
                            original_chunk_flp_tuple,
                        )

                # Update oriented_chunk_hash to use the saved orientation
                oriented_chunk_hash = saved_orient_hash
                orient_name = saved_orient_name

            # Record current as duplicate
            current_image_valid_coords.difference_update(coords_inside_current_chunk)

            save_duplicate_chunk_in_dict(
                chunk_track_dict,
                oriented_chunk_hash,
                x,
                y,
                orient_name,
                current_image_name,
                current_image_flp_tuple,
            )

            break  # Stop checking other orientations

        # If chunk wasn't found in hash map
        if not matched:
            # check if it's clashing duplicate
            orientation_hashes = {h for h, _ in current_chunk_oriented_data.values()}

            if tracking_hash_map.keys().isdisjoint(orientation_hashes):
                current_chunk_hash, current_chunk_numpy = current_chunk_oriented_data[
                    "original"
                ]
                tracking_hash_map[current_chunk_hash] = {
                    "source_image": current_image_name,
                    "coordinates": (x, y),
                    "frame_layer_palette_tuple": current_image_flp_tuple,
                    "inside_coordinates": coords_inside_current_chunk,
                    "chunk_numpy_array": current_chunk_numpy,
                }


def save_repeated_chunks(
    images_dict,
    frame_layes_name_dict,
    chunk_track_dict,
    image_height,
    image_width,
    intra_scan,
    inter_scan,
    scan_chunk_sizes,
    min_row_column_density,
):
    if intra_scan:
        for frame_no, frame_layers in frame_layes_name_dict.items():

            print(f"\n[SCANNING] Scanning Frame-{frame_no} for repeated chunks...")

            for chunk_width, chunk_height in scan_chunk_sizes:

                if chunk_height > image_height or chunk_width > image_width:
                    continue

                chunk_size_specific_dict = {}

                for layer_name, _ in frame_layers:

                    scan_for_repeated_chunks(
                        images_dict,
                        chunk_track_dict,
                        image_height,
                        image_width,
                        min_row_column_density,
                        layer_name,
                        chunk_width,
                        chunk_height,
                        chunk_size_specific_dict,
                        loop_no=1,
                    )

    if inter_scan:
        for chunk_width, chunk_height in scan_chunk_sizes:

            print(
                f"\n[SCANNING] Scanning across images for chunks of size ({chunk_width}x{chunk_height})..."
            )

            if chunk_height > image_height or chunk_width > image_width:
                continue

            chunk_size_specific_dict = {}

            for current_image_name in images_dict:

                scan_for_repeated_chunks(
                    images_dict,
                    chunk_track_dict,
                    image_height,
                    image_width,
                    min_row_column_density,
                    current_image_name,
                    chunk_width,
                    chunk_height,
                    chunk_size_specific_dict,
                    loop_no=2,
                )


def annotate_chunks(
    images_dict, chunk_track_dict, total_unique_chunks, debug_output_dir: Path
):

    # Generate distinct colors for chunk visualization
    distinct_colors = []
    for i in range(total_unique_chunks):
        hue = i / total_unique_chunks
        lightness = 0.5
        saturation = 0.9
        rgb = colorsys.hls_to_rgb(hue, lightness, saturation)
        rgb = tuple(int(c * 255) for c in rgb)
        distinct_colors.append(rgb)

    for image_name, image_info in images_dict.items():
        image_data = image_info["image_data"].copy()
        draw = ImageDraw.Draw(image_data)

        # Draw rectangles for each chunk on source images
        for index, chunk_info in enumerate(chunk_track_dict.values()):
            color = distinct_colors[index]

            # Check if this chunk's original is from current image
            if chunk_info.get("source_image") == image_name:
                x, y = chunk_info["coordinates"]
                chunk_width, chunk_height = chunk_info["dimension"]
                draw.rectangle(
                    [x, y, x + chunk_width - 1, y + chunk_height - 1],
                    outline=color,
                    width=1,
                )

            # Draw rectangles for duplicates in this image
            for duplicate in chunk_info["duplicates"]:
                if duplicate.get("source_image") == image_name:
                    dup_x, dup_y = duplicate["coordinates"]
                    chunk_width, chunk_height = chunk_info["dimension"]
                    draw.rectangle(
                        [
                            dup_x,
                            dup_y,
                            dup_x + chunk_width - 1,
                            dup_y + chunk_height - 1,
                        ],
                        outline=color,
                        width=1,
                    )

        output_path = (
            debug_output_dir
            / f"{image_name[:-4]}-Palette-{image_info['frame_layer_palette_tuple'][2]}-annotated.png"
        )
        image_data.save(output_path)

    print(f"\n[OK] Annotated images saved to: {debug_output_dir}\n")


def do_debug_exclusive_stuff(
    images_dict,
    chunk_track_dict,
    formatted_chunk_track_dict,
    total_unique_chunks,
    input_folder: Path,
):

    debug_output_dir = input_folder / "DEBUG"
    if DEBUG:
        debug_output_dir.mkdir(parents=True, exist_ok=True)

    # annotate chunks
    annotate_chunks(
        images_dict, chunk_track_dict, total_unique_chunks, debug_output_dir
    )

    # Build sanitized copies (no mutation)
    sanitized_chunk_track_dict = {
        key: {
            k: v
            for k, v in value.items()
            if k not in {"chunk_numpy_array", "inside_coordinates"}
        }
        for key, value in chunk_track_dict.items()
    }

    sanitized_images_dict = {
        key: {
            k: v
            for k, v in value.items()
            if k not in {"image_data", "tile_hash_dict", "valid_coordinates"}
        }
        for key, value in images_dict.items()
    }

    def safe_json_dumps(obj) -> str:
        try:
            return json.dumps(obj, indent=4, ensure_ascii=False, default=str)
        except TypeError:
            return json.dumps(str(obj), indent=4, ensure_ascii=False)

    # save debug info
    DEBUG_LOG_OUTPUT = debug_output_dir / "log.py"
    with open(DEBUG_LOG_OUTPUT, "w", encoding="utf-8") as f:
        f.write("Chunk_Track_Dict = ")
        f.write(safe_json_dumps(sanitized_chunk_track_dict))
        f.write("\n\nFormatted_Chunk_Track_Dict = ")
        f.write(safe_json_dumps(formatted_chunk_track_dict))
        f.write("\n\nImages_Dict = ")
        f.write(safe_json_dumps(sanitized_images_dict))


def give_sprite_overview(
    max_memory_used,
    frame_memory_usage,
    sprite,
    total_unique_chunks,
    formatted_chunk_track_dict,
    sprite_category,
):
    limits = SPRITE_CATEGORY_LIMITS.get(
        sprite_category, SPRITE_CATEGORY_LIMITS["4bpp_standalone"]
    )

    print("\nSprite Info:")
    print(f"[INFO] Maximum Memory Used by Animation: {max_memory_used}")

    if max_memory_used > limits["base_game_memory"]:
        print(
            f"[WARNING] High memory usage — may cause in-game issues."
            f"\n[INFO] Base-game sprites only use up to {limits['base_game_memory']} memory."
        )

    total_colors_used = sprite.palette.shape[0] // 3

    print(f"[INFO] Total Colors Used: {total_colors_used}")

    print(f"[INFO] Total Unique Chunks: {total_unique_chunks}")
    if total_unique_chunks > limits["base_game_unique_chunks"]:
        print(
            f"[WARNING] High total chunk count — may cause in-game issues."
            f"\n[INFO] Base-game sprites use up to {limits['base_game_unique_chunks']} unique chunks"
        )

    print("\nFrames Info: ")
    for frame_no, (frame, chunks) in enumerate(formatted_chunk_track_dict.items()):
        total_chunks = len(chunks)
        print(
            f"[INFO] {frame}: Total Chunks = {total_chunks} and Memory Usage = {frame_memory_usage[frame_no]}"
        )
        if total_chunks > limits["max_chunks_per_frame"]:
            print(
                f"[ERROR] {frame} uses {total_chunks} chunks — exceeds in-game render limit."
                f"\n[INFO] Allowed maximum chunks per frame: {limits['max_chunks_per_frame']}"
            )
        elif total_chunks > limits["base_game_chunks_per_frame"]:
            print(
                f"[WARNING] {frame} uses {total_chunks} chunks — may cause in-game issues."
                f"\n[INFO] Base-game frames use up to {limits['base_game_chunks_per_frame']} chunks"
            )


def generate_sprite_main(data):
    """Generate sprite from validated input data.

    Args:
        data: Tuple containing (input_folder, images_dict, original_shared_palette,
              max_colors_used, image_height, image_width, available_frames,
              min_row_column_density, displace_sprite, animation_group,
              scan_chunk_sizes, intra_scan, inter_scan, export_as_wan,
              sprite_category, custom_properties)
    """
    print("[GENERATING] Starting Sprite Generation...")

    (
        input_folder,
        images_dict,
        original_shared_palette,
        max_colors_used,
        image_height,
        image_width,
        available_frames,
        min_row_column_density,
        displace_sprite,
        animation_group,
        scan_chunk_sizes,
        intra_scan,
        inter_scan,
        export_as_wan,
        sprite_category,
        custom_properties,
    ) = data

    sprite_category = normalize_string(sprite_category)

    if sprite_category not in SPRITE_CATEGORY_CONFIGS:
        sprite_category = "4bpp_standalone"

    cfg = SPRITE_CATEGORY_CONFIGS[sprite_category]
    tiles = cfg["tiles_mode"]
    use_tiles_mode = (
        custom_properties.get("use_tiles_mode", False) if tiles is None else tiles
    )
    is_8bpp_sprite = cfg["is_8bpp"]
    sprite_type = cfg["sprite_type"]
    is_bool_unk3_true = cfg["bool_unk3"]
    unk4 = cfg["unk4"]
    unk5 = cfg["unk5"]
    is_bool_unk9_true = cfg["bool_unk9"]
    cfg_used_base_palette = cfg.get("used_base_palette", None)
    used_base_palette = (
        custom_properties.get("used_base_palette", False)
        if cfg_used_base_palette is None
        else cfg_used_base_palette
    )

    # Validate color count
    is_base_sprite = sprite_category in {"8bpp_base", "4bpp_base"}
    palette_slot_base = (
        PALETTE_SLOT_8BPP_BASE if is_8bpp_sprite else PALETTE_SLOT_4BPP_BASE
    )

    if is_base_sprite:
        # Base sprites can only use colors in the base palette slots
        max_colors_allowed = palette_slot_base * PALETTE_SLOT_COLOR_COUNT
        if max_colors_used > max_colors_allowed:
            raise ValueError(
                f"Base sprite uses {max_colors_used} colors, exceeding the {max_colors_allowed} base palette limit."
            )
    elif not used_base_palette:
        # Standalone sprites without base palette can use remaining slots
        max_palette_slots = 16 - palette_slot_base
        max_colors_allowed = max_palette_slots * PALETTE_SLOT_COLOR_COUNT
        if max_colors_used > max_colors_allowed:
            raise ValueError(
                f"Sprite uses {max_colors_used} colors, exceeding the {max_colors_allowed} unique color limit.\n"
                f"If using a base sprite palette, check 'Base Palette' to reference those colors."
            )

    valid_coordinates = get_inside_coordinates(0, 0, image_width, image_height)

    for file_name in images_dict:
        if images_dict[file_name]["is_transparent"]:
            images_dict[file_name]["valid_coordinates"] = set()
            if DEBUG:
                print(f"\n[WARNING] {file_name} is Transparent, No Valid Coordinate\n")
        else:
            images_dict[file_name]["valid_coordinates"] = valid_coordinates.copy()

    chunk_track_dict = {}

    frame_layes_name_dict = {}

    for image_name, image_info in images_dict.items():
        frame_num, _, _ = image_info["frame_layer_palette_tuple"]
        is_transparent = image_info["is_transparent"]
        frame_layes_name_dict.setdefault(frame_num, []).append(
            (image_name, is_transparent)
        )

    save_repeated_chunks(
        images_dict,
        frame_layes_name_dict,
        chunk_track_dict,
        image_height,
        image_width,
        intra_scan,
        inter_scan,
        scan_chunk_sizes,
        min_row_column_density,
    )

    save_remaining_chunks(
        images_dict, chunk_track_dict, image_height, image_width, min_row_column_density
    )

    save_transparent_frames_chunk(chunk_track_dict, frame_layes_name_dict)

    print("\nGenerated File Info:")

    sprite = BaseSprite()

    populate_frames_data(sprite, chunk_track_dict, is_8bpp_sprite)

    populate_palette(
        sprite,
        original_shared_palette,
        used_base_palette,
        is_8bpp_sprite,
        is_base_sprite,
    )

    top_left_x = round(COORDINATE_CENTER_X + displace_sprite[0] - image_width / 2)
    top_left_y = round(COORDINATE_CENTER_Y + displace_sprite[1] - image_height / 2)
    initial_coordinate = [top_left_x, top_left_y]

    formatted_chunk_track_dict = format_chunk_track_dict(chunk_track_dict)
    frame_memory_usage = populate_metaframes_data(
        sprite,
        sprite_category,
        formatted_chunk_track_dict,
        initial_coordinate,
        use_tiles_mode,
        is_8bpp_sprite,
        used_base_palette,
    )

    max_memory_used = max(frame_memory_usage)

    if max_memory_used > 255:
        raise ValueError(
            f"Memory overflow: max memory ({max_memory_used}) exceeds 255."
        )

    # Populate animations
    populate_animations_data(sprite, available_frames, animation_group)

    # Populate sprite info
    populate_sprite_info(
        sprite,
        max_memory_used,
        use_tiles_mode,
        is_8bpp_sprite,
        sprite_type,
        is_bool_unk3_true,
        unk4,
        unk5,
        is_bool_unk9_true,
    )

    # Export helper function
    def export_sprite(sprite_to_export, output_name, export_as_wan):
        sprite_to_export.validate(raise_on_errors=True)
        if export_as_wan:
            output_path = input_folder / f"{output_name}.wan"
            generate_wan(sprite_to_export, output_path)
        else:
            output_path = input_folder / f"{output_name}"
            write_external_files(sprite_to_export, output_path)

    # Export as WAN or external files
    folder_name = input_folder.name

    if sprite_category == "8bpp_base":
        # Create animation_base with animation data
        animation_base = BaseSprite()
        animation_base.metaframes = sprite.metaframes
        animation_base.metaframe_groups = sprite.metaframe_groups
        animation_base.anim_sequences = sprite.anim_sequences
        animation_base.anim_groups = sprite.anim_groups
        animation_base.spr_info.max_memory_used = sprite.spr_info.max_memory_used

        # Set animation_base spr_info from config
        cfg = SPRITE_CATEGORY_CONFIGS["8bpp_base"]
        animation_base.spr_info.tiles_mode = int(cfg["animation_base_tiles_mode"])
        animation_base.spr_info.is_8bpp_sprite = int(cfg["animation_base_is_8bpp"])
        animation_base.spr_info.sprite_type = cfg["animation_base_sprite_type"]
        animation_base.spr_info.bool_unk3 = int(cfg["animation_base_bool_unk3"])
        animation_base.spr_info.unk4 = cfg["animation_base_unk4"]
        animation_base.spr_info.unk5 = cfg["animation_base_unk5"]
        animation_base.spr_info.bool_unk9 = int(cfg["animation_base_bool_unk9"])

        # Clear animation data and max_memory_used from sprite (now image_base)
        sprite.metaframes = []
        sprite.metaframe_groups = []
        sprite.anim_sequences = []
        sprite.anim_groups = []
        sprite.spr_info.max_memory_used = 0

        # Export both
        export_sprite(sprite, f"{folder_name}_image_base", export_as_wan)
        export_sprite(animation_base, f"{folder_name}_animation_base", export_as_wan)
    else:
        export_sprite(sprite, f"{folder_name}_sprite", export_as_wan)

    total_unique_chunks = len(chunk_track_dict)

    # Give Overview
    give_sprite_overview(
        max_memory_used,
        frame_memory_usage,
        sprite,
        total_unique_chunks,
        formatted_chunk_track_dict,
        sprite_category,
    )

    # Debug Stuff
    if DEBUG:
        do_debug_exclusive_stuff(
            images_dict,
            chunk_track_dict,
            formatted_chunk_track_dict,
            total_unique_chunks,
            input_folder,
        )

    print(f"\n[OK] Sprite Generated Successfully")


def sg_process_single_folder(
    folder_path: Path,
    min_row_column_density=0.5,
    displace_sprite=[0, 0],
    intra_scan=True,
    inter_scan=True,
    scan_chunk_sizes=None,
    animation_group=None,
    export_as_wan=False,
    sprite_category="4bpp_standalone",
    custom_properties=None,
):
    """Process a single folder to generate a sprite.

    Args:
        folder_path: Path to folder containing PNG frame images
        min_row_column_density: Minimum density threshold (0.0-1.0)
        displace_sprite: [x, y] displacement offset
        intra_scan: Enable intra-frame chunk scanning
        inter_scan: Enable inter-frame chunk scanning
        scan_chunk_sizes: List of chunk size tuples to scan
        animation_group: Animation sequence data
        export_as_wan: Export as WAN file instead of external files
        sprite_category: Sprite category ("4bpp_standalone", "8bpp_standalone", etc.)
        custom_properties: Dict of custom sprite properties (includes used_base_palette)

    Returns:
        True if successful, False otherwise
    """

    if not validate_path_exists_and_is_dir(folder_path, "Folder"):
        return False

    print("=" * SEPARATOR_LINE_LENGTH)
    print(f"[INFO] Processing folder: {folder_path}")
    print("=" * SEPARATOR_LINE_LENGTH)
    print()

    # Validate folder
    (
        images_dict,
        common_image_size,
        original_shared_palette,
        max_colors_used,
        available_frames,
    ) = validate_sg_input_folder(folder_path)

    if (
        not images_dict
        or common_image_size is None
        or original_shared_palette is None
        or not available_frames
    ):
        print(f"[ERROR] Validation failed for folder: {folder_path}")
        return False

    print("[OK] Validation Successful.\n")

    # Determine animation_group: use provided, then check config.json, then default
    current_animation_group = animation_group

    if current_animation_group is None:
        # Try to load from config.json
        config_path = folder_path / "config.json"
        config_data = read_json_file(config_path)
        if config_data is not None:
            current_animation_group = config_data.get("animation_group", None)
            if current_animation_group is not None and not current_animation_group:
                print(
                    f"[WARNING] config.json found but animation_group is empty, using default"
                )
                current_animation_group = None

        # Use default if still None
        if current_animation_group is None:
            current_animation_group = [
                [
                    {"frame": frame_num, "duration": DEFAULT_ANIMATION_DURATION}
                    for frame_num in available_frames
                ]
            ]

    try:
        image_width, image_height = common_image_size

        # Use provided chunk sizes or default to all
        current_chunk_sizes = scan_chunk_sizes if scan_chunk_sizes else CHUNK_SIZES

        data = (
            folder_path,
            images_dict,
            original_shared_palette,
            max_colors_used,
            image_height,
            image_width,
            available_frames,
            min_row_column_density,
            displace_sprite,
            current_animation_group,
            current_chunk_sizes,
            intra_scan,
            inter_scan,
            export_as_wan,
            sprite_category,
            custom_properties,
        )

        generate_sprite_main(data)
        return True

    except Exception as e:
        print(f"[ERROR] Error processing {folder_path}: {str(e)}")
        return False


def sg_process_multiple_folder(
    parent_folder: Path,
    min_row_column_density=0.5,
    displace_sprite=[0, 0],
    intra_scan=True,
    inter_scan=True,
    scan_chunk_sizes=None,
    export_as_wan=False,
    sprite_category="4bpp_standalone",
    custom_properties=None,
):
    """Process multiple folders to generate sprites.

    Args:
        parent_folder: Folder containing subfolders with PNG frame images
        min_row_column_density: Minimum density threshold (0.0-1.0)
        displace_sprite: [x, y] displacement offset
        intra_scan: Enable intra-frame chunk scanning
        inter_scan: Enable inter-frame chunk scanning
        scan_chunk_sizes: List of chunk size tuples to scan
        export_as_wan: Export as WAN file instead of external files
        sprite_category: Sprite category ("4bpp_standalone", "8bpp_standalone", etc.)
        custom_properties: Dict of custom sprite properties (includes used_base_palette)
    """
    if not validate_path_exists_and_is_dir(parent_folder, "Parent folder"):
        return

    subfolders = [f for f in parent_folder.iterdir() if f.is_dir()]

    if not subfolders:
        print(f"[ERROR] No subfolders found in: {parent_folder}")
        return

    print("=" * SEPARATOR_LINE_LENGTH)
    print(f"[INFO] Found {len(subfolders)} folder(s) to process")
    print("=" * SEPARATOR_LINE_LENGTH)
    print()

    success_count = 0
    failed_folders = []

    for idx, subfolder_path in enumerate(subfolders):

        if idx > 0:
            print()

        success = sg_process_single_folder(
            folder_path=subfolder_path,
            min_row_column_density=min_row_column_density,
            displace_sprite=displace_sprite,
            intra_scan=intra_scan,
            inter_scan=inter_scan,
            scan_chunk_sizes=scan_chunk_sizes,
            export_as_wan=export_as_wan,
            sprite_category=sprite_category,
            custom_properties=custom_properties,
        )

        if success:
            success_count += 1
        else:
            failed_folders.append(subfolder_path.name)

    print()
    print("=" * SEPARATOR_LINE_LENGTH)
    print("[SUMMARY] PROCESSING SUMMARY")
    print("=" * SEPARATOR_LINE_LENGTH)
    print(f"[INFO] Total: {len(subfolders)}")
    print(f"[INFO] Successful: {success_count}")
    print(f"[INFO] Failed: {len(failed_folders)}")

    if failed_folders:
        print("\n[ERROR] Failed folders:")
        for folder in failed_folders:
            print(f"   • {folder}")

    print("=" * SEPARATOR_LINE_LENGTH)
