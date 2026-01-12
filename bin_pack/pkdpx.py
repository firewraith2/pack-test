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
    """PX decompression algorithm."""

    def __init__(self, compressed_data: bytes, flags: bytes):
        self.compressed_data = compressed_data
        self.flags = flags
        self.cursor = 0
        self.output = bytearray()

    def decompress(self) -> bytes:
        """Decompress PX data."""

        print("[DEBUG] Decompressing data...")

        self.cursor = 0
        self.output = bytearray()
        data_len = len(self.compressed_data)

        while self.cursor < data_len:
            ctrl_byte = self._read_byte()
            for ctrl_bit in _iter_bits(ctrl_byte):
                if self.cursor >= data_len:
                    break
                if ctrl_bit == 1:
                    self.output.append(self._read_byte())
                else:
                    self._handle_special()

        return bytes(self.output)

    def _read_byte(self) -> int:
        b = self.compressed_data[self.cursor]
        self.cursor += 1
        return b

    def _handle_special(self):
        next_byte = self._read_byte()
        high = (next_byte >> 4) & 0xF
        low = next_byte & 0xF

        # Check if matches any control flag
        flag_idx = self._match_flag(high)
        if flag_idx is not False:
            self.output += _compute_four_nibbles_pattern(flag_idx, low)
        else:
            # Copy sequence from previous output
            offset = (-0x1000 + (low << 8)) | self._read_byte()
            copy_pos = len(self.output) + offset
            copy_len = high + PX_MIN_MATCH_SEQLEN

            if copy_pos < 0:
                raise ValueError(f"Invalid sequence offset: {offset}")

            for i in range(copy_len):
                self.output.append(self.output[copy_pos + i])

    def _match_flag(self, nibble: int):
        for idx, flag in enumerate(self.flags):
            if flag == nibble:
                return idx
        return False


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
    """PX compression algorithm."""

    def __init__(self, data: bytes):
        self.data = memoryview(data) if not isinstance(data, memoryview) else data
        self.size = len(data)
        self.cursor = 0
        self.output_cursor = 0
        self.output = bytearray()
        self.pending: Deque[CompOp] = deque()
        self.high_nibble_lengths = [0, 0xF]  # Pre-reserve 0 and 0xF
        self.control_flags = bytearray(9)
        self.bytes_written = 0

    def compress(self) -> Tuple[bytes, bytes]:
        """Compress data, returns (flags, compressed_data)."""

        print("[DEBUG] Compressing data...")

        self.cursor = 0
        self.output_cursor = 0
        self.pending.clear()
        self.high_nibble_lengths = [0, 0xF]
        self.bytes_written = 0

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

        # Try sequence match first
        if self._try_sequence(self.cursor, op):
            advance = op.high + PX_MIN_MATCH_SEQLEN
        # Try simple 4-nibble compression
        elif self._try_simple_compress(self.cursor, op):
            advance = 2
        # Try complex nibble compression
        elif self._try_complex_compress(self.cursor, op):
            advance = 2
        else:
            # Copy as-is
            b = self.data[self.cursor]
            op.type = Operation.COPY_ASIS
            op.high = (b >> 4) & 0xF
            op.low = b & 0xF
            advance = 1

        self.cursor += advance
        return op

    def _try_simple_compress(self, pos: int, op: CompOp) -> bool:
        """Check if 2 bytes can be compressed to 1 (all 4 nibbles equal)."""
        if pos + 2 > self.size:
            return False

        b1, b2 = self.data[pos], self.data[pos + 1]
        low = b2 & 0xF

        for i in [3, 2, 1, 0]:
            if i < 2:
                nibble = (b1 >> (4 * (1 - i))) & 0xF
            else:
                nibble = (b2 >> (4 * (3 - i))) & 0xF
            if nibble != low:
                return False

        op.type = Operation.COPY_NYBBLE_4TIMES
        op.low = low
        return True

    def _try_complex_compress(self, pos: int, op: CompOp) -> bool:
        """Check if 2 bytes can be compressed with nibble manipulation."""
        if pos + 2 > self.size:
            return False

        b1, b2 = self.data[pos], self.data[pos + 1]
        nibbles = [(b1 >> 4) & 0xF, b1 & 0xF, (b2 >> 4) & 0xF, b2 & 0xF]
        counts = [nibbles.count(n) for n in nibbles]

        if counts.count(3) != 3:
            return False

        nmin, nmax = min(nibbles), max(nibbles)
        if nmax - nmin != 1:
            return False

        idx_small = nibbles.index(nmin)
        idx_large = nibbles.index(nmax)

        if counts[idx_small] == 1:
            op.type = Operation(idx_small + 1)
            op.low = nibbles[idx_small] if idx_small == 0 else nibbles[idx_small] + 1
        else:
            op.type = Operation(idx_large + 5)
            op.low = nibbles[idx_large] if idx_large == 0 else nibbles[idx_large] - 1

        return True

    def _try_sequence(self, pos: int, op: CompOp) -> bool:
        """Try to find a matching sequence in the lookback buffer."""
        lb_start = max(0, pos - PX_LOOKBACK_BUFFER_SIZE)
        lb_end = pos
        seq_end = min(pos + PX_MAX_MATCH_SEQLEN, self.size)

        if seq_end - pos < PX_MIN_MATCH_SEQLEN:
            return False

        # Find the minimum sequence to search for
        seq_to_find = bytes(self.data[pos : pos + PX_MIN_MATCH_SEQLEN])
        data_bytes = self.data.tobytes()

        best_pos = -1
        best_len = 0

        search_pos = lb_start
        while search_pos < lb_end:
            found = data_bytes.find(seq_to_find, search_pos, lb_end)
            if found == -1:
                break

            # Count how many bytes match
            match_len = 0
            for i in range(min(PX_MAX_MATCH_SEQLEN, seq_end - pos)):
                if found + i >= lb_end:
                    break
                if self.data[found + i] == self.data[pos + i]:
                    match_len += 1
                else:
                    break

            if match_len > best_len:
                best_len = match_len
                best_pos = found

            if match_len == PX_MAX_MATCH_SEQLEN:
                break

            search_pos = found + 1

        if best_len >= PX_MIN_MATCH_SEQLEN:
            high_nibble = best_len - PX_MIN_MATCH_SEQLEN

            if not self._check_or_add_length(high_nibble):
                # Find longest valid length
                for l in sorted(self.high_nibble_lengths, reverse=True):
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
        if length in self.high_nibble_lengths:
            return True
        if len(self.high_nibble_lengths) < PX_NB_POSSIBLE_SEQ_LEN:
            self.high_nibble_lengths.append(length)
            self.high_nibble_lengths.sort()
            return True
        return False

    def _build_ctrl_flags(self):
        """Build control flags from unused nibble values."""
        # Ensure we have 7 lengths
        for v in range(0xF):
            if len(self.high_nibble_lengths) >= PX_NB_POSSIBLE_SEQ_LEN:
                break
            if v not in self.high_nibble_lengths:
                self.high_nibble_lengths.append(v)

        # Build flags from unused values
        flag_idx = 0
        for v in range(0xF):
            if v not in self.high_nibble_lengths and flag_idx < 9:
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


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================


def pkdpx_decompress(data: bytes) -> bytes:
    """Decompress PKDPX data."""
    return Pkdpx.decompress(data)


def pkdpx_compress(data: bytes) -> bytes:
    """Compress data to PKDPX format."""
    return Pkdpx.compress(data)
