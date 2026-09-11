"""Robust cloud consensus for independent weather-model families."""
from __future__ import annotations

from typing import Any
import weather_models as wm


def cloud_consensus(values: dict[str, Any], warn: float = 35.0, bad: float = 55.0) -> dict[str, Any]:
    """Estimate cloud conservatively without invented fixed model weights."""
    points = sorted(
        ((str(name), value) for name, raw in values.items() if (value := wm.cloud(raw)) is not None),
        key=lambda item: item[1],
    )
    count = len(points)
    out = {
        "model_count": count,
        "model_names": [name for name, _ in points],
        "spread": None,
        "confidence": 0.0,
        "agreement": "none",
        "outlier": False,
        "outlier_name": None,
        "strong_disagreement": False,
        "median": None,
        "effective": None,
    }
    if count == 0:
        return out
    if count == 1:
        out.update(spread=0.0, confidence=45.0, agreement="single",
                   median=points[0][1], effective=points[0][1])
        return out

    low, high = points[0][1], points[-1][1]
    spread = high - low
    out["spread"] = spread
    if count == 2:
        mean = (low + high) / 2.0
        # Exactly the 12.1.12 total-cloud formula.
        effective = 0.70 * high + 0.30 * mean
        confidence = max(25.0, min(100.0, 100.0 - spread * 1.05))
        strong = spread >= bad and low <= 30 and high >= 60
        out.update(
            confidence=confidence,
            agreement="conflict" if strong else "reduced" if spread >= warn else "good",
            strong_disagreement=strong,
            median=mean,
            effective=effective,
        )
        return out

    numbers = [value for _, value in points]
    middle = count // 2
    median = numbers[middle] if count % 2 else (numbers[middle - 1] + numbers[middle]) / 2
    effective = min(100.0, median + 0.20 * spread)
    outlier = False
    outlier_name = None
    if count == 3 and spread >= warn:
        left_gap, right_gap = numbers[1] - numbers[0], numbers[2] - numbers[1]
        if min(left_gap, right_gap) <= max(5.0, warn / 2.0):
            outlier = True
            outlier_name = points[2][0] if left_gap <= right_gap else points[0][0]

    if spread <= warn:
        confidence, agreement = max(65.0, 100.0 - spread), "good"
    elif outlier:
        confidence, agreement = max(50.0, min(75.0, 75.0 - 0.35 * spread)), "outlier"
    else:
        confidence = max(25.0, min(60.0, 60.0 - 0.50 * spread))
        agreement = "conflict" if spread >= bad else "reduced"
    strong = not outlier and spread >= bad and low <= 30 and high >= 60
    out.update(
        confidence=confidence,
        agreement=agreement,
        outlier=outlier,
        outlier_name=outlier_name,
        strong_disagreement=strong,
        median=median,
        effective=effective,
    )
    return out


def _final_cloud(core: Any, row: dict[str, Any], options: dict[str, Any]) -> tuple[dict[str, Any], float | None]:
    met = row.get("met") if isinstance(row.get("met"), dict) else {}
    aladin = row.get("aladin") if isinstance(row.get("aladin"), dict) else {}
    icon = row.get("icon") if isinstance(row.get("icon"), dict) else wm.ICON_ROWS.get(str(row.get("datetime")), {})
    result = cloud_consensus(
        {"MET": met.get("cloud_total"), "ALADIN": aladin.get("cloud_total"), "ICON": icon.get("cloud_total")},
        float(options["disagreement_warn"]),
        float(options["disagreement_bad"]),
    )
    effective = result["effective"]
    if effective is None:
        return result, None

    highs = [wm.cloud(met.get("cloud_high")), wm.cloud(aladin.get("cloud_high")), wm.cloud(icon.get("cloud_high"))]
    highs = [value for value in highs if value is not None]
    if result["model_count"] <= 2:
        # Preserve the 12.1.12 high-cloud boost exactly when only two models exist.
        if highs:
            effective = max(float(effective), max(highs) * 0.85)
    elif highs:
        high_result = cloud_consensus(
            {"MET": met.get("cloud_high"), "ALADIN": aladin.get("cloud_high"), "ICON": icon.get("cloud_high")},
            float(options["disagreement_warn"]),
            float(options["disagreement_bad"]),
        )
        if high_result["effective"] is not None:
            effective = max(float(effective), float(high_result["effective"]) * 0.85)
    return result, min(100.0, effective)


