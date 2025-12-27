"""
Sprite data structures and constants for representing WAN sprite data.
"""

import numpy as np
from typing import List, Tuple
from dataclasses import dataclass, field
from data import enum_res_to_integer, DEBUG

from .constants import (
    WanFormat,
    MetaFrameRes,
    CHUNK_SIZES,
    PALETTE_SLOT_4BPP_BASE,
    PALETTE_SLOT_8BPP_BASE,
    PALETTE_OFFSET_BASE,
    PALETTE_SLOT_COLOR_COUNT,
)


def _allocated_tiles(width: int, height: int, is_8bpp: bool = False) -> int:
    """Calculate memory blocks allocated for a chunk.

    4bpp: 256 pixels per block, 8bpp: 128 pixels per block.
    """
    pixels = width * height
    block_size = 128 if is_8bpp else 256
    return (pixels + block_size - 1) // block_size


@dataclass
class SprOffParticle:
    """Particle offset entry."""

    offx: int = 0
    offy: int = 0


@dataclass
class ImageInfo:
    """Image-specific information."""

    zindex: int = 0


@dataclass
class MetaFrame:
    """Meta-frame structure containing frame properties."""

    image_index: int = WanFormat.SPECIAL_META_FRAME_ID
    unk0: int = 0
    offset_y: int = 0
    offset_x: int = 0
    memory_offset: int = 0
    palette_offset: int = 0
    resolution: int = MetaFrameRes._INVALID
    v_flip: int = 0
    h_flip: int = 0
    mosaic: int = 0
    is_absolute_palette: int = 0
    x_off_bit7: int = 0
    y_off_bit3: int = 0
    y_off_bit5: int = 0
    y_off_bit6: int = 0
    anim_refs: List[Tuple[int, int]] = field(default_factory=list)


@dataclass
class MetaFrameGroup:
    """Group of meta-frame indices."""

    metaframes: List[int] = field(default_factory=list)


@dataclass
class AnimFrame:
    """Single animation frame."""

    frame_duration: int = 0
    meta_frm_grp_index: int = 0
    spr_offset_x: int = 0
    spr_offset_y: int = 0
    shadow_offset_x: int = 0
    shadow_offset_y: int = 0

    def is_null(self) -> bool:
        """Check if this is a null frame."""
        return (
            self.frame_duration == 0
            and self.meta_frm_grp_index == 0
            and self.spr_offset_x == 0
            and self.spr_offset_y == 0
            and self.shadow_offset_x == 0
            and self.shadow_offset_y == 0
        )


class AnimationSequence:
    """Animation sequence containing multiple frames."""

    def __init__(self, nbframes: int = 0):
        self.frames: List[AnimFrame] = []
        if nbframes > 0:
            self.frames = [AnimFrame() for _ in range(nbframes)]

    def insert_frame(self, frame: AnimFrame, index: int = -1) -> int:
        """Insert a frame. If index == -1, insert at the end."""
        if index == -1:
            self.frames.append(frame)
            return len(self.frames) - 1
        else:
            self.frames.insert(index, frame)
            return index

    def remove_frame(self, index: int) -> None:
        """Remove frame at index."""
        del self.frames[index]


@dataclass
class SpriteAnimationGroup:
    """Group of animation sequences."""

    seqs_indexes: List[int] = field(default_factory=list)


@dataclass
class SprInfo:
    """Common sprite information."""

    sprite_type: int = 0
    is_8bpp_sprite: int = 0  # 1 for 8bpp, 0 for 4bpp
    max_colors_used: int = 0
    unk3: int = 0
    unk4: int = 0
    unk5: int = 0
    max_memory_used: int = 0
    unk7: int = 0
    unk8: int = 0
    unk9: int = 0
    unk10: int = 0
    palette_slots_used: int = 0
    unk12: int = 0
    tiles_mode: int = 0  # 1 for tile-based assembly, 0 for chunk-based


class TiledImage:
    """Base class for tiled images.

    Dimensions are stored in pixels.shape (height, width) - no need for separate width/height attributes.
    WAN files don't store image dimensions, so dimensions are only needed when:
    - Creating pixels array from PNG (dimensions come from image file)
    - Creating pixels array from WAN (dimensions are inferred from pixel count)
    - Exporting to PNG (dimensions come from pixels.shape)
    """

    def __init__(self):
        """Initialize with empty pixels array. Will be populated when reading from WAN or importing from PNG."""
        self.pixels: np.ndarray = np.array([], dtype=np.uint8).reshape(0, 0)


