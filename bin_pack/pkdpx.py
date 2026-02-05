"""
Standalone PKDPX Compression/Decompression Module

Independent implementation - no skytemple-files dependency.
Based on SkyTemple research (GPL-3.0 licensed).

PKDPX is an LZ-style compression used in Pokemon Mystery Dungeon games.
"""

from collections import deque
from enum import Enum
from typing import Tuple, Deque


# ============================================================================
# CONSTANTS
# ============================================================================

PX_LOOKBACK_BUFFER_SIZE = 4096
PX_MAX_MATCH_SEQLEN = 18
PX_MIN_MATCH_SEQLEN = 3
PX_NB_POSSIBLE_SEQ_LEN = 7

PKDPX_MAGIC = b"PKDPX"
PKDPX_HEADER_SIZE = 0x14


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================


def _iter_bits(byte: int):
    """Iterate over bits in a byte (MSB first)."""
    for i in range(7, -1, -1):
        yield (byte >> i) & 1


def _compute_four_nibbles_pattern(idx_ctrl_flags: int, low_nibble: int) -> bytes:
    """Build 2 bytes from control flag index and low nibble."""
    if idx_ctrl_flags == 0:
        byte1 = byte2 = low_nibble << 4 | low_nibble
    else:
        nibble_base = low_nibble
        if idx_ctrl_flags == 1:
            nibble_base += 1
        elif idx_ctrl_flags == 5:
            nibble_base -= 1

        ns = [nibble_base, nibble_base, nibble_base, nibble_base]
        if 1 <= idx_ctrl_flags <= 4:
            ns[idx_ctrl_flags - 1] -= 1
        else:
            ns[idx_ctrl_flags - 5] += 1

        byte1 = ns[0] << 4 | ns[1]
        byte2 = ns[2] << 4 | ns[3]

    return bytes([byte1 & 0xFF, byte2 & 0xFF])


# ============================================================================
# DECOMPRESSOR
# ============================================================================


class PxDecompressor:
    """Optimized PX decompression algorithm."""

    def __init__(self, compressed_data: bytes, flags: bytes):
        self.compressed_data = compressed_data
        self.flags = flags
        # Pre-build flag lookup dict for O(1) matching
        self.flag_map = {f: i for i, f in enumerate(flags)}

    def decompress(self) -> bytes:
        """Decompress PX data with optimized inner loop."""
        print("[DEBUG] Decompressing data...")

        data = self.compressed_data
        data_len = len(data)
        flag_map = self.flag_map
        output = bytearray()
        cursor = 0

        while cursor < data_len:
            ctrl_byte = data[cursor]
            cursor += 1

            # Unrolled bit iteration (MSB first)
            for shift in (7, 6, 5, 4, 3, 2, 1, 0):
                if cursor >= data_len:
                    break

                if (ctrl_byte >> shift) & 1:
                    # Copy literal byte
                    output.append(data[cursor])
                    cursor += 1
                else:
                    # Handle special operation
                    next_byte = data[cursor]
                    cursor += 1
                    high = (next_byte >> 4) & 0xF
                    low = next_byte & 0xF

                    # Check if matches any control flag (O(1) lookup)
                    flag_idx = flag_map.get(high)
                    if flag_idx is not None:
                        # Nibble pattern expansion
                        output += _compute_four_nibbles_pattern(flag_idx, low)
                    else:
                        # Copy sequence from previous output
                        offset_byte = data[cursor]
                        cursor += 1
                        offset = (-0x1000 + (low << 8)) | offset_byte
                        copy_pos = len(output) + offset
                        copy_len = high + PX_MIN_MATCH_SEQLEN

                        if copy_pos < 0:
                            raise ValueError(f"Invalid sequence offset: {offset}")

                        # Fast copy using extend where possible
                        if copy_pos + copy_len <= len(output):
                            output.extend(output[copy_pos : copy_pos + copy_len])
                        else:
                            # Overlapping copy - must do byte by byte
                            for i in range(copy_len):
                                output.append(output[copy_pos + i])

        return bytes(output)


