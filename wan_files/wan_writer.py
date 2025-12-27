"""
WAN file writer for creating .wan sprite files.
"""

import numpy as np
from pathlib import Path
from typing import List, Optional, Tuple
from .sprite import BaseSprite, AnimFrame
from .constants import Sir0, WanFormat
from .sir0 import wrap_sir0
from data import (
    write_uint32,
    write_uint16,
    write_uint8,
    write_int16,
    write_bytes_to_file,
    align_offset,
    pad_bytes,
    TILE_SIZE,
    TILE_AREA,
)


def _calculate_tile_dimensions(
    width: int, height: int, tile_size: int = TILE_SIZE
) -> Tuple[int, int]:
    """
    Calculate the number of tiles needed for given dimensions.

    Args:
        width: Image width in pixels
        height: Image height in pixels
        tile_size: Size of each tile (defaults to TILE_SIZE constant)

    Returns:
        Tuple of (num_tiles_x, num_tiles_y)
    """
    num_tiles_x = (width + tile_size - 1) // tile_size
    num_tiles_y = (height + tile_size - 1) // tile_size
    return num_tiles_x, num_tiles_y


def _is_zero_tile(data: bytes) -> bool:
    """Check if tile data is all zeros."""
    return all(b == 0 for b in data)


def _write_meta_frame_to_wan(mf, set_last_bit: bool = False) -> bytes:
    """
    Write meta-frame to WAN format bytes (10 bytes total).

    Args:
        mf: MetaFrame object
        set_last_bit: If True, set the last bit in XOffset (for last frame in group)

    Returns:
        Bytes representation of the meta-frame (10 bytes)
    """
    result = bytearray()

    # Special metaframe index (0xFFFF) must be encoded as -1 in signed int16
    img_idx = mf.image_index
    result.extend(write_int16(img_idx))

    result.extend(write_uint16(mf.unk0))

    resval = mf.resolution & 0xFF
    endbit_val = int(set_last_bit)

    # YOffset bit layout: [15:14]=res[1:0], [13]=YOffbit3, [12]=Mosaic, [11]=YOffbit5, [10]=YOffbit6, [9:0]=offsetY
    y_offset = (
        ((resval << 8) & 0xC000)
        | (mf.y_off_bit3 << 13)
        | (mf.mosaic << 12)
        | (mf.y_off_bit5 << 11)
        | (mf.y_off_bit6 << 10)
        | (mf.offset_y & 0x03FF)
    )
    result.extend(write_uint16(y_offset))

    # XOffset bit layout: [15:14]=res[3:2], [13]=vFlip, [12]=hFlip, [11]=Endbit, [10]=IsAbsPal, [9]=XOffbit7, [8:0]=offsetX
    x_offset = (
        ((resval << 12) & 0xC000)
        | (mf.v_flip << 13)
        | (mf.h_flip << 12)
        | (endbit_val << 11)
        | (mf.is_absolute_palette << 10)
        | (mf.x_off_bit7 << 9)
        | (mf.offset_x & 0x01FF)
    )
    result.extend(write_uint16(x_offset))

    result.extend(write_uint8(mf.memory_offset & 0xFF))
    result.extend(write_uint8(mf.palette_offset & 0xFF))

    return bytes(result)


