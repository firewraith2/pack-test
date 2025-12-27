"""
XML reader functions for sprite data structures.
Handles reading frames.xml, animations.xml, spriteinfo.xml, offsets.xml, and imgsinfo.xml
"""

import xml.etree.ElementTree as ET
from pathlib import Path

from wan_files.sprite import (
    BaseSprite,
    MetaFrame,
    MetaFrameGroup,
    AnimationSequence,
    AnimFrame,
    SpriteAnimationGroup,
    SprOffParticle,
    ImageInfo,
    MetaFrameRes,
)
from .constants import ExternalFiles, XmlNode, XmlProp
from data import string_value_to_int


def read_sprite_xml(sprite: BaseSprite, sprite_path: Path) -> None:
    """Read all XML files for a sprite.

    Args:
        sprite: BaseSprite object
        sprite_path: Path to sprite XML files

    """

    read_spriteinfo_xml(sprite, sprite_path / ExternalFiles.SPRITEINFO_FILE)
    read_frames_xml(sprite, sprite_path / ExternalFiles.FRAMES_FILE)
    read_animations_xml(sprite, sprite_path / ExternalFiles.ANIMATIONS_FILE)
    read_offsets_xml(sprite, sprite_path / ExternalFiles.OFFSETS_FILE)
    read_imgsinfo_xml(sprite, sprite_path / ExternalFiles.IMGSINFO_FILE)


def read_spriteinfo_xml(sprite: BaseSprite, xml_path: Path) -> None:
    """Read spriteinfo.xml.

    Reads sprite properties and sets is_8bpp_sprite flag based on Is256Colors property.

    Args:
        sprite: BaseSprite object
        xml_path: Path to spriteinfo.xml file

    """
    if not xml_path.exists():
        return

    tree = ET.parse(xml_path)
    root = tree.getroot()

    info = sprite.spr_info

    prop_map = {
        XmlProp.UNK3: lambda v: setattr(info, "unk3", string_value_to_int(v)),
        XmlProp.MAXCOLUSED: lambda v: setattr(
            info, "max_colors_used", string_value_to_int(v)
        ),
        XmlProp.UNK4: lambda v: setattr(info, "unk4", string_value_to_int(v)),
        XmlProp.UNK5: lambda v: setattr(info, "unk5", string_value_to_int(v)),
        XmlProp.MAXMEMUSED: lambda v: setattr(
            info, "max_memory_used", string_value_to_int(v)
        ),
        XmlProp.UNK7: lambda v: setattr(info, "unk7", string_value_to_int(v)),
        XmlProp.UNK8: lambda v: setattr(info, "unk8", string_value_to_int(v)),
        XmlProp.UNK9: lambda v: setattr(info, "unk9", string_value_to_int(v)),
        XmlProp.UNK10: lambda v: setattr(info, "unk10", string_value_to_int(v)),
        XmlProp.SPRTY: lambda v: setattr(info, "sprite_type", string_value_to_int(v)),
        XmlProp.IS8BPPSPRITE: lambda v: setattr(
            info, "is_8bpp_sprite", string_value_to_int(v)
        ),
        XmlProp.TILESMODE: lambda v: setattr(
            info, "tiles_mode", string_value_to_int(v)
        ),
        XmlProp.PALSLOTSUSED: lambda v: setattr(
            info, "palette_slots_used", string_value_to_int(v)
        ),
        XmlProp.UNK12: lambda v: setattr(info, "unk12", string_value_to_int(v)),
    }

    for elem in root:
        tag = elem.tag
        value = elem.text or "0"
        if tag in prop_map:
            prop_map[tag](value)


def read_frames_xml(sprite: BaseSprite, xml_path: Path) -> None:
    """Read frames.xml."""
    if not xml_path.exists():
        raise FileNotFoundError(f"{xml_path.name} not found.")

    tree = ET.parse(xml_path)
    root = tree.getroot()

    sprite.metaframes = []
    sprite.metaframe_groups = []

    for group_elem in root.findall(XmlNode.FRMGRP):
        group = MetaFrameGroup()

        for frame_elem in group_elem.findall(XmlNode.FRAME):
            mf = MetaFrame()

            img_idx_elem = frame_elem.find(XmlProp.IMGINDEX)
            if img_idx_elem is not None:
                img_idx_val = img_idx_elem.text or "0"
                mf.image_index = string_value_to_int(img_idx_val)

            offset_elem = frame_elem.find(XmlNode.OFFSET)
            if offset_elem is not None:
                x_elem = offset_elem.find(XmlProp.OFFSET_X)
                y_elem = offset_elem.find(XmlProp.OFFSET_Y)
                if x_elem is not None:
                    mf.offset_x = string_value_to_int(x_elem.text or "0")
                if y_elem is not None:
                    mf.offset_y = string_value_to_int(y_elem.text or "0")

            for prop in frame_elem:
                tag = prop.tag
                if tag == XmlNode.OFFSET:
                    continue
                elif tag == XmlNode.RESOLUTION:
                    width = string_value_to_int(prop.find(XmlProp.WIDTH).text or "64")
                    height = string_value_to_int(prop.find(XmlProp.HEIGHT).text or "64")
                    mf.resolution = MetaFrameRes.RESOLUTION_TO_ENUM.get(
                        (width, height), MetaFrameRes._INVALID
                    )
                else:
                    value = prop.text or "0"
                    if tag == XmlProp.UNK0:
                        mf.unk0 = string_value_to_int(value)
                    elif tag == XmlProp.MEMOFFSET:
                        mf.memory_offset = string_value_to_int(value)
                    elif tag == XmlProp.PALOFFSET:
                        mf.palette_offset = string_value_to_int(value)
                    elif tag == XmlProp.HFLIP:
                        mf.h_flip = string_value_to_int(value)
                    elif tag == XmlProp.VFLIP:
                        mf.v_flip = string_value_to_int(value)
                    elif tag == XmlProp.MOSAIC:
                        mf.mosaic = string_value_to_int(value)
                    elif tag == XmlProp.ISABSOLUTEPALETTE:
                        mf.is_absolute_palette = string_value_to_int(value)
                    elif tag == XmlProp.XOFFBIT7:
                        mf.x_off_bit7 = string_value_to_int(value)
                    elif tag == XmlProp.YOFFBIT3:
                        mf.y_off_bit3 = string_value_to_int(value)
                    elif tag == XmlProp.YOFFBIT5:
                        mf.y_off_bit5 = string_value_to_int(value)
                    elif tag == XmlProp.YOFFBIT6:
                        mf.y_off_bit6 = string_value_to_int(value)

            mf_idx = len(sprite.metaframes)
            sprite.metaframes.append(mf)
            group.metaframes.append(mf_idx)

        sprite.metaframe_groups.append(group)


