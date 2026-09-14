"""Operational second-order group fix for Astro Weather Backend 12.4.16.

EUMETSAT's current MTG/FCI CLM GRIB2 template 5.50002 can legitimately contain
hundreds of thousands of second-order groups. Release 12.4.15 inherited an
internal ecCodes *packing* limit (65534) as a decoder validation limit and
therefore rejected a real operational product with numberOfGroups=436159.

This patch removes that incorrect decoder limit while keeping hard memory
bounds. The three descriptor vectors are stored in compact unsigned-64 arrays
instead of Python int lists, so the observed 436159-group product needs only
about 10 MiB for the decoded descriptor vectors rather than tens of MiB.
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

RELEASE_VERSION = "12.4.16"
MAX_SECOND_ORDER_GROUPS = 2_000_000
MAX_DESCRIPTOR_WORKING_SET_BYTES = 64 * 1024 * 1024


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

    # GRIB2 local template 5.50002 stores numberOfGroups as an unsigned 4-byte
    # field. The old 65534 limit belongs to an ecCodes encoder path; it is not a
    # valid decoding limit for externally produced EUMETSAT files.
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

    if order:
        width_out = core.run_cmd(["grib_get", "-p", "widthOfSPD", str(grib_path)], timeout=30)
        width_tokens = lowmem._parse_ints(str(width_out))
        if not width_tokens:
            raise RuntimeError(f"FCI widthOfSPD nelze precist: {width_out!r}")
        meta["width_of_spd"] = int(width_tokens[0])
        if not 1 <= int(meta["width_of_spd"]) <= 64:
            raise RuntimeError(f"Neocekavane widthOfSPD={meta['width_of_spd']}")

        spd_out = core.run_cmd(["grib_get", "-p", "SPD", str(grib_path)], timeout=30)
        spd = lowmem._parse_ints(str(spd_out))
        expected = order + 1
        if len(spd) != expected:
            raise RuntimeError(
                f"FCI SPD ma {len(spd)} hodnot, ocekavano {expected}: {spd_out!r}"
            )
        meta["spd"] = spd
    else:
        meta["width_of_spd"] = 0
        meta["spd"] = []


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

    # lowmem._metadata and _second_order_layout resolve these names at call
    # time, so replacing the module globals is enough; the sampler itself stays
    # the 12.4.15 bounded-memory implementation.
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
