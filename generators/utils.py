from wan_files import extract_wan
from external_files import read_external_files
from pathlib import Path
from typing import Union


def validate_external_input(
    wan_input: Union[Path, bytes],
    raise_on_errors: bool = True,
):
    """Validate and load sprite from path or raw bytes.

    Args:
        wan_input: Path to folder/WAN file or raw WAN bytes
        raise_on_errors: If True, raise exception on validation errors

    Returns:
        Tuple of (sprite, validation_info) where validation_info is a dict with:
        is_image_base, is_animation_base, requires_base_sprite
    """
    print("[VALIDATING] Validating files...\n")

    if isinstance(wan_input, Path) and wan_input.is_dir():
        sprite = read_external_files(wan_input)
    else:
        sprite = extract_wan(wan_input)

    validation_info = sprite.validate(raise_on_errors=raise_on_errors)

    return sprite, validation_info
