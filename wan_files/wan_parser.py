"""
WAN file parser for reading .wan sprite files.
"""

from typing import List, Optional, Tuple
import numpy as np

from .sir0 import read_sir0_header, validate_sir0_header
from .sprite import (
    BaseSprite,
    MetaFrame,
    MetaFrameGroup,
    AnimationSequence,
    AnimFrame,
    SpriteAnimationGroup,
    SprOffParticle,
    ImageInfo,
    TiledImage,
)
from .constants import WanFormat
from data import (
    read_uint32,
    read_uint16,
    read_uint8,
    read_int16,
    enum_res_to_integer,
    TILE_SIZE,
    TILE_AREA,
)


class WANSubHeader:
    """WAN sub-header structure."""

    def __init__(self):
        self.ptr_animinfo = 0
        self.ptr_imginfo = 0
        self.sprite_type = 0
        self.const0_unk12 = 0

    @classmethod
    def read_from_bytes(cls, data: bytes, offset: int) -> "WANSubHeader":
        """Read WAN sub-header from bytes."""
        header = cls()
        header.ptr_animinfo = read_uint32(data, offset)
        header.ptr_imginfo = read_uint32(data, offset + 4)
        header.sprite_type = read_uint16(data, offset + 8)
        header.const0_unk12 = read_uint16(data, offset + 10)
        return header


class WANAnimInfo:
    """WAN animation info structure."""

    def __init__(self):
        self.ptr_meta_frm_table = 0
        self.ptr_p_offsets_table = 0
        self.ptr_anim_grp_table = 0
        self.nb_anim_groups = 0
        self.max_memory_used = 0
        self.const0_unk7 = 0
        self.const0_unk8 = 0
        self.bool_unk9 = 0
        self.const0_unk10 = 0

    @classmethod
    def read_from_bytes(cls, data: bytes, offset: int) -> "WANAnimInfo":
        """Read animation info from bytes."""
        info = cls()
        info.ptr_meta_frm_table = read_uint32(data, offset)
        info.ptr_p_offsets_table = read_uint32(data, offset + 4)
        info.ptr_anim_grp_table = read_uint32(data, offset + 8)
        info.nb_anim_groups = read_uint16(data, offset + 12)
        info.max_memory_used = read_uint16(data, offset + 14)
        info.const0_unk7 = read_uint16(data, offset + 16)
        info.const0_unk8 = read_uint16(data, offset + 18)
        info.bool_unk9 = read_uint16(data, offset + 20)
        info.const0_unk10 = read_uint16(data, offset + 22)
        return info


class WANImgDataInfo:
    """WAN image data info structure."""

    def __init__(self):
        self.ptr_imgs_tbl = 0
        self.ptr_pal = 0
        self.tiles_mode = 0
        self.is_8bpp_sprite = 0
        self.palette_slots_used = 0
        self.nb_imgs_tbl_ptr = 0

    @classmethod
    def read_from_bytes(cls, data: bytes, offset: int) -> "WANImgDataInfo":
        """Read image data info from bytes."""
        info = cls()
        info.ptr_imgs_tbl = read_uint32(data, offset)
        info.ptr_pal = read_uint32(data, offset + 4)
        info.tiles_mode = read_uint16(data, offset + 8)
        info.is_8bpp_sprite = read_uint16(data, offset + 10)
        info.palette_slots_used = read_uint16(data, offset + 12)
        info.nb_imgs_tbl_ptr = read_uint16(data, offset + 14)
        return info


class WANPalInfo:
    """WAN palette info structure."""

    def __init__(self):
        self.ptr_pal = 0
        self.bool_unk3 = 0
        self.max_colors_used = 0
        self.unk4 = 0
        self.unk5 = 0
        self.null_bytes = 0

    @classmethod
    def read_from_bytes(cls, data: bytes, offset: int) -> "WANPalInfo":
        """Read palette info from bytes."""
        info = cls()
        info.ptr_pal = read_uint32(data, offset)
        info.bool_unk3 = read_uint16(data, offset + 4)
        info.max_colors_used = read_uint16(data, offset + 6)
        info.unk4 = read_uint16(data, offset + 8)
        info.unk5 = read_uint16(data, offset + 10)
        info.null_bytes = read_uint32(data, offset + 12)
        return info


