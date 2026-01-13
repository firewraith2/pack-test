"""
XML writer functions for sprite data structures.
Handles writing frames.xml, animations.xml, spriteinfo.xml, offsets.xml, and imgsinfo.xml
"""

import xml.etree.ElementTree as ET
from pathlib import Path

from wan_files.sprite import (
    BaseSprite,
)
from .constants import ExternalFiles, XmlRoot, XmlNode, XmlProp
from data import (
    int_value_to_string,
    enum_res_to_integer,
    write_xml_file,
)


def write_sprite_xml(sprite: BaseSprite, output_dir: Path) -> None:
    """Write all XML files for a sprite."""
    write_spriteinfo_xml(sprite, output_dir / ExternalFiles.SPRITEINFO_FILE)
    write_frames_xml(sprite, output_dir / ExternalFiles.FRAMES_FILE)
    write_animations_xml(sprite, output_dir / ExternalFiles.ANIMATIONS_FILE)
    write_offsets_xml(sprite, output_dir / ExternalFiles.OFFSETS_FILE)
    write_imgsinfo_xml(sprite, output_dir / ExternalFiles.IMGSINFO_FILE)


def write_spriteinfo_xml(sprite: BaseSprite, output_path: Path) -> None:
    """Write spriteinfo.xml with all sprite properties."""
    root = ET.Element(XmlRoot.SPRPROPS)

    info = sprite.spr_info

    ET.SubElement(root, XmlProp.BOOL_UNK3).text = int_value_to_string(info.bool_unk3)
    ET.SubElement(root, XmlProp.MAXCOLUSED).text = int_value_to_string(
        info.max_colors_used
    )
    ET.SubElement(root, XmlProp.UNK4).text = int_value_to_string(info.unk4)
    ET.SubElement(root, XmlProp.UNK5).text = int_value_to_string(info.unk5)
    ET.SubElement(root, XmlProp.MAXMEMUSED).text = int_value_to_string(
        info.max_memory_used
    )
    ET.SubElement(root, XmlProp.CONST0_UNK7).text = int_value_to_string(
        info.const0_unk7
    )
    ET.SubElement(root, XmlProp.CONST0_UNK8).text = int_value_to_string(
        info.const0_unk8
    )
    ET.SubElement(root, XmlProp.BOOL_UNK9).text = int_value_to_string(info.bool_unk9)
    ET.SubElement(root, XmlProp.CONST0_UNK10).text = int_value_to_string(
        info.const0_unk10
    )
    ET.SubElement(root, XmlProp.SPRTY).text = int_value_to_string(info.sprite_type)
    ET.SubElement(root, XmlProp.IS8BPPSPRITE).text = int_value_to_string(
        info.is_8bpp_sprite
    )
    ET.SubElement(root, XmlProp.TILESMODE).text = int_value_to_string(info.tiles_mode)
    ET.SubElement(root, XmlProp.PALSLOTSUSED).text = int_value_to_string(
        info.palette_slots_used
    )
    ET.SubElement(root, XmlProp.CONST0_UNK12).text = int_value_to_string(
        info.const0_unk12
    )

    write_xml_file(root, output_path)


def write_frames_xml(sprite: BaseSprite, output_path: Path) -> None:
    """Write frames.xml with meta-frames and frame groups."""
    root = ET.Element(XmlRoot.FRMLST)

    for group in sprite.metaframe_groups:
        group_elem = ET.SubElement(root, XmlNode.FRMGRP)

        for mf_idx in group.metaframes:
            if mf_idx < len(sprite.metaframes):
                mf = sprite.metaframes[mf_idx]
                frame_elem = ET.SubElement(group_elem, XmlNode.FRAME)

                ET.SubElement(frame_elem, XmlProp.IMGINDEX).text = int_value_to_string(
                    mf.image_index
                )

                ET.SubElement(frame_elem, XmlProp.UNK0).text = int_value_to_string(
                    mf.unk0
                )

                offset_elem = ET.SubElement(frame_elem, XmlNode.OFFSET)
                ET.SubElement(offset_elem, XmlProp.OFFSET_X).text = int_value_to_string(
                    mf.offset_x
                )
                ET.SubElement(offset_elem, XmlProp.OFFSET_Y).text = int_value_to_string(
                    mf.offset_y
                )

                ET.SubElement(frame_elem, XmlProp.MEMOFFSET).text = int_value_to_string(
                    mf.memory_offset
                )
                ET.SubElement(frame_elem, XmlProp.PALOFFSET).text = int_value_to_string(
                    mf.palette_offset
                )

                width, height = enum_res_to_integer(mf.resolution)
                res_elem = ET.SubElement(frame_elem, XmlNode.RESOLUTION)
                ET.SubElement(res_elem, XmlProp.WIDTH).text = int_value_to_string(width)
                ET.SubElement(res_elem, XmlProp.HEIGHT).text = int_value_to_string(
                    height
                )

                ET.SubElement(frame_elem, XmlProp.HFLIP).text = int_value_to_string(
                    mf.h_flip
                )
                ET.SubElement(frame_elem, XmlProp.VFLIP).text = int_value_to_string(
                    mf.v_flip
                )
                ET.SubElement(frame_elem, XmlProp.MOSAIC).text = int_value_to_string(
                    mf.mosaic
                )
                ET.SubElement(frame_elem, XmlProp.ISABSOLUTEPALETTE).text = (
                    int_value_to_string(mf.is_absolute_palette)
                )
                ET.SubElement(frame_elem, XmlProp.CONST0_XOFFBIT7).text = (
                    int_value_to_string(mf.const0_x_off_bit7)
                )
                ET.SubElement(frame_elem, XmlProp.BOOL_YOFFBIT3).text = (
                    int_value_to_string(mf.bool_y_off_bit3)
                )
                ET.SubElement(frame_elem, XmlProp.CONST0_YOFFBIT5).text = (
                    int_value_to_string(mf.const0_y_off_bit5)
                )
                ET.SubElement(frame_elem, XmlProp.CONST0_YOFFBIT6).text = (
                    int_value_to_string(mf.const0_y_off_bit6)
                )

    write_xml_file(root, output_path)


