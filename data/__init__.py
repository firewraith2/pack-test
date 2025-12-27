"""
Core configuration, constants, and utils
"""

from .config import (
    DEBUG,
    CURRENT_VERSION,
    DOCUMENTATION_URL,
    RELEASE_API_ENDPOINT,
)

from .utils import (
    read_uint32,
    read_uint16,
    read_uint8,
    read_int16,
    read_int32,
    write_uint32,
    write_uint16,
    write_uint8,
    write_int16,
    write_int32,
    read_file_to_bytes,
    write_bytes_to_file,
    align_offset,
    pad_bytes,
    enum_res_to_integer,
    int_value_to_string,
    string_value_to_int,
    read_json_file,
    write_json_file,
    validate_path_exists_and_is_dir,
    write_xml_file,
    normalize_string,
)

from .constants import (
    SEPARATOR_LINE_LENGTH,
    DEFAULT_ANIMATION_DURATION,
    TILE_SIZE,
    TILE_AREA,
)

__all__ = [
    # Config
    "DEBUG",
    "CURRENT_VERSION",
    "DOCUMENTATION_URL",
    "RELEASE_API_ENDPOINT",
    "RELEASE_URL",
    # Utils
    "read_uint32",
    "read_uint16",
    "read_uint8",
    "read_int16",
    "read_int32",
    "write_uint32",
    "write_uint16",
    "write_uint8",
    "write_int16",
    "write_int32",
    "read_file_to_bytes",
    "write_bytes_to_file",
    "align_offset",
    "pad_bytes",
    "enum_res_to_integer",
    "int_value_to_string",
    "string_value_to_int",
    "read_json_file",
    "write_json_file",
    "validate_path_exists_and_is_dir",
    "write_xml_file",
    "normalize_string",
    # Constants
    "SEPARATOR_LINE_LENGTH",
    "DEFAULT_ANIMATION_DURATION",
    "TILE_SIZE",
    "TILE_AREA",
]