class ImgAsmTblEntry:
    """Image assembly table entry."""

    def __init__(self):
        self.pixelsrc = 0
        self.pixamt = 0
        self.unk14 = 0
        self.z_index = 0

    @classmethod
    def read_from_bytes(cls, data: bytes, offset: int) -> "ImgAsmTblEntry":
        """Read assembly table entry from bytes."""
        entry = cls()
        entry.pixelsrc = read_uint32(data, offset)
        entry.pixamt = read_uint16(data, offset + 4)
        entry.unk14 = read_uint16(data, offset + 6)
        entry.z_index = read_uint32(data, offset + 8)
        return entry

    def is_null(self) -> bool:
        """Check if this is a null entry."""
        return self.pixelsrc == 0 and self.pixamt == 0 and self.z_index == 0


def _get_resolution_from_offsets(xoffset: int, yoffset: int) -> int:
    """Extract resolution enum from offset values (first 2 bits of each)."""
    y_bits = (yoffset & 0xC000) >> 8
    x_bits = (xoffset & 0xC000) >> 12
    return y_bits | x_bits


class WANParser:
    """Parser for WAN sprite files."""

    def __init__(self, rawdata: bytes):
        """Initialize parser with raw WAN file data."""
        self.rawdata = rawdata
        self.sir0_header: Optional[Tuple[int, int, int, int]] = (
            None  # (magic, subheader_ptr, ptr_offset_list_ptr, padding)
        )
        self.wan_header: Optional[WANSubHeader] = None
        self.wan_anim_info: Optional[WANAnimInfo] = None
        self.wan_img_data_info: Optional[WANImgDataInfo] = None
        self.wan_pal_info: Optional[WANPalInfo] = None

    def parse(self, is_4bpp: bool) -> BaseSprite:
        """Parse sprite as 4bpp or 8bpp.

        Args:
            is_4bpp: True for 4bpp, False for 8bpp
        """
        sprite = BaseSprite()
        self._parse_common(sprite)
        self._read_images(sprite, is_4bpp=is_4bpp)
        return sprite

    def _read_headers(self) -> None:
        """Read all headers."""
        if self.sir0_header is not None:
            return

        magic, subheader_ptr, ptr_offset_list_ptr, padding = read_sir0_header(
            self.rawdata, 0
        )
        self.sir0_header = (magic, subheader_ptr, ptr_offset_list_ptr, padding)

        if not validate_sir0_header(magic, subheader_ptr, ptr_offset_list_ptr):
            raise ValueError("Invalid SIR0 header")

        self.wan_header = WANSubHeader.read_from_bytes(self.rawdata, subheader_ptr)

        # WAN uses absolute file offsets, not relative offsets
        if self.wan_header.ptr_animinfo != 0:
            self.wan_anim_info = WANAnimInfo.read_from_bytes(
                self.rawdata, self.wan_header.ptr_animinfo
            )

        if self.wan_header.ptr_imginfo != 0:
            self.wan_img_data_info = WANImgDataInfo.read_from_bytes(
                self.rawdata, self.wan_header.ptr_imginfo
            )

    def _parse_common(self, sprite: BaseSprite) -> None:
        """Parse common sprite data."""
        self._read_headers()

        sprite.palette = self._read_palette()

        if self.wan_img_data_info:
            sprite.spr_info.is_8bpp_sprite = self.wan_img_data_info.is_8bpp_sprite
            sprite.spr_info.tiles_mode = self.wan_img_data_info.tiles_mode
            sprite.spr_info.palette_slots_used = (
                self.wan_img_data_info.palette_slots_used
            )

        if self.wan_header:
            sprite.spr_info.sprite_type = self.wan_header.sprite_type
            sprite.spr_info.const0_unk12 = self.wan_header.const0_unk12

        if self.wan_pal_info:
            sprite.spr_info.max_colors_used = self.wan_pal_info.max_colors_used
            sprite.spr_info.bool_unk3 = self.wan_pal_info.bool_unk3
            sprite.spr_info.unk4 = self.wan_pal_info.unk4
            sprite.spr_info.unk5 = self.wan_pal_info.unk5

        if self.wan_anim_info:
            sprite.spr_info.max_memory_used = self.wan_anim_info.max_memory_used
            sprite.spr_info.const0_unk7 = self.wan_anim_info.const0_unk7
            sprite.spr_info.const0_unk8 = self.wan_anim_info.const0_unk8
            sprite.spr_info.bool_unk9 = self.wan_anim_info.bool_unk9
            sprite.spr_info.const0_unk10 = self.wan_anim_info.const0_unk10

        sprite.metaframes, sprite.metaframe_groups = self._read_meta_frame_groups()
        sprite.anim_groups = self._read_anim_groups()
        sprite.anim_sequences = self._read_anim_sequences(sprite.anim_groups)
        sprite.part_offsets = self._read_particle_offsets()

    def _read_palette(self) -> np.ndarray:
        """Read palette from file as flattened NumPy array (n_colors * 3) for RGB values."""
        if not self.wan_img_data_info or self.wan_img_data_info.ptr_pal == 0:
            return np.array([], dtype=np.uint8)

        self.wan_pal_info = WANPalInfo.read_from_bytes(
            self.rawdata, self.wan_img_data_info.ptr_pal
        )

        if self.wan_pal_info.ptr_pal == 0:
            return np.array([], dtype=np.uint8)

        # Palette stored as RGBX (4 bytes per color), extract only RGB for PIL
        palette_start = self.wan_pal_info.ptr_pal
        palette_end = self.wan_img_data_info.ptr_pal
        nb_colors = (palette_end - palette_start) // 4

        if nb_colors > 0:
            palette_bytes = self.rawdata[palette_start : palette_start + nb_colors * 4]
            palette_arr = np.frombuffer(palette_bytes, dtype=np.uint8).reshape(
                nb_colors, 4
            )

            palette = palette_arr[:, :3].flatten()
        else:
            palette = np.array([], dtype=np.uint8)

        return palette

    def _read_meta_frame_groups(self) -> Tuple[List[MetaFrame], List[MetaFrameGroup]]:
        """Read meta-frame groups."""
        if not self.wan_anim_info or self.wan_anim_info.ptr_meta_frm_table == 0:
            return [], []

        beg_seq_tbl = self._calc_file_offset_beg_seq_table()

        if self.wan_anim_info.ptr_p_offsets_table != 0:
            end_mf_ptr_tbl = self.wan_anim_info.ptr_p_offsets_table
        else:
            end_mf_ptr_tbl = beg_seq_tbl

        nb_ptr_mf_grp_tbl = (
            end_mf_ptr_tbl - self.wan_anim_info.ptr_meta_frm_table
        ) // 4

        if nb_ptr_mf_grp_tbl == 0:
            return [], []

        pos = self.wan_anim_info.ptr_meta_frm_table
        mf_ptr_tbl = [
            read_uint32(self.rawdata, pos + i * 4) for i in range(nb_ptr_mf_grp_tbl)
        ]

        metaframes = []
        metaframe_groups = []

        for grp_ptr in mf_ptr_tbl:
            group = MetaFrameGroup()
            pos = grp_ptr

            while pos < len(self.rawdata):
                mf, is_last = self._read_meta_frame(pos)
                metaframes.append(mf)
                group.metaframes.append(len(metaframes) - 1)
                pos += WanFormat.LENGTH_META_FRM
                if is_last:
                    break

            metaframe_groups.append(group)

        return metaframes, metaframe_groups

    def _read_meta_frame(self, offset: int) -> Tuple[MetaFrame, bool]:
        """Read a single meta-frame from WAN container. Returns (MetaFrame, is_last)."""
        mf = MetaFrame()

        mf.image_index = read_int16(self.rawdata, offset)
        mf.unk0 = read_uint16(self.rawdata, offset + 2)
        offy_fl = read_uint16(self.rawdata, offset + 4)
        offx_fl = read_uint16(self.rawdata, offset + 6)
        mf.memory_offset = read_uint8(self.rawdata, offset + 8)
        mf.palette_offset = read_uint8(self.rawdata, offset + 9)

        mf.offset_y = offy_fl & 0x03FF
        mf.offset_x = offx_fl & 0x01FF

        mf.resolution = _get_resolution_from_offsets(offx_fl, offy_fl)

        mf.v_flip = (offx_fl >> 13) & 1
        mf.h_flip = (offx_fl >> 12) & 1
        is_last = bool(offx_fl & (1 << 11))  # Bit 11 indicates last frame in group
        mf.is_absolute_palette = (offx_fl >> 10) & 1
        mf.const0_x_off_bit7 = (offx_fl >> 9) & 1

        mf.bool_y_off_bit3 = (offy_fl >> 13) & 1
        mf.mosaic = (offy_fl >> 12) & 1
        mf.const0_y_off_bit5 = (offy_fl >> 11) & 1
        mf.const0_y_off_bit6 = (offy_fl >> 10) & 1

        return mf, is_last

    def _read_anim_groups(self) -> List[SpriteAnimationGroup]:
        """Read animation groups."""
        if not self.wan_anim_info or self.wan_anim_info.ptr_anim_grp_table == 0:
            return []

        anim_groups = []
        pos = self.wan_anim_info.ptr_anim_grp_table

        for _ in range(self.wan_anim_info.nb_anim_groups):
            ptr_grp = read_uint32(self.rawdata, pos)
            nb_seqs = read_uint32(self.rawdata, pos + 4)
            pos += 8

            group = SpriteAnimationGroup()

            if ptr_grp != 0 and nb_seqs != 0:
                seq_pos = ptr_grp
                for _ in range(nb_seqs):
                    seq_ptr = read_uint32(self.rawdata, seq_pos)
                    group.seqs_indexes.append(
                        seq_ptr
                    )  # Store as pointer, will be converted to index later
                    seq_pos += 4

            anim_groups.append(group)

        return anim_groups

    def _read_anim_sequences(
        self, anim_groups: List[SpriteAnimationGroup]
    ) -> List[AnimationSequence]:
        """Read animation sequences."""
        sequences = []
        sequences_locations = {}  # Map pointer -> index in sequences list

        for group in anim_groups:
            for i, seq_ptr in enumerate(group.seqs_indexes):
                if seq_ptr in sequences_locations:
                    group.seqs_indexes[i] = sequences_locations[seq_ptr]
                else:
                    seq_idx = len(sequences)
                    sequences_locations[seq_ptr] = seq_idx
                    seq = self._read_anim_sequence(seq_ptr)
                    sequences.append(seq)
                    group.seqs_indexes[i] = seq_idx

        return sequences

    def _read_anim_sequence(self, offset: int) -> AnimationSequence:
        """Read a single animation sequence."""
        seq = AnimationSequence()
        pos = offset

        while pos < len(self.rawdata):
            frame = self._read_anim_frame(pos)
            if frame.is_null():
                break
            seq.insert_frame(frame)
            pos += WanFormat.LENGTH_ANIM_FRM

        return seq

    def _read_anim_frame(self, offset: int) -> AnimFrame:
        """Read a single animation frame."""
        af = AnimFrame()
        af.frame_duration = read_uint16(self.rawdata, offset)
        af.meta_frm_grp_index = read_uint16(self.rawdata, offset + 2)
        af.spr_offset_x = read_int16(self.rawdata, offset + 4)
        af.spr_offset_y = read_int16(self.rawdata, offset + 6)
        af.shadow_offset_x = read_int16(self.rawdata, offset + 8)
        af.shadow_offset_y = read_int16(self.rawdata, offset + 10)
        return af

    def _read_particle_offsets(self) -> List[SprOffParticle]:
        """Read particle offsets."""
        if not self.wan_anim_info or self.wan_anim_info.ptr_p_offsets_table == 0:
            return []

        # Some files reuse meta-frame table pointer for particle offsets (invalid)
        if (
            self.wan_anim_info.ptr_p_offsets_table
            == self.wan_anim_info.ptr_meta_frm_table
        ):
            return []

        offset_beg_seq_table = self._calc_file_offset_beg_seq_table()
        offset_block_len = offset_beg_seq_table - self.wan_anim_info.ptr_p_offsets_table
        nb_offsets = offset_block_len // 4

        offsets = []
        pos = self.wan_anim_info.ptr_p_offsets_table

        for _ in range(nb_offsets):
            if pos + 4 > len(self.rawdata):
                break
            offset = SprOffParticle()
            offset.offx = read_int16(self.rawdata, pos)
            offset.offy = read_int16(self.rawdata, pos + 2)
            offsets.append(offset)
            pos += 4

        return offsets

    def _calc_file_offset_beg_seq_table(self) -> int:
        """Calculate the beginning of the sequence table.

        For normal sprites: uses ptr_imgs_tbl as the end boundary.
        For animation-only sprites (no image data): uses ptr_anim_grp_table as the end boundary
        and finds the first non-null sequence pointer.
        """
        if not self.wan_anim_info:
            return 0

        pos = self.wan_anim_info.ptr_anim_grp_table
        nb_null_groups = 0

        # Determine the end boundary for scanning
        if self.wan_img_data_info:
            end_boundary = self.wan_img_data_info.ptr_imgs_tbl
        else:
            # Animation-only file: use anim_info offset as rough end boundary
            # Scan up to nb_anim_groups entries
            end_boundary = pos + (self.wan_anim_info.nb_anim_groups * 8)

        while pos < end_boundary:
            ptr_grp = read_uint32(self.rawdata, pos)
            if ptr_grp == 0:
                nb_null_groups += 1
                pos += 8
            else:
                break

        first_non_null_grp = self.wan_anim_info.ptr_anim_grp_table + (
            nb_null_groups * 8
        )
        nb_bytes_bef_non_null_seq = nb_null_groups * 4

        if (
            self.wan_img_data_info
            and first_non_null_grp == self.wan_img_data_info.ptr_imgs_tbl
        ):
            return self.wan_anim_info.ptr_anim_grp_table - nb_bytes_bef_non_null_seq
        elif first_non_null_grp >= end_boundary:
            # All groups are null or we hit the boundary
            return self.wan_anim_info.ptr_anim_grp_table - nb_bytes_bef_non_null_seq
        else:
            first_non_null_seq = read_uint32(self.rawdata, first_non_null_grp)
            return first_non_null_seq - nb_bytes_bef_non_null_seq

    def _build_frame_dimension_map(self, sprite: BaseSprite) -> dict:
        """
        Build a lookup map from frame_index to (width, height) for dimension detection.

        Works for both modes:
        - Normal mode: Uses image_index from metaframes to map to dimensions
        - Tiles mode: Uses memory_offset ordering to map sequential frames to dimensions

        Returns:
            Dictionary mapping frame_index -> (width, height)
        """
        is_tiles_mode = sprite.spr_info.tiles_mode == 1
        frame_dimension_map = {}

        if not sprite.metaframes:
            return frame_dimension_map

        if is_tiles_mode:
            # Tiles mode: collect unique (memory_offset, width, height) and sort by offset
            # This gives us the frame order in the tilemap
            offset_dimensions = {}
            for mf in sprite.metaframes:
                if mf.image_index == WanFormat.SPECIAL_META_FRAME_ID:
                    offset = mf.memory_offset
                    if offset not in offset_dimensions:
                        width, height = enum_res_to_integer(mf.resolution)
                        offset_dimensions[offset] = (width, height)

            # Map sorted offsets to frame indices
            for frame_idx, offset in enumerate(sorted(offset_dimensions.keys())):
                frame_dimension_map[frame_idx] = offset_dimensions[offset]
        else:
            # Normal mode: map image_index directly to dimensions
            for mf in sprite.metaframes:
                if (
                    mf.image_index != WanFormat.SPECIAL_META_FRAME_ID
                    and mf.image_index not in frame_dimension_map
                ):
                    width, height = enum_res_to_integer(mf.resolution)
                    frame_dimension_map[mf.image_index] = (width, height)

        return frame_dimension_map

    def _determine_tile_arrangement(
        self,
        num_tiles: int,
        frame_index: int,
        frame_dimension_map: dict = None,
    ) -> Tuple[int, int]:
        """
        Determine tile grid arrangement (num_tiles_x × num_tiles_y).

        Uses frame_dimension_map if available and matches tile count.
        Otherwise returns tiles as stored (single row).
        """
        # Try to use frame_dimension_map (works for both normal and tiles mode)
        if frame_dimension_map and frame_index in frame_dimension_map:
            width, height = frame_dimension_map[frame_index]
            expected_tiles_x = width // TILE_SIZE
            expected_tiles_y = height // TILE_SIZE
            expected_tiles = expected_tiles_x * expected_tiles_y

            if expected_tiles == num_tiles:
                return expected_tiles_x, expected_tiles_y

        if num_tiles == 0:
            return (1, 1)
        elif num_tiles == 1:
            return (1, 1)
        elif num_tiles == 4:
            return (2, 2)
        elif num_tiles == 8:
            return (4, 2)  # Prefer landscape (4x2) over portrait (2x4)
        elif num_tiles == 16:
            return (4, 4)
        else:
            best_arrangement = None
            best_score = float("inf")

            for tiles_x in [1, 2, 4, 8, 16, 32]:
                if num_tiles % tiles_x == 0:
                    tiles_y = num_tiles // tiles_x
                    aspect_ratio = max(tiles_x, tiles_y) / min(tiles_x, tiles_y)

                    if aspect_ratio < best_score:
                        best_score = aspect_ratio
                        best_arrangement = (tiles_x, tiles_y)

            result = best_arrangement if best_arrangement else (4, (num_tiles + 3) // 4)
            return result

    def _read_images(self, sprite: BaseSprite, is_4bpp: bool) -> None:
        """Read images from the image table.

        Args:
            sprite: Sprite object to populate
            is_4bpp: True for 4bpp, False for 8bpp
        """
        if not self.wan_img_data_info:
            return

        nb_frames = self.wan_img_data_info.nb_imgs_tbl_ptr
        img_tbl_offset = self.wan_img_data_info.ptr_imgs_tbl

        # Build unified dimension map (works for both normal and tiles mode)
        frame_dimension_map = self._build_frame_dimension_map(sprite)

        sprite.frames = []
        sprite.imgs_info = []

        for i in range(nb_frames):
            img_ptr = read_uint32(self.rawdata, img_tbl_offset + (i * 4))
            img, z_index = self._read_image(
                img_ptr,
                i,
                is_4bpp=is_4bpp,
                frame_dimension_map=frame_dimension_map,
            )
            sprite.frames.append(img)

            info = ImageInfo()
            info.zindex = z_index
            sprite.imgs_info.append(info)

    def _read_image(
        self,
        offset: int,
        frame_index: int,
        is_4bpp: bool,
        frame_dimension_map: dict = None,
    ) -> Tuple[TiledImage, int]:
        """Read an image from the assembly table.

        Args:
            offset: Offset to assembly table
            frame_index: Frame index
            is_4bpp: True for 4bpp (pixamt in bytes, 2 pixels/byte), False for 8bpp (pixamt in pixels, 1 pixel/byte)
            frame_dimension_map: Map of frame_index -> (width, height) for dimension detection

        Returns:
            Tuple of (TiledImage, z_index)
        """
        img = TiledImage()

        asm_table = []
        pos = offset

        while pos < len(self.rawdata):
            entry = ImgAsmTblEntry.read_from_bytes(self.rawdata, pos)
            if entry.is_null():
                break
            asm_table.append(entry)
            pos += 12

        if not asm_table:
            return img, 0

        total_pixels = 0

        for entry in asm_table:
            if is_4bpp:
                total_pixels += entry.pixamt * 2
            else:
                total_pixels += entry.pixamt

        tiled_pixels = np.zeros(total_pixels, dtype=np.uint8)
        pixel_idx = 0

        for entry in asm_table:
            if entry.pixelsrc == 0:
                pixel_idx += entry.pixamt * 2 if is_4bpp else entry.pixamt
            else:
                src_offset = entry.pixelsrc

                if is_4bpp:
                    bytes_to_read = entry.pixamt
                    end_offset = min(src_offset + bytes_to_read, len(self.rawdata))

                    bytes_data = self.rawdata[src_offset:end_offset]
                    arr = np.frombuffer(bytes_data, dtype=np.uint8)

                    # WAN files use reversed pixel order: low nybble first
                    low = arr & 0x0F
                    high = (arr >> 4) & 0x0F
                    unpacked = np.stack([low, high], axis=1).flatten()

                    copy_len = len(unpacked)
                    tiled_pixels[pixel_idx : pixel_idx + copy_len] = unpacked
                    pixel_idx += copy_len

                    remaining_bytes = bytes_to_read - (end_offset - src_offset)
                    if remaining_bytes > 0:
                        pixel_idx += remaining_bytes * 2
                else:
                    end_offset = min(src_offset + entry.pixamt, len(self.rawdata))
                    copy_len = end_offset - src_offset

                    tiled_pixels[pixel_idx : pixel_idx + copy_len] = np.frombuffer(
                        self.rawdata[src_offset:end_offset], dtype=np.uint8
                    )
                    pixel_idx += entry.pixamt

        num_tiles = (len(tiled_pixels) + TILE_AREA - 1) // TILE_AREA

        num_tiles_x, num_tiles_y = self._determine_tile_arrangement(
            num_tiles, frame_index, frame_dimension_map
        )

        width = num_tiles_x * TILE_SIZE
        height = num_tiles_y * TILE_SIZE

        actual_num_tiles = len(tiled_pixels) // TILE_AREA

        if actual_num_tiles > 0:
            tiles_3d = tiled_pixels[: actual_num_tiles * TILE_AREA].reshape(
                actual_num_tiles, TILE_SIZE, TILE_SIZE
            )
            img.pixels = np.zeros((height, width), dtype=np.uint8)

            tile_idx = 0
            for tile_y in range(num_tiles_y):
                y_start = tile_y * TILE_SIZE
                y_end = min(y_start + TILE_SIZE, height)
                for tile_x in range(num_tiles_x):
                    if tile_idx >= actual_num_tiles:
                        break
                    x_start = tile_x * TILE_SIZE
                    x_end = min(x_start + TILE_SIZE, width)
                    img.pixels[y_start:y_end, x_start:x_end] = tiles_3d[
                        tile_idx, : y_end - y_start, : x_end - x_start
                    ]
                    tile_idx += 1
        else:
            img.pixels = np.zeros((height, width), dtype=np.uint8)

        z_index = asm_table[0].z_index if asm_table else 0

        return img, z_index
