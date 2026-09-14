"""Operational FCI template-50002 fixes for Astro Weather Backend 12.4.17.

Two assumptions in the first low-memory decoder were wrong for the real
EUMETSAT product:

* numberOfGroups is a 32-bit field and can legitimately be much larger than
  ecCodes' internal encoder optimisation limit of 65534;
* SPD is an array key. ``grib_get -p SPD`` uses a scalar getter and therefore
  fails with "Passed array is too small" even though the GRIB is valid.

This patch keeps the bounded-memory decoder, accepts operational group counts,
stores descriptor vectors compactly, and reads the tiny SPD descriptor directly
from Section 5 according to GRIB2 template 5.50002. No full-field ecCodes value
decode is used.
"""
from __future__ import annotations

from array import array
from pathlib import Path
from typing import Any, BinaryIO

import satellite_nowcast_patch as sat
import satellite_index_sampler_patch as index_sampler
import storage_protection_patch as storage
import satellite_card_map_patch as clm_map
import satellite_lowload_patch as lowload
import satellite_ui_patch as satellite_ui
import satellite_lowmem_patch as lowmem

RELEASE_VERSION = "12.4.17"
MAX_SECOND_ORDER_GROUPS = 2_000_000
MAX_DESCRIPTOR_WORKING_SET_BYTES = 64 * 1024 * 1024


def _section_range(grib_path: Path, wanted_section: int) -> tuple[int, int]:
    size = grib_path.stat().st_size
    with grib_path.open("rb") as handle:
        header = handle.read(16)
        if len(header) != 16 or header[:4] != b"GRIB":
            raise RuntimeError("FCI soubor nema platnou GRIB hlavicku")
        if header[7] != 2:
            raise RuntimeError(f"FCI soubor neni GRIB edition 2 (edition={header[7]})")
        total_length = int.from_bytes(header[8:16], "big")
        if total_length < 20 or total_length > size:
            raise RuntimeError(
                f"Neplatna delka GRIB zpravy {total_length} B pro soubor {size} B"
            )

        pos = 16
        while pos + 5 <= total_length - 4:
            handle.seek(pos)
            prefix = handle.read(5)
            if len(prefix) != 5:
                break
            section_length = int.from_bytes(prefix[:4], "big")
            section_number = prefix[4]
            if section_length < 5 or pos + section_length > total_length:
                raise RuntimeError(
                    f"Neplatna GRIB sekce {section_number} na offsetu {pos}: "
                    f"delka={section_length}"
                )
            if section_number == wanted_section:
                return pos, section_length
            pos += section_length
    raise RuntimeError(f"FCI GRIB neobsahuje Section {wanted_section}")


def _bits_from_blob(blob: bytes, bit_pos: int, width: int) -> int:
    if width <= 0 or width > 64:
        raise RuntimeError(f"Neocekavana bitova sirka {width}")
    bit_end = bit_pos + width
    if bit_pos < 0 or bit_end > len(blob) * 8:
        raise RuntimeError("Bitova hodnota presahuje dostupna GRIB data")
    byte_start = bit_pos // 8
    bit_offset = bit_pos % 8
    byte_count = (bit_offset + width + 7) // 8
    chunk = int.from_bytes(blob[byte_start:byte_start + byte_count], "big")
    shift = byte_count * 8 - bit_offset - width
    return (chunk >> shift) & ((1 << width) - 1)


def _signed_magnitude(raw: int, width: int) -> int:
    sign_mask = 1 << (width - 1)
    magnitude = raw & (sign_mask - 1)
    return -magnitude if raw & sign_mask else magnitude


def _read_spd_from_section5(grib_path: Path, expected_order: int) -> tuple[int, list[int]]:
    """Read SPD without asking grib_get to treat an array as a scalar key."""
    start, length = _section_range(grib_path, 5)
    with grib_path.open("rb") as handle:
        handle.seek(start)
        section = handle.read(length)

    if len(section) != length or len(section) < 34:
        raise RuntimeError("FCI Section 5 je zkracena")
    template = int.from_bytes(section[9:11], "big")
    if template != 50002:
        raise RuntimeError(f"SPD parser ocekava template 50002, nalezen {template}")

    # Template 5.50002: octet 33 = orderOfSPD, octet 34 = widthOfSPD,
    # octets 35... = order initial unsigned values + one signed-magnitude bias.
    order = int(section[32])
    width = int(section[33]) if order else 0
    if order != int(expected_order):
        raise RuntimeError(
            f"FCI orderOfSPD nesedi: metadata={expected_order}, Section5={order}"
        )
    if order == 0:
        return 0, []
    if not 1 <= width <= 64:
        raise RuntimeError(f"Neocekavane widthOfSPD={width}")

    count = order + 1
    spd_blob = section[34:]
    required_bits = count * width
    if required_bits > len(spd_blob) * 8:
        raise RuntimeError(
            f"FCI SPD je zkracene: potreba {required_bits} bitu, "
            f"k dispozici {len(spd_blob) * 8}"
        )

    values: list[int] = []
    bit_pos = 0
    for _ in range(order):
        values.append(_bits_from_blob(spd_blob, bit_pos, width))
        bit_pos += width
    bias_raw = _bits_from_blob(spd_blob, bit_pos, width)
    values.append(_signed_magnitude(bias_raw, width))
    return width, values