class WANWriter:
    """Writer for WAN sprite files."""

    def __init__(self, sprite: BaseSprite):
        """Initialize writer with sprite data."""
        self.sprite = sprite
        self.output_buffer = bytearray()
        self.pointer_offsets: List[int] = []
        self.wan_subheader_pos = 0

        self.meta_frm_table_pos = 0
        self.p_offsets_table_pos = 0
        self.anim_grp_table_pos = 0
        self.imgs_tbl_pos = 0
        self.pal_pos = 0
        self.anim_info_pos = 0
        self.img_info_pos = 0

        self.meta_frame_group_offsets: List[int] = []
        self.comp_image_table_offsets: List[int] = []
        self.anim_sequence_offsets: dict = {}
        self.anim_sequences_list_offsets: List[int] = []

    def write(self, output_path: Optional[str] = None) -> bytes:
        """
        Write WAN file.

        Args:
            output_path: Optional path to write file to. If None, returns bytes.

        Returns:
            WAN file as bytes
        """

        self.output_buffer = bytearray()
        self.pointer_offsets = []

        self.output_buffer.extend(bytes(Sir0.HEADER_LEN))

        self._write_wan_content()

        wan_content = bytes(self.output_buffer[Sir0.HEADER_LEN :])
        wan_subheader_offset = self.wan_subheader_pos - Sir0.HEADER_LEN

        sir0_data = wrap_sir0(
            wan_content,
            subheader_offset=wan_subheader_offset,
            pointer_offsets=self.pointer_offsets,
        )

        if output_path:
            write_bytes_to_file(Path(output_path), sir0_data)

        return sir0_data

    def _is_image_base(self) -> bool:
        """Check if this is an image-only sprite (no animation data).

        Image-only sprites have frames but no metaframes or animation groups.
        Example: effect0292 which contains shared palette/images.
        """
        has_images = len(self.sprite.frames) > 0 or self.sprite.palette.size > 0
        has_animation = (
            bool(self.sprite.metaframes)
            or bool(self.sprite.anim_groups)
            or bool(self.sprite.anim_sequences)
        )
        return has_images and not has_animation

    def _is_animation_base(self) -> bool:
        """Check if this is an animation-only sprite (no image data).

        Animation-only sprites have metaframes/anim_groups but no frames or palette.
        Example: effect0000 which uses images from effect0292.
        """
        has_images = len(self.sprite.frames) > 0 or self.sprite.palette.size > 0
        has_animation = (
            bool(self.sprite.metaframes)
            or bool(self.sprite.anim_groups)
            or bool(self.sprite.anim_sequences)
        )
        return has_animation and not has_images

    def _write_wan_content(self) -> None:
        """Write WAN file content following GfxCrunch order: data blocks first, then info headers."""

        is_image_base = self._is_image_base()
        is_animation_base = self._is_animation_base()

        # Animation data blocks (skip for image-only sprites)
        if not is_image_base:
            self._write_meta_frames()
            self._write_anim_sequences()
            self._write_padding(4)

        # Image data blocks (skip for animation-only sprites)
        if not is_animation_base:
            self._write_frames()
            self._write_palette()

        # Pointer tables (skip as appropriate)
        if not is_image_base:
            self._write_meta_frame_group_ptr_table()
            self._write_particle_offsets()
            self._write_anim_sequence_ptr_table()
            self._write_anim_group_ptr_table()

        if not is_animation_base:
            self._write_comp_image_ptr_table()

        # Info headers (skip as appropriate)
        if not is_image_base:
            self._write_anim_info()

        if not is_animation_base:
            self._write_img_data_info()

        self._write_wan_subheader()  # Must be last (contains pointers to info headers)
        self._write_padding(16)

    def _write_wan_subheader(self) -> None:
        """Write WAN sub-header (called at the end after all data is written)."""

        self.wan_subheader_pos = len(self.output_buffer)

        anim_info_offset = self.anim_info_pos if self.anim_info_pos > 0 else 0
        img_info_offset = self.img_info_pos if self.img_info_pos > 0 else 0
        self._write_pointer(anim_info_offset)
        self._write_pointer(img_info_offset)
        self.output_buffer.extend(write_uint16(self.sprite.spr_info.sprite_type))
        self.output_buffer.extend(write_uint16(self.sprite.spr_info.unk12))

    def _write_anim_info(self) -> None:
        """Write animation info structure."""

        self.anim_info_pos = len(self.output_buffer)

        meta_frm_table_offset = (
            self.meta_frm_table_pos if self.meta_frm_table_pos > 0 else 0
        )
        p_offsets_table_offset = (
            self.p_offsets_table_pos if self.p_offsets_table_pos > 0 else 0
        )
        anim_grp_table_offset = (
            self.anim_grp_table_pos if self.anim_grp_table_pos > 0 else 0
        )

        self._write_pointer(meta_frm_table_offset)
        self._write_pointer(p_offsets_table_offset)
        self._write_pointer(anim_grp_table_offset)

        nb_anim_groups = len(self.sprite.anim_groups) if self.sprite.anim_groups else 0
        self.output_buffer.extend(write_uint16(nb_anim_groups))
        self.output_buffer.extend(write_uint16(self.sprite.spr_info.max_memory_used))
        self.output_buffer.extend(write_uint16(self.sprite.spr_info.unk7))
        self.output_buffer.extend(write_uint16(self.sprite.spr_info.unk8))
        self.output_buffer.extend(write_uint16(self.sprite.spr_info.unk9))
        self.output_buffer.extend(write_uint16(self.sprite.spr_info.unk10))

    def _write_img_data_info(self) -> None:
        """Write image data info structure."""

        self.img_info_pos = len(self.output_buffer)

        imgs_tbl_offset = self.imgs_tbl_pos if self.imgs_tbl_pos > 0 else 0
        pal_offset = self.pal_pos if self.pal_pos > 0 else 0
        self._write_pointer(imgs_tbl_offset)
        self._write_pointer(pal_offset)
        self.output_buffer.extend(write_uint16(self.sprite.spr_info.tiles_mode))
        self.output_buffer.extend(write_uint16(self.sprite.spr_info.is_8bpp_sprite))
        self.output_buffer.extend(write_uint16(self.sprite.spr_info.palette_slots_used))
        nb_imgs = len(self.sprite.frames)
        self.output_buffer.extend(write_uint16(nb_imgs))

    def _write_frames(self) -> None:
        """Write image frames."""

        frames_start_pos = len(self.output_buffer)
        frames = self.sprite.frames

        is_4bpp = self.sprite.spr_info.is_8bpp_sprite == 0

        for i, frame in enumerate(frames):
            z_index = 0
            if self.sprite.imgs_info and i < len(self.sprite.imgs_info):
                z_index = self.sprite.imgs_info[i].zindex

            self._write_compressed_frame(frame, z_index, is_4bpp)

    def _write_palette(self) -> None:
        """Write palette block (colors + palette info structure)."""

        if self.sprite.palette.size == 0:
            return

        palette_colors_pos = len(self.output_buffer)

        nb_colors = self.sprite.palette.size // 3

        palette_arr = np.zeros((nb_colors, 4), dtype=np.uint8)
        palette_arr[:, :3] = self.sprite.palette.reshape(
            nb_colors, 3
        )  # Copy RGB values
        palette_arr[:, 3] = 0x80

        self.output_buffer.extend(palette_arr.tobytes())

        self.pal_pos = len(self.output_buffer)

        self._write_pointer(palette_colors_pos)
        unk3 = self.sprite.spr_info.unk3
        max_colors_used = self.sprite.spr_info.max_colors_used
        unk4 = self.sprite.spr_info.unk4
        unk5 = self.sprite.spr_info.unk5

        self.output_buffer.extend(write_uint16(unk3))
        self.output_buffer.extend(write_uint16(max_colors_used))
        self.output_buffer.extend(write_uint16(unk4))
        self.output_buffer.extend(write_uint16(unk5))
        self.output_buffer.extend(write_uint32(0))

    def _write_meta_frames(self) -> None:
        """Write meta-frames block."""

        if not self.sprite.metaframes or not self.sprite.metaframe_groups:
            return

        metaframes = self.sprite.metaframes
        groups = self.sprite.metaframe_groups

        for group in groups:
            group_offset = len(self.output_buffer)
            self.meta_frame_group_offsets.append(group_offset)

            for frame_idx, mf_idx in enumerate(group.metaframes):
                if mf_idx < len(metaframes):
                    mf = metaframes[mf_idx]
                    is_last = frame_idx == len(group.metaframes) - 1

                    mf_bytes = _write_meta_frame_to_wan(mf, set_last_bit=is_last)
                    self.output_buffer.extend(mf_bytes)

    def _write_anim_sequences(self) -> None:
        """Write animation sequences block (deduplicated)."""

        if not self.sprite.anim_groups or not self.sprite.anim_sequences:
            return

        anim_sequences = self.sprite.anim_sequences
        anim_groups = self.sprite.anim_groups

        written_sequences = set()

        for group in anim_groups:
            for seq_idx in group.seqs_indexes:
                if seq_idx not in written_sequences:
                    seq_offset = len(self.output_buffer)
                    self.anim_sequence_offsets[seq_idx] = seq_offset
                    written_sequences.add(seq_idx)

                    if seq_idx < len(anim_sequences):
                        seq = anim_sequences[seq_idx]
                        for af in seq.frames:
                            self._write_anim_frame(af)
                        null_frame = AnimFrame()
                        self._write_anim_frame(null_frame)

    def _write_anim_frame(self, af: AnimFrame) -> None:
        """Write a single animation frame (12 bytes total)."""
        self.output_buffer.extend(write_uint16(af.frame_duration))
        self.output_buffer.extend(write_uint16(af.meta_frm_grp_index))
        self.output_buffer.extend(write_int16(af.spr_offset_x))
        self.output_buffer.extend(write_int16(af.spr_offset_y))
        self.output_buffer.extend(write_int16(af.shadow_offset_x))
        self.output_buffer.extend(write_int16(af.shadow_offset_y))

    def _write_meta_frame_group_ptr_table(self) -> None:
        """Write meta-frame group pointer table."""

        self.meta_frm_table_pos = len(self.output_buffer)

        for group_offset in self.meta_frame_group_offsets:
            self._write_pointer(group_offset)

    def _write_particle_offsets(self) -> None:
        """Write particle offsets block."""

        if not self.sprite.part_offsets:
            if self.sprite.spr_info.sprite_type == 1 and self.meta_frm_table_pos > 0:
                self.p_offsets_table_pos = self.meta_frm_table_pos
            else:
                self.p_offsets_table_pos = 0
            return

        self.p_offsets_table_pos = len(self.output_buffer)

        for offset in self.sprite.part_offsets:
            self.output_buffer.extend(write_int16(offset.offx))
            self.output_buffer.extend(write_int16(offset.offy))

    def _write_anim_sequence_ptr_table(self) -> None:
        """Write animation sequence pointer table."""

        if not self.sprite.anim_groups:
            return

        for group in self.sprite.anim_groups:
            if not group.seqs_indexes:
                self._write_pointer(0)
            else:
                seq_list_offset = len(self.output_buffer)
                self.anim_sequences_list_offsets.append(seq_list_offset)

                for seq_idx in group.seqs_indexes:
                    if seq_idx in self.anim_sequence_offsets:
                        seq_offset = self.anim_sequence_offsets[seq_idx]
                        self._write_pointer(seq_offset)
                    else:
                        self._write_pointer(0)

    def _write_anim_group_ptr_table(self) -> None:
        """Write animation group pointer table."""

        self.anim_grp_table_pos = len(self.output_buffer)
        if not self.sprite.anim_groups:
            return

        seq_list_iter = iter(self.anim_sequences_list_offsets)

        for group in self.sprite.anim_groups:
            if not group.seqs_indexes:
                self.output_buffer.extend(bytes(8))
            else:
                seq_list_offset = next(seq_list_iter, 0)
                self._write_pointer(seq_list_offset)
                self.output_buffer.extend(write_uint32(len(group.seqs_indexes)))

    def _write_comp_image_ptr_table(self) -> None:
        """Write compressed image pointer table."""

        self.imgs_tbl_pos = len(self.output_buffer)
        for img_offset in self.comp_image_table_offsets:
            self._write_pointer(img_offset)

    def _write_pointer(self, offset: int) -> None:
        """Write a pointer and track its offset for SIR0 encoding."""

        ptr_pos = len(self.output_buffer)
        self.output_buffer.extend(write_uint32(offset))
        if offset != 0:
            self.pointer_offsets.append(ptr_pos)

    def _write_padding(self, alignment: int) -> None:
        """
        Write padding bytes to align to the specified boundary.

        Args:
            alignment: Alignment boundary (e.g., 4 or 16)
        """

        bufflen = len(self.output_buffer)
        aligned_len = align_offset(bufflen, alignment)
        len_padding = aligned_len - bufflen
        if len_padding > 0:
            self.output_buffer.extend(pad_bytes(len_padding, WanFormat.PADDING_BYTE))

    def _convert_tiled_image_to_bytes(self, frame, is_4bpp: bool) -> bytes:
        """
        Convert tiled image pixels to bytes for writing.

        For 4bpp: Pack 2 pixels per byte (low nybble first)
        For 8bpp: 1 pixel per byte

        Args:
            frame: Frame to convert
            is_4bpp: True if 4bpp, False if 8bpp
        """
        pixels_2d = frame.pixels
        height, width = pixels_2d.shape

        num_tiles_x, num_tiles_y = _calculate_tile_dimensions(width, height, TILE_SIZE)
        num_tiles = num_tiles_x * num_tiles_y

        pixels = np.zeros(num_tiles * TILE_AREA, dtype=np.uint8)
        tile_idx = 0

        for tile_y in range(num_tiles_y):
            y_start = tile_y * TILE_SIZE
            y_end = min(y_start + TILE_SIZE, height)
            for tile_x in range(num_tiles_x):
                x_start = tile_x * TILE_SIZE
                x_end = min(x_start + TILE_SIZE, width)
                tile = pixels_2d[y_start:y_end, x_start:x_end]

                if tile.shape == (TILE_SIZE, TILE_SIZE):
                    pixels[tile_idx * TILE_AREA : (tile_idx + 1) * TILE_AREA] = (
                        tile.flatten()
                    )
                else:
                    padded_tile = np.zeros((TILE_SIZE, TILE_SIZE), dtype=np.uint8)
                    padded_tile[: tile.shape[0], : tile.shape[1]] = tile
                    pixels[tile_idx * TILE_AREA : (tile_idx + 1) * TILE_AREA] = (
                        padded_tile.flatten()
                    )

                tile_idx += 1
        pixels_len = len(pixels)

        if is_4bpp:
            arr = pixels & 0x0F
            result_size = (pixels_len + 1) // 2
            result = np.zeros(result_size, dtype=np.uint8)

            # WAN files use reversed pixel order: low nybble first
            pairs = pixels_len // 2
            if pairs > 0:
                low = arr[::2][:pairs]
                high = arr[1::2][:pairs]
                result[:pairs] = (low | (high << 4)).astype(np.uint8)
            if pixels_len % 2:
                result[pairs] = arr[pairs * 2] & 0x0F
            result = result.tobytes()
        else:
            result = pixels.tobytes()

        return bytes(result)

    def _build_tile_aligned_entries(self, pixel_data: bytes, is_4bpp: bool) -> list:
        """
        Build assembly table entries with tile-aligned zero-fill compression.

        In 4bpp mode: 1 tile = 64 pixels = 32 bytes
        In 8bpp mode: 1 tile = 64 pixels = 64 bytes

        Only creates zero-fill entries for complete tiles that are all zeros.
        This matches the original WAN format pattern.

        Returns:
            List of entry dicts with keys: is_zero_fill, pixamt, data_bytes
        """
        tile_bytes = 32 if is_4bpp else 64  # Bytes per tile
        entries = []
        pos = 0
        data_len = len(pixel_data)

        while pos < data_len:
            # Check if we're at a tile boundary and have a complete zero tile
            if pos % tile_bytes == 0 and pos + tile_bytes <= data_len:
                # Check if entire tile is zeros
                tile_data = pixel_data[pos : pos + tile_bytes]
                if _is_zero_tile(tile_data):
                    # Count consecutive zero tiles
                    zero_start = pos
                    while pos + tile_bytes <= data_len:
                        next_tile = pixel_data[pos : pos + tile_bytes]
                        if not _is_zero_tile(next_tile):
                            break
                        pos += tile_bytes

                    entries.append(
                        {
                            "is_zero_fill": True,
                            "pixamt": pos - zero_start,
                            "data_bytes": None,
                        }
                    )
                    continue

            # Not a zero tile - collect data until next tile boundary with all zeros
            data_start = pos
            while pos < data_len:
                # If at tile boundary, check if next tile is all zeros
                if pos % tile_bytes == 0 and pos + tile_bytes <= data_len:
                    next_tile = pixel_data[pos : pos + tile_bytes]
                    if _is_zero_tile(next_tile):
                        break  # Stop collecting data, zero tile follows
                pos += 1

            if pos > data_start:
                entries.append(
                    {
                        "is_zero_fill": False,
                        "pixamt": pos - data_start,
                        "data_bytes": pixel_data[data_start:pos],
                    }
                )

        return entries

    def _write_compressed_frame(self, frame, img_z_index: int, is_4bpp: bool) -> None:
        """Write a single compressed frame with optional tile-aligned zero-fill compression."""

        img_bytes = self._convert_tiled_image_to_bytes(frame, is_4bpp)

        # Only apply tile-aligned compression for sprite_type == 1 (monster sprites)
        # sprite_type == 0 files (object, effects, etc.) don't use compression
        use_compression = self.sprite.spr_info.sprite_type == 1

        if use_compression:
            raw_entries = self._build_tile_aligned_entries(img_bytes, is_4bpp)
        else:
            # No compression - single entry for all data
            raw_entries = [
                {
                    "is_zero_fill": False,
                    "pixamt": len(img_bytes),
                    "data_bytes": img_bytes,
                }
            ]

        img_begin_offset = len(self.output_buffer)

        pixel_strips = bytearray()
        asm_table = []

        for raw_entry in raw_entries:
            if raw_entry["is_zero_fill"]:
                asm_table.append(
                    {
                        "pixelsrc": 0,
                        "pixamt": raw_entry["pixamt"],
                        "unk14": 0,
                        "z_index": img_z_index,
                        "is_zero_fill": True,
                    }
                )
            else:
                data_offset = len(pixel_strips)
                pixel_strips.extend(raw_entry["data_bytes"])

                asm_table.append(
                    {
                        "pixelsrc": data_offset,
                        "pixamt": raw_entry["pixamt"],
                        "unk14": 0,
                        "z_index": img_z_index,
                        "is_zero_fill": False,
                    }
                )

        self.output_buffer.extend(pixel_strips)

        asm_table_offset = len(self.output_buffer)
        self.comp_image_table_offsets.append(asm_table_offset)

        for entry in asm_table:
            if entry["is_zero_fill"]:
                self.output_buffer.extend(write_uint32(0))
            else:
                entry["pixelsrc"] += img_begin_offset
                ptr_pos = len(self.output_buffer)
                self.pointer_offsets.append(ptr_pos)
                self.output_buffer.extend(write_uint32(entry["pixelsrc"]))

            self.output_buffer.extend(write_uint16(entry["pixamt"]))
            self.output_buffer.extend(write_uint16(entry["unk14"]))
            self.output_buffer.extend(write_uint32(entry["z_index"]))

        # Null terminator entry
        self.output_buffer.extend(write_uint32(0))
        self.output_buffer.extend(write_uint16(0))
        self.output_buffer.extend(write_uint16(0))
        self.output_buffer.extend(write_uint32(0))
