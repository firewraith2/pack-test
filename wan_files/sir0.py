"""
SIR0 container format reading and writing.

SIR0 is a container format used to wrap WAN files and other formats.
This module contains functions for reading/parsing and writing/wrapping SIR0 containers.
"""

from typing import List, Tuple
from data import (
    read_uint32,
    write_uint32,
    align_offset,
    pad_bytes,
)
from .constants import Sir0, PADDING_BYTE


def read_sir0_header(data: bytes, offset: int = 0) -> Tuple[int, int, int, int]:
    """
    Read SIR0 header from bytes.

    Returns:
        Tuple of (magic, subheader_ptr, ptr_offset_list_ptr, padding)
    """
    magic = read_uint32(data, offset, little_endian=False)
    subheader_ptr = read_uint32(data, offset + 4)
    ptr_offset_list_ptr = read_uint32(data, offset + 8)
    padding = read_uint32(data, offset + 12)
    return magic, subheader_ptr, ptr_offset_list_ptr, padding


def validate_sir0_header(
    magic: int, subheader_ptr: int, ptr_offset_list_ptr: int
) -> bool:
    """Validate the SIR0 header."""
    return magic == Sir0.MAGIC and subheader_ptr > 0x10 and ptr_offset_list_ptr > 0x10


def decode_pointer_offset_list(data: bytes, offset: int) -> List[int]:
    """
    Decode the SIR0 pointer offset list.

    Implements the DecodeSIR0PtrOffsetList algorithm:
    - Uses a buffer to accumulate bits
    - Shifts buffer by 7 bits when continuation bit is set
    - Accumulates offsetsum to get absolute offsets
    """
    offsets = []
    pos = offset

    # SIR0 header pointers (0x04, 0x08) are encoded first in the list
    offset_sum = 0
    buffer = 0
    last_had_bit_flag = False

    while pos < len(data) and (last_had_bit_flag or data[pos] != 0x00):
        cur_byte = data[pos]
        pos += 1

        buffer |= cur_byte & 0x7F

        if (0x80 & cur_byte) != 0:
            last_had_bit_flag = True
            buffer <<= 7
        else:
            last_had_bit_flag = False
            offset_sum += buffer
            offsets.append(offset_sum)
            buffer = 0

    return offsets


def extract_sir0_content(data: bytes) -> Tuple[bytes, List[int]]:
    """
    Extract the actual content from an SIR0 container.

    Returns:
        Tuple of (content_bytes, pointer_offsets)
    """
    magic, subheader_ptr, ptr_offset_list_ptr, padding = read_sir0_header(data)

    if not validate_sir0_header(magic, subheader_ptr, ptr_offset_list_ptr):
        raise ValueError("Invalid SIR0 header")

    content = data[:ptr_offset_list_ptr]

    ptr_list_data = data[ptr_offset_list_ptr:]
    offsets = decode_pointer_offset_list(ptr_list_data, 0)

    return content, offsets


def write_sir0_header(subheader_ptr: int, ptr_offset_list_ptr: int) -> bytes:
    """
    Write SIR0 header to bytes.

    Args:
        subheader_ptr: Offset to the subheader within content
        ptr_offset_list_ptr: Offset to the pointer offset list

    Returns:
        SIR0 header as bytes (16 bytes)
    """
    result = bytearray()
    result.extend(write_uint32(Sir0.MAGIC, little_endian=False))
    result.extend(write_uint32(subheader_ptr))
    result.extend(write_uint32(ptr_offset_list_ptr))
    result.extend(write_uint32(0))
    return bytes(result)


def encode_pointer_offset_list(offsets: List[int]) -> bytes:
    """
    Encode a list of pointer offsets into SIR0 format.

    Add the two SIR0 header pointer offsets (4 and 8) first,
    then encodes all offsets including those.

    This implements the EncodeSIR0PtrOffsetList algorithm:
    - Calculates deltas between consecutive offsets
    - Encodes each delta in base-128 (7 bits per byte)
    - Uses high bit (0x80) to indicate continuation bytes
    - Only encodes non-zero bytes or bytes after a non-zero byte

    Args:
        offsets: List of pointer offsets (relative to content start)

    Returns:
        Encoded pointer offset list as bytes
    """
    SIR0_EncodedOffsetsHeader = 0x04

    # Header pointers (0x04, 0x08) must be encoded first, then content pointers in order
    header_offset2 = SIR0_EncodedOffsetsHeader + SIR0_EncodedOffsetsHeader
    offsets_to_encode = [SIR0_EncodedOffsetsHeader, header_offset2] + offsets

    result = bytearray()

    if not offsets_to_encode:
        result.append(0x00)
        return bytes(result)

    offset_so_far = 0

    for anoffset in offsets_to_encode:
        offset_to_encode = anoffset - offset_so_far
        offset_so_far = anoffset
        has_higher_non_zero = False

        for i in range(4, 0, -1):
            current_byte = (offset_to_encode >> (7 * (i - 1))) & 0x7F

            if i == 1:
                result.append(current_byte)
            elif current_byte != 0 or has_higher_non_zero:
                result.append(current_byte | 0x80)
                has_higher_non_zero = True

    result.append(0x00)
    return bytes(result)


def wrap_sir0(
    content: bytes, subheader_offset: int, pointer_offsets: List[int]
) -> bytes:
    """
    Wrap content in an SIR0 container.

    Args:
        content: The actual content to wrap
        subheader_offset: Offset to the subheader within content
        pointer_offsets: List of pointer offsets that need to be encoded

    Returns:
        Complete SIR0 file as bytes
    """

    result = bytearray()

    header_pos = 0
    result.extend(bytes(Sir0.HEADER_LEN))

    content_start = len(result)
    result.extend(content)

    content_end = len(result)
    aligned_end = align_offset(content_end, 16)
    padding_needed = aligned_end - content_end
    if padding_needed > 0:
        result.extend(pad_bytes(padding_needed, PADDING_BYTE))

    ptr_list_start = len(result)
    encoded_offsets = encode_pointer_offset_list(pointer_offsets)
    result.extend(encoded_offsets)

    final_pos = len(result)
    aligned_pos = align_offset(final_pos, 16)
    padding_needed = aligned_pos - final_pos
    if padding_needed > 0:
        result.extend(pad_bytes(padding_needed, PADDING_BYTE))

    header_bytes = write_sir0_header(
        subheader_ptr=content_start + subheader_offset,
        ptr_offset_list_ptr=ptr_list_start,
    )
    result[header_pos : header_pos + Sir0.HEADER_LEN] = header_bytes

    return bytes(result)