def _load_second_order_metadata(core: Any, grib_path: Path, meta: dict[str, Any]) -> None:
    out = core.run_cmd(["grib_get", "-p", lowmem._SECOND_ORDER_KEYS, str(grib_path)], timeout=30)
    parts = str(out).strip().split()
    if len(parts) < 8:
        raise RuntimeError(f"FCI second-order metadata jsou neuplna: {out!r}")

    try:
        meta.update({
            "width_of_first_order_values": int(parts[0]),
            "number_of_groups": int(parts[1]),
            "number_of_second_order_values": int(parts[2]),
            "width_of_widths": int(parts[3]),
            "width_of_lengths": int(parts[4]),
            "order_of_spd": int(parts[5]),
            "boustrophedonic": int(parts[6]),
            "number_of_points": int(parts[7]),
        })
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"FCI second-order metadata nelze precist: {out!r}") from exc

    groups = int(meta["number_of_groups"])
    packed_values = int(meta["number_of_second_order_values"])
    number_of_points = int(meta["number_of_points"])

    # numberOfGroups is an unsigned four-byte value in template 5.50002.
    # 65534 is an ecCodes encoder optimisation constant, not a format limit.
    if groups <= 0:
        raise RuntimeError(f"Neocekavany numberOfGroups={groups}")
    if groups > MAX_SECOND_ORDER_GROUPS:
        raise RuntimeError(
            f"FCI numberOfGroups={groups} prekrocil bezpecnostni limit "
            f"{MAX_SECOND_ORDER_GROUPS}"
        )
    if number_of_points <= 0 or number_of_points > int(meta["nx"]) * int(meta["ny"]):
        raise RuntimeError(f"Neocekavany numberOfPoints={number_of_points}")
    if packed_values < 0 or packed_values > number_of_points:
        raise RuntimeError(
            f"Neocekavany numberOfSecondOrderPackedValues={packed_values} "
            f"pro numberOfPoints={number_of_points}"
        )
    if groups > number_of_points:
        raise RuntimeError(
            f"FCI numberOfGroups={groups} je vetsi nez numberOfPoints={number_of_points}"
        )

    for key in ("width_of_first_order_values", "width_of_widths", "width_of_lengths"):
        width = int(meta[key])
        if not 0 <= width <= 64:
            raise RuntimeError(f"Neocekavana sirka {key}={width}")

    packed_descriptor_bytes = sum(
        (groups * int(meta[key]) + 7) // 8
        for key in ("width_of_widths", "width_of_lengths", "width_of_first_order_values")
    )
    compact_vector_bytes = groups * 8 * 3
    descriptor_working_set = packed_descriptor_bytes + compact_vector_bytes
    if descriptor_working_set > MAX_DESCRIPTOR_WORKING_SET_BYTES:
        raise RuntimeError(
            "FCI second-order descriptor metadata by prekrocila bezpecny pametovy limit: "
            f"odhad={descriptor_working_set / (1024 * 1024):.1f} MiB, "
            f"limit={MAX_DESCRIPTOR_WORKING_SET_BYTES / (1024 * 1024):.0f} MiB"
        )
    meta["descriptor_packed_bytes"] = packed_descriptor_bytes
    meta["descriptor_vector_bytes"] = compact_vector_bytes

    order = int(meta["order_of_spd"])
    if not 0 <= order <= 3:
        raise RuntimeError(f"Nepodporovany orderOfSPD={order}")
    if int(meta["boustrophedonic"]) not in (0, 1):
        raise RuntimeError(f"Neocekavany boustrophedonicOrdering={meta['boustrophedonic']}")

    width, spd = _read_spd_from_section5(grib_path, order)
    meta["width_of_spd"] = width
    meta["spd"] = spd


def _read_aligned_uint_array(
    handle: BinaryIO,
    offset: int,
    payload_end: int,
    count: int,
    width: int,
) -> tuple[array, int]:
    if count < 0:
        raise RuntimeError(f"Zaporny pocet packed hodnot: {count}")
    if width == 0:
        return array("Q", [0]) * count, offset

    byte_count = (count * width + 7) // 8
    if offset + byte_count > payload_end:
        raise RuntimeError(
            f"FCI descriptor pole presahuje Section 7: offset={offset}, bytes={byte_count}"
        )
    handle.seek(offset)
    blob = handle.read(byte_count)
    if len(blob) != byte_count:
        raise RuntimeError("FCI descriptor pole je zkracene")

    values = array("Q")
    mask = (1 << width) - 1
    bit_pos = 0
    append = values.append
    for _ in range(count):
        byte_start = bit_pos // 8
        bit_offset = bit_pos % 8
        width_bytes = (bit_offset + width + 7) // 8
        chunk = int.from_bytes(blob[byte_start:byte_start + width_bytes], "big")
        shift = width_bytes * 8 - bit_offset - width
        append((chunk >> shift) & mask)
        bit_pos += width

    return values, offset + byte_count


def install(core: Any) -> None:
    if getattr(core, "_SATELLITE_GROUP_PATCH_INSTALLED", False):
        return

    # The low-memory decoder resolves these module globals at call time.
    lowmem._load_second_order_metadata = _load_second_order_metadata
    lowmem._read_aligned_uint_array = _read_aligned_uint_array

    lowmem.RELEASE_VERSION = RELEASE_VERSION
    sat.RELEASE_VERSION = RELEASE_VERSION
    index_sampler.RELEASE_VERSION = RELEASE_VERSION
    storage.RELEASE_VERSION = RELEASE_VERSION
    clm_map.RELEASE_VERSION = RELEASE_VERSION
    lowload.RELEASE_VERSION = RELEASE_VERSION
    satellite_ui.RELEASE_VERSION = RELEASE_VERSION
    core.APP_VERSION = RELEASE_VERSION
    core.Handler.server_version = f"AstroWeatherBackend/{RELEASE_VERSION}"
    core._SATELLITE_GROUP_PATCH_INSTALLED = True
