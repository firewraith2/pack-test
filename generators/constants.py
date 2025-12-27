MEMORY_BLOCK_SIZE = 256

TRANSPARENT_CHUNK_ID = "9999"

COORDINATE_CENTER_X = 256
COORDINATE_CENTER_Y = 512

DEFAULT_UNK_VALUE = 0

# Validation Constants per Category
SPRITE_CATEGORY_LIMITS = {
    "4bpp_standalone": {
        "max_memory": 255,  # 0xFF
        "base_game_memory": 138,  # 0x8A
        "max_chunks_per_frame": 108,
        "base_game_chunks_per_frame": 80,
        "base_game_unique_chunks": 144,
    },
    "8bpp_standalone": {
        "max_memory": 255,
        "base_game_memory": 151,
        "max_chunks_per_frame": 9999,  # not tested
        "base_game_chunks_per_frame": 37,
        "base_game_unique_chunks": 58,
    },
    "8bpp_base": {
        "max_memory": 255,
        "base_game_memory": 193,
        "max_chunks_per_frame": 9999,  # not tested
        "base_game_chunks_per_frame": 27,
        "base_game_unique_chunks": 114,
    },
    "4bpp_base": {
        "max_memory": 255,
        "base_game_memory": 86,
        "max_chunks_per_frame": 9999,  # not tested
        "base_game_chunks_per_frame": 10,
        "base_game_unique_chunks": 86,
    },
}

# Sprite category configurations
SPRITE_CATEGORY_CONFIGS = {
    "4bpp_standalone": {
        "tiles_mode": None,
        "is_8bpp": False,
        "sprite_type": 0,
        "unk3": False,
        "unk4": 0,
        "unk5": 255,
        "unk9": False,
        "used_base_palette": None,
    },
    "8bpp_standalone": {
        "tiles_mode": None,
        "is_8bpp": True,
        "sprite_type": 2,
        "unk3": True,
        "unk4": 16,
        "unk5": 269,
        "unk9": True,
        "used_base_palette": None,
    },
    "8bpp_base": {
        "tiles_mode": None,
        "is_8bpp": True,
        "sprite_type": 2,
        "unk3": True,
        "unk4": 0,
        "unk5": 255,
        "unk9": False,
        "animation_base_tiles_mode": False,
        "animation_base_is_8bpp": False,
        "animation_base_sprite_type": 2,
        "animation_base_unk3": False,
        "animation_base_unk4": 0,
        "animation_base_unk5": 0,
        "animation_base_unk9": True,
        "used_base_palette": True,
    },
    "4bpp_base": {
        "tiles_mode": None,
        "is_8bpp": False,
        "sprite_type": 2,
        "unk3": False,
        "unk4": 0,
        "unk5": 255,
        "unk9": False,
        "used_base_palette": True,
    },
}

# Base sprite type info for user-facing messages
# Maps requires_base_sprite value to (display_name, location_hint)
BASE_SPRITE_INFO = {
    "animation": ("8bpp animation", "first WAN in EFFECT/effect.bin"),
    "image": ("8bpp image", "last WAN in EFFECT/effect.bin"),
    "4bpp": ("4bpp", "second WAN in EFFECT/effect.bin"),
}
