"""
Image export and import functions for sprite frames.
"""

import numpy as np
from pathlib import Path
from PIL import Image
from wan_files.sprite import BaseSprite, TiledImage


def import_frame_images(imgs_dir: Path, sprite: BaseSprite) -> None:
    """Import all frame images from a directory.

    Args:
        imgs_dir: Directory containing PNG image files
        sprite: Sprite object to populate with frames
    """
    if not imgs_dir.exists():
        return

    image_files = list(imgs_dir.glob("*.png"))

    if not image_files:
        return

    image_files.sort(key=lambda p: int(p.stem))

    for img_file in image_files:
        img = Image.open(img_file)

        if img.mode != "P":
            img = img.convert("P")

        frame = TiledImage()
        frame.pixels = np.array(img, dtype=np.uint8)
        sprite.frames.append(frame)


def export_frame_images(sprite: BaseSprite, imgs_dir: Path) -> None:
    """Export all frame images to a directory.

    Args:
        sprite: Sprite object containing frames
        imgs_dir: Output directory for PNG image files
    """
    imgs_dir.mkdir(exist_ok=True)

    frame_palette = sprite.palette

    for frame_idx, frame in enumerate(sprite.frames):
        img_path = imgs_dir / f"{frame_idx}.png"
        pixel_arr = frame.pixels

        img = Image.fromarray(pixel_arr)

        if frame_palette.size > 0:
            img.putpalette(frame_palette)
        else:
            img.putpalette([0, 0, 0])

        img.save(img_path, "PNG")

    print(f"[OK] {len(sprite.frames)} frame image(s) saved to: {imgs_dir}")