# ============================================================================
# COMPRESSOR
# ============================================================================


class Operation(Enum):
    COPY_ASIS = -1
    COPY_NYBBLE_4TIMES = 0
    COPY_NYBBLE_4TIMES_EX_INCRALL_DECRNYBBLE0 = 1
    COPY_NYBBLE_4TIMES_EX_DECRNYBBLE1 = 2
    COPY_NYBBLE_4TIMES_EX_DECRNYBBLE2 = 3
    COPY_NYBBLE_4TIMES_EX_DECRNYBBLE3 = 4
    COPY_NYBBLE_4TIMES_EX_DECRALL_INCRNYBBLE0 = 5
    COPY_NYBBLE_4TIMES_EX_INCRNYBBLE1 = 6
    COPY_NYBBLE_4TIMES_EX_INCRNYBBLE2 = 7
    COPY_NYBBLE_4TIMES_EX_INCRNYBBLE3 = 8
    COPY_SEQUENCE = 9


class CompOp:
    """Compression operation."""

    def __init__(self, op_type=Operation.COPY_ASIS, high=0, low=0, next_byte=0):
        self.type = op_type
        self.high = high
        self.low = low
        self.next_byte = next_byte


class PxCompressor:
    """Optimized PX compression with hash-chain LZ77 matching."""

    def __init__(self, data: bytes):
        self.data_bytes = bytes(data)
        self.size = len(data)
        self.cursor = 0
        self.output_cursor = 0
        self.output = bytearray()
        self.pending: Deque[CompOp] = deque()
        self.high_nibble_lengths = [0, 0xF]
        self.high_nibble_set = {0, 0xF}
        self.control_flags = bytearray(9)
        self.bytes_written = 0
        # Hash chain for O(1) average match finding
        self.head = {}  # hash -> most recent position
        self.prev = [-1] * self.size  # chain: pos -> prev pos with same hash

    def _hash3(self, pos: int) -> int:
        """Hash 3 bytes at position."""
        if pos + 3 > self.size:
            return -1
        b = self.data_bytes
        return ((b[pos] << 16) | (b[pos + 1] << 8) | b[pos + 2]) & 0xFFFFFF

    def _update_hash(self, pos: int):
        """Add position to hash chain."""
        h = self._hash3(pos)
        if h != -1:
            if h in self.head:
                self.prev[pos] = self.head[h]
            self.head[h] = pos

    def compress(self) -> Tuple[bytes, bytes]:
        """Compress data, returns (flags, compressed_data)."""

        print("[DEBUG] Compressing data...")

        self.cursor = 0
        self.output_cursor = 0
        self.pending.clear()
        self.high_nibble_lengths = [0, 0xF]
        self.high_nibble_set = {0, 0xF}
        self.bytes_written = 0
        self.head = {}
        self.prev = [-1] * self.size

        # Worst case allocation
        self.output = bytearray(self.size * 2 + (1 if self.size % 8 != 0 else 0))

        # Build operations
        while self.cursor < self.size:
            for _ in range(8):
                if self.cursor >= self.size:
                    break
                self.pending.append(self._best_operation())

        # Build control flags
        self._build_ctrl_flags()

        # Output operations
        self._output_all()

        return bytes(self.control_flags), bytes(self.output[: self.output_cursor])

    def _best_operation(self) -> CompOp:
        op = CompOp()
        pos = self.cursor

        # Try sequence match first (most compression potential)
        if self._try_sequence(pos, op):
            advance = op.high + PX_MIN_MATCH_SEQLEN
            # Update hash for all positions we're skipping
            for i in range(advance):
                self._update_hash(pos + i)
        # Try simple 4-nibble compression
        elif self._try_simple_compress(pos, op):
            advance = 2
            self._update_hash(pos)
            self._update_hash(pos + 1)
        # Try complex nibble compression
        elif self._try_complex_compress(pos, op):
            advance = 2
            self._update_hash(pos)
            self._update_hash(pos + 1)
        else:
            # Copy as-is
            b = self.data_bytes[pos]
            op.type = Operation.COPY_ASIS
            op.high = (b >> 4) & 0xF
            op.low = b & 0xF
            advance = 1
            self._update_hash(pos)

        self.cursor += advance
        return op

    def _try_simple_compress(self, pos: int, op: CompOp) -> bool:
        """Check if 2 bytes can be compressed to 1 (all 4 nibbles equal)."""
        if pos + 2 > self.size:
            return False

        b1, b2 = self.data_bytes[pos], self.data_bytes[pos + 1]
        n0 = (b1 >> 4) & 0xF
        n1 = b1 & 0xF
        n2 = (b2 >> 4) & 0xF
        n3 = b2 & 0xF

        if n0 == n1 == n2 == n3:
            op.type = Operation.COPY_NYBBLE_4TIMES
            op.low = n3
            return True
        return False

    def _try_complex_compress(self, pos: int, op: CompOp) -> bool:
        """Check if 2 bytes can be compressed with nibble manipulation."""
        if pos + 2 > self.size:
            return False

        b1, b2 = self.data_bytes[pos], self.data_bytes[pos + 1]
        nibbles = [(b1 >> 4) & 0xF, b1 & 0xF, (b2 >> 4) & 0xF, b2 & 0xF]

        nmin, nmax = min(nibbles), max(nibbles)
        if nmax - nmin != 1:
            return False

        # Check if exactly one nibble differs
        count_min = nibbles.count(nmin)
        count_max = nibbles.count(nmax)

        if count_min == 1:
            idx = nibbles.index(nmin)
            op.type = Operation(idx + 1)
            op.low = nibbles[idx] if idx == 0 else nibbles[idx] + 1
            return True
        elif count_max == 1:
            idx = nibbles.index(nmax)
            op.type = Operation(idx + 5)
            op.low = nibbles[idx] if idx == 0 else nibbles[idx] - 1
            return True

        return False

    def _try_sequence(self, pos: int, op: CompOp) -> bool:
        """Highly optimized hash-chain sequence matching."""
        size = self.size
        max_match = size - pos
        if max_match > PX_MAX_MATCH_SEQLEN:
            max_match = PX_MAX_MATCH_SEQLEN
        if max_match < PX_MIN_MATCH_SEQLEN:
            return False

        # Inline hash computation
        if pos + 3 > size:
            return False
        b = self.data_bytes
        h = ((b[pos] << 16) | (b[pos + 1] << 8) | b[pos + 2]) & 0xFFFFFF

        lb_start = pos - PX_LOOKBACK_BUFFER_SIZE
        if lb_start < 0:
            lb_start = 0

        best_pos = -1
        best_len = 0
        head = self.head
        prev = self.prev

        # Direct dict access
        match_pos = head.get(h, -1)
        chain_count = 0

        # Walk hash chain with early termination
        while match_pos >= lb_start and chain_count < 96:
            # Skip if can't beat current best
            limit = pos - match_pos
            if limit > max_match:
                limit = max_match

            if limit > best_len:
                # Quick first byte check
                if b[match_pos] == b[pos]:
                    # Extend match
                    match_len = 1
                    while (
                        match_len < limit
                        and b[match_pos + match_len] == b[pos + match_len]
                    ):
                        match_len += 1

                    if match_len > best_len:
                        best_len = match_len
                        best_pos = match_pos
                        # Early exit on max match
                        if best_len >= PX_MAX_MATCH_SEQLEN:
                            break

            match_pos = prev[match_pos]
            chain_count += 1

        if best_len >= PX_MIN_MATCH_SEQLEN:
            high_nibble = best_len - PX_MIN_MATCH_SEQLEN

            if high_nibble not in self.high_nibble_set:
                if len(self.high_nibble_lengths) < PX_NB_POSSIBLE_SEQ_LEN:
                    self.high_nibble_lengths.append(high_nibble)
                    self.high_nibble_lengths.sort()
                    self.high_nibble_set.add(high_nibble)
                else:
                    # Find longest valid length
                    for l in self.high_nibble_lengths[::-1]:
                        if l + PX_MIN_MATCH_SEQLEN <= best_len:
                            high_nibble = l
                            break
                    else:
                        return False

            offset = -(pos - best_pos)
            op.type = Operation.COPY_SEQUENCE
            op.low = (offset >> 8) & 0xF
            op.next_byte = offset & 0xFF
            op.high = high_nibble
            return True

        return False

    def _check_or_add_length(self, length: int) -> bool:
        """Check if length is in allowed list, or add it if space available."""
        if length in self.high_nibble_set:
            return True
        if len(self.high_nibble_lengths) < PX_NB_POSSIBLE_SEQ_LEN:
            self.high_nibble_lengths.append(length)
            self.high_nibble_lengths.sort()
            self.high_nibble_set.add(length)
            return True
        return False

    def _build_ctrl_flags(self):
        """Build control flags from unused nibble values."""
        # Ensure we have 7 lengths
        for v in range(0xF):
            if len(self.high_nibble_lengths) >= PX_NB_POSSIBLE_SEQ_LEN:
                break
            if v not in self.high_nibble_set:
                self.high_nibble_lengths.append(v)
                self.high_nibble_set.add(v)

        # Build flags from unused values
        flag_idx = 0
        for v in range(0xF):
            if v not in self.high_nibble_set and flag_idx < 9:
                self.control_flags[flag_idx] = v
                flag_idx += 1

    def _output_all(self):
        """Output all pending operations."""
        while self.pending:
            # Build command byte
            cmd = 0
            for i in range(min(8, len(self.pending))):
                if self.pending[i].type == Operation.COPY_ASIS:
                    cmd |= 1 << (7 - i)

            self.output[self.output_cursor] = cmd
            self.output_cursor += 1
            self.bytes_written += 1

            # Output up to 8 operations
            for _ in range(8):
                if not self.pending:
                    break
                op = self.pending.popleft()
                self._output_op(op)

    def _output_op(self, op: CompOp):
        """Output a single operation."""
        if op.type == Operation.COPY_ASIS:
            self.output[self.output_cursor] = (op.high << 4) | op.low
            self.output_cursor += 1
            self.bytes_written += 1
        elif op.type == Operation.COPY_SEQUENCE:
            self.output[self.output_cursor] = (op.high << 4) | op.low
            self.output_cursor += 1
            self.output[self.output_cursor] = op.next_byte
            self.output_cursor += 1
            self.bytes_written += 2
        else:
            flag = self.control_flags[op.type.value]
            self.output[self.output_cursor] = (flag << 4) | op.low
            self.output_cursor += 1
            self.bytes_written += 1


