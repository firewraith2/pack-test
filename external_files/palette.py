"""
JASC-PAL palette reading and writing functions.
"""

from PIL import Image
import numpy as np
from pathlib import Path
from wan_files.sprite import BaseSprite
from data import (
    read_file_to_bytes,
    write_bytes_to_file,
)


def write_palette(sprite: BaseSprite, output_path: Path) -> None:
    """Export palette to JASC-PAL format.

    Args:
        sprite: BaseSprite object
        output_path: Path to output palette file
    """
    palette = sprite.palette

    num_colors = min(palette.size // 3, 256) if palette.size > 0 else 0
    colors = (
        palette[: num_colors * 3].reshape(num_colors, 3).astype(np.uint8)
        if num_colors > 0
        else []
    )

    lines = ["JASC-PAL", "0100", str(num_colors)]
    for r, g, b in colors:
        lines.append(f"{r} {g} {b} 255")

    content = "\n".join(lines) + "\n"
    write_bytes_to_file(output_path, content.encode("ascii"))


def read_palette(palette_path: Path, imgs_dir: Path) -> np.ndarray:
    """Import palette from JASC-PAL format.

    Args:
        palette_path: Path to palette file
        imgs_dir: Directory containing sprite images

    Returns:
        Flattened NumPy array (n_colors * 3) for RGB values
    """

    if not palette_path.exists() and imgs_dir.exists():
        png_file = next(imgs_dir.glob("*.png"), None)
        if png_file is not None:
            with Image.open(png_file) as img:
                if img.mode != "P":
                    img = img.convert("P", palette=Image.ADAPTIVE, colors=192)

                palette = img.getpalette()
                if palette:
                    return np.array(palette[: 192 * 3], dtype=np.uint8)
        else:
            return np.array([], dtype=np.uint8)

    data = read_file_to_bytes(palette_path)
    text = data.decode("ascii").strip()
    lines = text.split("\n")

    if len(lines) < 3:
        raise ValueError("Invalid JASC-PAL file: too few lines")

    if lines[0].strip() != "JASC-PAL":
        raise ValueError("Invalid JASC-PAL file: missing header")

    if lines[1].strip() != "0100":
        raise ValueError(f"Unsupported JASC-PAL version: {lines[1].strip()}")

    num_colors = int(lines[2].strip())

    if num_colors > 256:
        raise ValueError(f"Invalid palette: {num_colors} colors exceeds maximum of 256")

    if len(lines) < 3 + num_colors:
        raise ValueError(
            f"Invalid JASC-PAL file: expected {num_colors} colors, got {len(lines) - 3}"
        )

    colors = []
    for i in range(num_colors):
        line_num = 4 + i
        parts = lines[3 + i].strip().split()
        if len(parts) < 3 or len(parts) > 4:
            raise ValueError(
                f"Invalid color entry at line {line_num}: expected 3 or 4 values"
            )

        try:
            r, g, b = int(parts[0]), int(parts[1]), int(parts[2])
        except ValueError:
            raise ValueError(
                f"Invalid color entry at line {line_num}: values must be integers, got '{parts[0]} {parts[1]} {parts[2]}'"
            )

        if not (0 <= r <= 255 and 0 <= g <= 255 and 0 <= b <= 255):
            raise ValueError(
                f"Invalid color entry at line {line_num}: values must be 0-255, got '{r} {g} {b}'"
            )

        # Alpha (parts[3]) is ignored - WAN sprites don't use per-color alpha
        colors.extend([r, g, b])

    return np.array(colors, dtype=np.uint8)
