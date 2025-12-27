"""
Wrapper functions for reading and writing all external files (XML, palette, and images).
"""

from pathlib import Path
from wan_files.sprite import BaseSprite
from .constants import ExternalFiles
from .xml_reader import read_sprite_xml
from .xml_writer import write_sprite_xml
from .palette import read_palette, write_palette
from .images import export_frame_images, import_frame_images


def read_external_files(sprite_dir: Path) -> BaseSprite:
    """Read all external files (XML, palette, and images) for a sprite.

    Reads spriteinfo.xml to determine sprite properties and sets is_8bpp_sprite flag.

    Args:
        sprite_dir: Directory containing sprite external files

    Returns:
        BaseSprite object
    """
    sprite = BaseSprite()

    read_sprite_xml(sprite, sprite_dir)

    palette_file = sprite_dir / ExternalFiles.PALETTE_FILE

    imgs_dir = sprite_dir / ExternalFiles.IMGS_DIR

    sprite.palette = read_palette(palette_file, imgs_dir)

    import_frame_images(imgs_dir, sprite)

    return sprite


def write_external_files(sprite: BaseSprite, output_dir: Path) -> None:
    """Write all external files (XML, palette, and images) for a sprite.

    Args:
        sprite: BaseSprite object to export
        output_dir: Output directory path
    """

    output_dir.mkdir(parents=True, exist_ok=True)

    write_sprite_xml(sprite, output_dir)

    write_palette(sprite, output_dir / ExternalFiles.PALETTE_FILE)

    imgs_dir = output_dir / ExternalFiles.IMGS_DIR

    export_frame_images(sprite, imgs_dir)
