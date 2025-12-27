"""
WAN file format constants.
"""


class Sir0:
    MAGIC = 0x53495230
    HEADER_LEN = 16


class WanFormat:
    LENGTH_META_FRM = 10
    LENGTH_ANIM_FRM = 12
    IMG_ASM_TBL_ENTRY_LEN = 12
    PADDING_BYTE = 0xAA
    SPECIAL_META_FRAME_ID = -1


class MetaFrameRes:
    _INVALID = 0xFF

    RESOLUTION_MAP = {
        0: (8, 8),
        0x04: (16, 16),
        0x08: (32, 32),
        0x0C: (64, 64),
        0x40: (16, 8),
        0x80: (8, 16),
        0x44: (32, 8),
        0x84: (8, 32),
        0x48: (32, 16),
        0x88: (16, 32),
        0x4C: (64, 32),
        0x8C: (32, 64),
    }

    RESOLUTION_TO_ENUM = {v: k for k, v in RESOLUTION_MAP.items()}


CHUNK_SIZES = sorted(
    MetaFrameRes.RESOLUTION_MAP.values(),
    key=lambda r: (r[0] * r[1], max(r[0], r[1])),
    reverse=True,
)

ORIENTATION_VALUES = {
    "original": (0, 0),
    "flip_h": (0, 1),
    "flip_v": (1, 0),
    "flip_both": (1, 1),
}


PALETTE_SLOT_4BPP_BASE = 4
PALETTE_SLOT_8BPP_BASE = 13
PALETTE_SLOT_COLOR_COUNT = 16
PALETTE_SLOT_RGB_COUNT = PALETTE_SLOT_COLOR_COUNT * 3
PALETTE_OFFSET_BASE = 12