def write_animations_xml(sprite: BaseSprite, output_path: Path) -> None:
    """Write animations.xml with animation sequences and groups."""
    root = ET.Element(XmlRoot.ANIMDAT)

    group_table = ET.SubElement(root, XmlNode.ANIMGRPTBL)
    for group in sprite.anim_groups:
        group_elem = ET.SubElement(group_table, XmlNode.ANIMGRP)

        for seq_idx in group.seqs_indexes:
            seq_ref = ET.SubElement(group_elem, XmlProp.ANIMSEQIND)
            seq_ref.text = int_value_to_string(seq_idx)

    seq_table = ET.SubElement(root, XmlNode.ANIMSEQTBL)
    for seq in sprite.anim_sequences:
        seq_elem = ET.SubElement(seq_table, XmlNode.ANIMSEQ)

        for frame in seq.frames:
            frame_elem = ET.SubElement(seq_elem, XmlNode.ANIMFRM)
            ET.SubElement(frame_elem, XmlProp.DURATION).text = int_value_to_string(
                frame.frame_duration
            )
            ET.SubElement(frame_elem, XmlProp.METAGRPIND).text = int_value_to_string(
                frame.meta_frm_grp_index
            )

            sprite_elem = ET.SubElement(frame_elem, XmlNode.SPRITE)
            ET.SubElement(sprite_elem, XmlProp.OFFSETX).text = int_value_to_string(
                frame.spr_offset_x
            )
            ET.SubElement(sprite_elem, XmlProp.OFFSETY).text = int_value_to_string(
                frame.spr_offset_y
            )

            shadow_elem = ET.SubElement(frame_elem, XmlNode.SHADOW)
            ET.SubElement(shadow_elem, XmlProp.OFFSETX).text = int_value_to_string(
                frame.shadow_offset_x
            )
            ET.SubElement(shadow_elem, XmlProp.OFFSETY).text = int_value_to_string(
                frame.shadow_offset_y
            )
    write_xml_file(root, output_path)


def write_offsets_xml(sprite: BaseSprite, output_path: Path) -> None:
    """Write offsets.xml with particle offsets."""
    root = ET.Element(XmlRoot.OFFLST)

    for offset in sprite.part_offsets:
        offset_elem = ET.SubElement(root, XmlNode.OFFSET)
        ET.SubElement(offset_elem, XmlProp.OFFSETX).text = int_value_to_string(
            offset.offx
        )
        ET.SubElement(offset_elem, XmlProp.OFFSETY).text = int_value_to_string(
            offset.offy
        )

    write_xml_file(root, output_path)


def write_imgsinfo_xml(sprite: BaseSprite, output_path: Path) -> None:
    """Write imgsinfo.xml with image properties."""
    root = ET.Element(XmlRoot.IMGINFO)

    for img_idx, img_info in enumerate(sprite.imgs_info):
        img_elem = ET.SubElement(root, XmlNode.IMAGE)
        ET.SubElement(img_elem, XmlProp.IMGINDEX).text = int_value_to_string(img_idx)
        ET.SubElement(img_elem, XmlProp.ZINDEX).text = int_value_to_string(
            img_info.zindex
        )

    write_xml_file(root, output_path)
