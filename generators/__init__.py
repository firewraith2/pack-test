"""
Wanimation Studio Generators Module

This module provides functions for converting between frames and sprites
"""

from .sprite_generator import (
    sg_process_single_folder,
    sg_process_multiple_folder,
    generate_sprite_main,
    validate_sg_input_folder,
)

from .frames_generator import (
    fg_process_single_folder,
    fg_process_multiple_folder,
    generate_frames_main,
)

from .wan_transform import (
    wan_transform_main,
    wan_transform_process_single,
    wan_transform_process_multiple,
)

from .utils import validate_external_input

from .constants import BASE_SPRITE_INFO

__all__ = [
    # Sprite Generator functions
    "sg_process_single_folder",
    "sg_process_multiple_folder",
    "generate_sprite_main",
    "validate_sg_input_folder",
    # Frames Generator functions
    "fg_process_single_folder",
    "fg_process_multiple_folder",
    "generate_frames_main",
    # WAN IO functions
    "wan_transform_main",
    "wan_transform_process_single",
    "wan_transform_process_multiple",
    # Utils functions
    "validate_external_input",
    # Constants
    "BASE_SPRITE_INFO",
]