def score_hour_wrapped(core: Any, original: Any, row: dict[str, Any], moon_hour: Any,
                       night: dict[str, Any], options: dict[str, Any]) -> dict[str, Any]:
    consensus, effective = _final_cloud(core, row, options)
    met = row.get("met") if isinstance(row.get("met"), dict) else None
    aladin = row.get("aladin") if isinstance(row.get("aladin"), dict) else None
    icon = row.get("icon") if isinstance(row.get("icon"), dict) else wm.ICON_ROWS.get(str(row.get("datetime")))
    mt = core.safe_float(met.get("cloud_total")) if met else None
    at = core.safe_float(aladin.get("cloud_total")) if aladin else None
    it = core.safe_float(icon.get("cloud_total")) if isinstance(icon, dict) else None

    if effective is None:
        scored = original(row, moon_hour, night, options)
    else:
        # Use the proven 12.1.12 scorer for every non-cloud penalty and veto.
        synthetic = dict(row)
        synthetic_met = dict(met or {})
        synthetic_met.update(cloud_total=effective, cloud_high=0.0)
        synthetic["met"] = synthetic_met
        synthetic["aladin"] = {"cloud_total": effective, "cloud_high": 0.0}
        scored = original(synthetic, moon_hour, night, options)

    spread = consensus["spread"]
    confidence = float(consensus["confidence"])
    moon_uncertain = any("Měsíc – chybí hodinový detail" in str(r) for r in scored.get("reasons", []))
    if moon_uncertain:
        confidence = min(confidence, 45.0)

    precip = core.safe_float(scored.get("precip"))
    fog = core.safe_float(scored.get("fog"))
    wind = core.safe_float(scored.get("wind"))
    aod = core.safe_float(scored.get("aod550"))
    seeing = core.safe_float(scored.get("seeingArcsec"))
    hard_bad = bool(
        (precip is not None and precip > 0)
        or (fog is not None and fog >= 20)
        or (wind is not None and wind >= options["wind_bad_ms"])
        or scored.get("moonInterferes")
        or (scored.get("aerosolApplied") and aod is not None and aod >= options["aod_bad"])
        or (scored.get("seeingApplied") and seeing is not None and seeing >= options["seeing_bad_arcsec"])
    )
    aod_uncertain = bool(scored.get("aerosolApplied") and aod is not None and aod >= options["aod_warn"])
    seeing_uncertain = bool(scored.get("seeingApplied") and seeing is not None and seeing >= options["seeing_warn_arcsec"])
    score = float(scored.get("score") or 0)
    strong = bool(consensus["strong_disagreement"])
    if hard_bad:
        status = "bad"
    elif strong or moon_uncertain or (aod_uncertain and score >= options["marginal_score"]) or (seeing_uncertain and score >= options["marginal_score"]):
        status = "uncertain"
    elif score >= options["good_score"] and confidence >= 50:
        status = "good"
    elif score >= options["marginal_score"]:
        status = "partial"
    else:
        status = "bad"

    reasons = [str(r) for r in scored.get("reasons", [])
               if "MET/ALADIN rozdíl" not in str(r) and "nejistota modelů" not in str(r)]
    if strong and spread is not None:
        reasons.append(f"konflikt modelů {spread:.0f} p.b.")
    elif consensus["outlier"] and spread is not None:
        reasons.append(f"{consensus['outlier_name']} mimo shodu modelů ({spread:.0f} p.b.)")
    elif spread is not None and spread >= options["disagreement_warn"]:
        reasons.append(f"nejistota modelů {spread:.0f} p.b.")

    scored.update(
        status=status,
        confidence=round(confidence, 1),
        reasons=reasons,
        metTotal=core.round_or_none(mt),
        aladinTotal=core.round_or_none(at),
        iconTotal=core.round_or_none(it),
        disagreement=core.round_or_none(spread),
        modelSpread=core.round_or_none(spread),
        modelCount=consensus["model_count"],
        modelNames=consensus["model_names"],
        modelAgreement=consensus["agreement"],
        modelOutlier=bool(consensus["outlier"]),
        modelOutlierName=consensus["outlier_name"],
        strongDisagreement=strong,
        effectiveCloud=core.round_or_none(effective),
        metAvailable=mt is not None,
        aladinAvailable=at is not None,
        iconAvailable=it is not None,
    )
    return scored