# ============================================================================
# PKDPX CONTAINER
# ============================================================================


class Pkdpx:
    """PKDPX compression container with header handling."""

    @staticmethod
    def decompress(data: bytes) -> bytes:
        """
        Decompress a PKDPX file.

        Args:
            data: Raw PKDPX file bytes (including header)

        Returns:
            Decompressed data
        """
        if data[:5] != PKDPX_MAGIC:
            raise ValueError(f"Invalid PKDPX magic: {data[:5]}")

        length_compressed = int.from_bytes(data[5:7], "little")
        flags = data[7:16]
        length_decompressed = int.from_bytes(data[0x10:0x14], "little")
        compressed_data = data[PKDPX_HEADER_SIZE:]

        result = PxDecompressor(
            compressed_data[: length_compressed - PKDPX_HEADER_SIZE], flags
        ).decompress()

        if len(result) != length_decompressed:
            raise ValueError(
                f"Decompressed size mismatch: expected {length_decompressed}, got {len(result)}"
            )

        return result

    @staticmethod
    def compress(data: bytes) -> bytes:
        """
        Compress data to PKDPX format.

        Args:
            data: Uncompressed data

        Returns:
            PKDPX file bytes (including header)
        """
        flags, compressed = PxCompressor(data).compress()

        length_compressed = len(compressed) + PKDPX_HEADER_SIZE

        return (
            PKDPX_MAGIC
            + length_compressed.to_bytes(2, "little")
            + flags
            + len(data).to_bytes(4, "little")
            + compressed
        )