class BaseSprite:
    """Sprite class supporting both 4bpp and 8bpp formats.

    Pixel data is stored as np.uint8 which can handle both formats.
    The is_8bpp_sprite value in spr_info (0 for 4bpp, 1 for 8bpp) determines how pixels are encoded/decoded in WAN format.
    """

    def __init__(self):
        """Initialize sprite."""
        self.spr_info = SprInfo()
        self.palette: np.ndarray = np.array([], dtype=np.uint8)
        self.metaframes: List[MetaFrame] = []
        self.metaframe_groups: List[MetaFrameGroup] = []
        self.anim_groups: List[SpriteAnimationGroup] = []
        self.anim_sequences: List[AnimationSequence] = []
        self.part_offsets: List[SprOffParticle] = []
        self.imgs_info: List[ImageInfo] = []
        self.frames: List[TiledImage] = []

    def validate(self, raise_on_errors: bool = True) -> dict:
        """Validate sprite data.

        Args:
            raise_on_errors: If True, raise ValueError on validation errors. If False, print errors and continue.

        Returns:
            dict with keys: is_image_base, is_animation_base, requires_base_sprite

        Raises:
            ValueError: If any invalid references are found and raise_on_errors is True
        """

        errors = []

        sprite_type = self.spr_info.sprite_type
        is_8bpp = self.spr_info.is_8bpp_sprite == 1
        palette_color_count = self.palette.size // 3
        max_colors_used = self.spr_info.max_colors_used
        palette_slots_used = self.spr_info.palette_slots_used

        num_frames = len(self.frames)
        num_metaframes = len(self.metaframes)
        num_metaframe_groups = len(self.metaframe_groups)
        num_anim_sequences = len(self.anim_sequences)
        num_anim_groups = len(self.anim_groups)

        is_4bpp_base = (
            sprite_type == 2
            and is_8bpp == 0
            and num_frames > 0
            and num_metaframes > 0
            and num_anim_sequences > 0
        )
        is_animation_base = (
            sprite_type == 2
            and num_frames == 0
            and num_metaframes > 0
            and num_anim_sequences > 0
        )
        is_image_base = (
            sprite_type == 2
            and is_8bpp == 1
            and num_frames > 0
            and num_metaframes == 0
            and num_anim_sequences == 0
        )
        is_blank_animation = (
            num_frames == 0 and num_metaframes == 0 and num_anim_sequences == 0
        )

        if DEBUG:
            if is_animation_base:
                print("[DEBUG] Detected 8bpp animation base file (no images/palette)\n")
            elif is_image_base:
                print(
                    "[DEBUG] Detected 8bpp image base file (no metaframes/animations)\n"
                )
            elif is_blank_animation:
                print(
                    "[DEBUG] Detected blank animation file (no images/metaframes/animations)\n"
                )
            elif is_4bpp_base:
                print("[DEBUG] Detected 4bpp base file\n")

        if not is_animation_base and not is_blank_animation:
            if num_frames == 0:
                errors.append("Sprite must have at least one chunk image")

        if not is_image_base and not is_blank_animation:
            if num_metaframes == 0:
                errors.append("Sprite must have at least one metaframe")

            if num_metaframe_groups == 0:
                errors.append("Sprite must have at least one metaframe group")

            if num_anim_sequences == 0:
                errors.append("Sprite must have at least one animation sequence")

            if num_anim_groups == 0:
                errors.append("Sprite must have at least one animation group")

        total_available_tiles = 0
        has_special_metaframe = False
        has_normal_metaframe = False

        for frame_idx, frame in enumerate(self.frames):
            if frame.pixels.size > 0:
                height, width = frame.pixels.shape
                dimensions = (width, height)
                if dimensions not in CHUNK_SIZES:
                    errors.append(
                        f"Frame[{frame_idx}]: Invalid dimensions {width}x{height}, "
                        f"must match one of: {CHUNK_SIZES}"
                    )
                total_available_tiles += _allocated_tiles(width, height, is_8bpp)

        max_tiles_required = 0
        max_memory_used = 0
        for mf_idx, mf in enumerate(self.metaframes):
            width, height = enum_res_to_integer(mf.resolution)
            memory_blocks = _allocated_tiles(width, height, is_8bpp)

            if mf.image_index == WanFormat.SPECIAL_META_FRAME_ID:
                has_special_metaframe = True
                chunk_memory_offset = mf.memory_offset

                tiles_required = chunk_memory_offset + memory_blocks
                if tiles_required > max_tiles_required:
                    max_tiles_required = tiles_required
            else:
                has_normal_metaframe = True
                if mf.image_index < 0 or mf.image_index >= num_frames:
                    errors.append(
                        f"MetaFrame[{mf_idx}]: Invalid image_index {mf.image_index}, "
                        f"must be {WanFormat.SPECIAL_META_FRAME_ID} (special) or in range [0, {num_frames - 1}]"
                    )

            memory_usage = mf.memory_offset + memory_blocks
            if memory_usage > max_memory_used:
                max_memory_used = memory_usage

        is_tiles_mode = has_special_metaframe and not has_normal_metaframe

        if is_tiles_mode and not is_animation_base:
            if self.spr_info.tiles_mode != 0x1:
                errors.append(
                    f"Tiles mode: tiles_mode ({self.spr_info.tiles_mode}) must be 0x1"
                )

            if DEBUG:
                print(f"[DEBUG] Tiles mode: Required {max_tiles_required} tiles")
                print(f"[DEBUG] Tiles mode: Available {total_available_tiles} tiles\n")

            if total_available_tiles < max_tiles_required:
                errors.append(
                    f"Tiles mode: Required {max_tiles_required} tiles "
                    f"but only {total_available_tiles} available "
                    f"(deficit: {max_tiles_required - total_available_tiles} tiles)"
                )

        for group_idx, group in enumerate(self.metaframe_groups):
            for mf_ref_idx, mf_ref in enumerate(group.metaframes):
                if mf_ref < 0 or mf_ref >= num_metaframes:
                    errors.append(
                        f"MetaFrameGroup[{group_idx}].metaframes[{mf_ref_idx}]: "
                        f"Invalid metaframe index {mf_ref}, must be in range [0, {num_metaframes - 1}]"
                    )

        for seq_idx, seq in enumerate(self.anim_sequences):
            for frame_idx, af in enumerate(seq.frames):
                # In tiles mode, meta_frm_grp_index >= num_metaframe_groups indicates
                # a blank frame, not an error. Only validate for non-tiles-mode sprites.
                if af.meta_frm_grp_index < 0:
                    errors.append(
                        f"AnimationSequence[{seq_idx}] AnimFrame[{frame_idx}]: "
                        f"Invalid meta_frm_grp_index {af.meta_frm_grp_index}, "
                        f"must be >= 0"
                    )
                elif (
                    not is_tiles_mode and af.meta_frm_grp_index >= num_metaframe_groups
                ):
                    errors.append(
                        f"AnimationSequence[{seq_idx}] AnimFrame[{frame_idx}]: "
                        f"Invalid meta_frm_grp_index {af.meta_frm_grp_index}, "
                        f"must be in range [0, {num_metaframe_groups - 1}]"
                    )

        if max_colors_used > palette_color_count:
            errors.append(
                f"SpriteInfo: max_colors_used ({max_colors_used}) "
                f"exceeds palette color count ({palette_color_count})"
            )

        # Validate color limits based on sprite type
        palette_slot_base = (
            PALETTE_SLOT_8BPP_BASE if is_8bpp else PALETTE_SLOT_4BPP_BASE
        )
        is_base_sprite = is_4bpp_base or is_image_base

        if is_base_sprite:
            max_colors_allowed = palette_slot_base * PALETTE_SLOT_COLOR_COUNT
            if max_colors_used > max_colors_allowed:
                errors.append(
                    f"Base sprite uses {max_colors_used} colors, "
                    f"exceeding {max_colors_allowed} base palette limit"
                )
        elif not is_animation_base:
            max_palette_slots = 16 - palette_slot_base
            max_colors_allowed = max_palette_slots * PALETTE_SLOT_COLOR_COUNT
            if max_colors_used > max_colors_allowed:
                errors.append(
                    f"Sprite uses {max_colors_used} colors, "
                    f"exceeding {max_colors_allowed} unique color limit"
                )

        # For 8bpp, palette_slots_used is always 1
        expected_palette_slots_used = 1 if is_8bpp else max_colors_used // 16

        if (
            palette_slots_used != expected_palette_slots_used
            and not is_image_base
            and not is_4bpp_base
        ):
            errors.append(
                f"SpriteInfo: palette_slots_used ({palette_slots_used}) does not match expected value ({expected_palette_slots_used})"
            )

        if self.spr_info.max_memory_used < max_memory_used:
            errors.append(
                f"SpriteInfo: max_memory_used ({self.spr_info.max_memory_used}) is lower than actual memory usage ({max_memory_used})"
            )

        if errors:
            error_msg = "\n".join(f"  - {err}" for err in errors)
            if raise_on_errors and not DEBUG:
                raise ValueError(error_msg)
            else:
                print(f"[WARNING] Validation errors:\n{error_msg}")
                print()

        # Determine what type of base sprite is needed (if any)
        # - is_4bpp_base: self-contained, no base needed
        # - is_image_base: needs animation base
        # - is_animation_base: needs image base
        # - Otherwise: check if metaframes use base palette slots
        requires_base_sprite = (
            "animation" if is_image_base else "image" if is_animation_base else None
        )

        # For normal sprites, check if any metaframe uses base palette slots
        if requires_base_sprite is None and not is_4bpp_base:
            palette_slot_base = (
                PALETTE_SLOT_8BPP_BASE if is_8bpp else PALETTE_SLOT_4BPP_BASE
            )
            for mf in self.metaframes:
                if is_8bpp or mf.is_absolute_palette == 1:
                    palette_slot = (
                        mf.palette_offset - PALETTE_OFFSET_BASE
                    ) // PALETTE_SLOT_COLOR_COUNT
                    if palette_slot < palette_slot_base:
                        requires_base_sprite = "image" if is_8bpp else "4bpp"
                        break

        # Determine base_type: "image", "animation", "4bpp", or None
        base_type = (
            "image"
            if is_image_base
            else "animation" if is_animation_base else "4bpp" if is_4bpp_base else None
        )

        return {
            "base_type": base_type,
            "requires_base_sprite": requires_base_sprite,
            "is_normal_mode": has_normal_metaframe,
        }