def read_animations_xml(sprite: BaseSprite, xml_path: Path) -> None:
    """Read animations.xml."""
    if not xml_path.exists():
        raise FileNotFoundError(f"{xml_path.name} not found.")

    tree = ET.parse(xml_path)
    root = tree.getroot()

    sprite.anim_sequences = []
    sprite.anim_groups = []

    seq_table = root.find(XmlNode.ANIMSEQTBL)
    if seq_table is not None:
        for seq_elem in seq_table.findall(XmlNode.ANIMSEQ):
            seq = AnimationSequence()

            for frame_elem in seq_elem.findall(XmlNode.ANIMFRM):
                af = AnimFrame()

                duration_elem = frame_elem.find(XmlProp.DURATION)
                if duration_elem is not None:
                    af.frame_duration = string_value_to_int(duration_elem.text or "0")

                meta_idx_elem = frame_elem.find(XmlProp.METAGRPIND)
                if meta_idx_elem is not None:
                    af.meta_frm_grp_index = string_value_to_int(
                        meta_idx_elem.text or "0"
                    )

                sprite_elem = frame_elem.find(XmlNode.SPRITE)
                if sprite_elem is not None:
                    af.spr_offset_x = string_value_to_int(
                        sprite_elem.find(XmlProp.OFFSETX).text or "0"
                    )
                    af.spr_offset_y = string_value_to_int(
                        sprite_elem.find(XmlProp.OFFSETY).text or "0"
                    )

                shadow_elem = frame_elem.find(XmlNode.SHADOW)
                if shadow_elem is not None:
                    af.shadow_offset_x = string_value_to_int(
                        shadow_elem.find(XmlProp.OFFSETX).text or "0"
                    )
                    af.shadow_offset_y = string_value_to_int(
                        shadow_elem.find(XmlProp.OFFSETY).text or "0"
                    )

                seq.insert_frame(af)

            sprite.anim_sequences.append(seq)

    group_table = root.find(XmlNode.ANIMGRPTBL)
    if group_table is not None:
        for group_elem in group_table.findall(XmlNode.ANIMGRP):
            group = SpriteAnimationGroup()

            for seq_ref in group_elem.findall(XmlProp.ANIMSEQIND):
                seq_idx = string_value_to_int(seq_ref.text or "0")
                group.seqs_indexes.append(seq_idx)

            sprite.anim_groups.append(group)


def read_offsets_xml(sprite: BaseSprite, xml_path: Path) -> None:
    """Read offsets.xml."""
    if not xml_path.exists():
        return

    tree = ET.parse(xml_path)
    root = tree.getroot()

    sprite.part_offsets = []

    for offset_elem in root.findall(XmlNode.OFFSET):
        offset = SprOffParticle()
        offset.offx = string_value_to_int(offset_elem.find(XmlProp.OFFSETX).text or "0")
        offset.offy = string_value_to_int(offset_elem.find(XmlProp.OFFSETY).text or "0")
        sprite.part_offsets.append(offset)


def read_imgsinfo_xml(sprite: BaseSprite, xml_path: Path) -> None:
    """Read imgsinfo.xml."""
    if not xml_path.exists():
        return

    tree = ET.parse(xml_path)
    root = tree.getroot()

    if not sprite.imgs_info:
        sprite.imgs_info = []

    for img_elem in root.findall(XmlNode.IMAGE):
        img_idx = string_value_to_int(img_elem.find(XmlProp.IMGINDEX).text or "0")
        zindex = string_value_to_int(img_elem.find(XmlProp.ZINDEX).text or "0")

        while len(sprite.imgs_info) <= img_idx:
            sprite.imgs_info.append(ImageInfo())

        sprite.imgs_info[img_idx].zindex = zindex
