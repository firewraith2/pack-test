import json
import struct
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


def read_uint32(data: bytes, offset: int, little_endian: bool = True) -> int:
    fmt = "<I" if little_endian else ">I"
    return struct.unpack_from(fmt, data, offset)[0]


def read_uint16(data: bytes, offset: int, little_endian: bool = True) -> int:
    fmt = "<H" if little_endian else ">H"
    return struct.unpack_from(fmt, data, offset)[0]


def read_uint8(data: bytes, offset: int) -> int:
    return data[offset]


def read_int16(data: bytes, offset: int, little_endian: bool = True) -> int:
    fmt = "<h" if little_endian else ">h"
    return struct.unpack_from(fmt, data, offset)[0]


def read_int32(data: bytes, offset: int, little_endian: bool = True) -> int:
    fmt = "<i" if little_endian else ">i"
    return struct.unpack_from(fmt, data, offset)[0]


def write_uint32(value: int, little_endian: bool = True) -> bytes:
    fmt = "<I" if little_endian else ">I"
    return struct.pack(fmt, value)


def write_uint16(value: int, little_endian: bool = True) -> bytes:
    fmt = "<H" if little_endian else ">H"
    return struct.pack(fmt, value)


def write_uint8(value: int) -> bytes:
    return struct.pack("B", value)


def write_int16(value: int, little_endian: bool = True) -> bytes:
    fmt = "<h" if little_endian else ">h"
    return struct.pack(fmt, value)


def write_int32(value: int, little_endian: bool = True) -> bytes:
    fmt = "<i" if little_endian else ">i"
    return struct.pack(fmt, value)


def read_file_to_bytes(filepath: Path) -> bytes:
    with open(filepath, "rb") as f:
        return f.read()


def write_bytes_to_file(filepath: Path, data: bytes) -> None:
    with open(filepath, "wb") as f:
        f.write(data)


def align_offset(offset: int, alignment: int) -> int:
    if offset % alignment == 0:
        return offset
    return offset + (alignment - (offset % alignment))


def pad_bytes(length: int, value: int = 0) -> bytes:
    return bytes([value] * length)


def enum_res_to_integer(enum_val: int) -> Tuple[int, int]:
    from wan_files import MetaFrameRes

    return MetaFrameRes.RESOLUTION_MAP.get(enum_val, (64, 64))


def int_value_to_string(value: int) -> str:
    return str(value)


def string_value_to_int(value: str) -> int:
    try:
        return int(value)
    except ValueError as e:
        raise ValueError(f"Could not parse value '{value}': {e}")


def read_json_file(filepath: Path) -> Optional[Dict[str, Any]]:
    if not filepath.exists():
        return None

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError, OSError):
        return None


def write_json_file(filepath: Path, data: Dict[str, Any], indent: int = 4) -> None:
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=indent, ensure_ascii=False)


def validate_path_exists_and_is_dir(path: Path, path_description: str = "Path") -> bool:
    if not path.exists():
        print(f"[ERROR] {path_description} does not exist: {path}\n")
        return False

    if not path.is_dir():
        print(f"[ERROR] Path is not a directory: {path}\n")
        return False

    return True


def write_xml_file(root: ET.Element, output_path: Path) -> None:
    tree = ET.ElementTree(root)
    ET.indent(tree, space="    ")
    tree.write(output_path, encoding="utf-8", xml_declaration=True)


def normalize_string(display_name: str) -> str:
    return display_name.lower().replace(" ", "_")
