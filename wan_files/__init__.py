"""
WAN files module for extracting, generating, and representing WAN sprite files.
"""

from .wan_io import extract_wan, generate_wan
from .sprite import (
    # Sprite classes
    BaseSprite,
    TiledImage,
    MetaFrame,
    MetaFrameGroup,
    AnimFrame,
    AnimationSequence,
    SpriteAnimationGroup,
    SprOffParticle,
    ImageInfo,
    SprInfo,
)
from .constants import (
    # Constants
    MetaFrameRes,
    ORIENTATION_VALUES,
    CHUNK_SIZES,
    WanFormat,
    # Palette constants
    PALETTE_SLOT_COLOR_COUNT,
    PALETTE_SLOT_RGB_COUNT,
    PALETTE_OFFSET_BASE,
    PALETTE_SLOT_4BPP_BASE,
    PALETTE_SLOT_8BPP_BASE,
)

__all__ = [
    # IO functions
    "extract_wan",
    "generate_wan",
    # Sprite classes
    "BaseSprite",
    "TiledImage",
    "MetaFrame",
    "MetaFrameGroup",
    "AnimFrame",
    "AnimationSequence",
    "SpriteAnimationGroup",
    "SprOffParticle",
    "ImageInfo",
    "SprInfo",
    # Constants
    "MetaFrameRes",
    "WanFormat",
    "ORIENTATION_VALUES",
    "CHUNK_SIZES",
    # Palette constants
    "PALETTE_SLOT_COLOR_COUNT",
    "PALETTE_SLOT_RGB_COUNT",
    "PALETTE_OFFSET_BASE",
    "PALETTE_SLOT_4BPP_BASE",
    "PALETTE_SLOT_8BPP_BASE",
]
