from __future__ import annotations

"""Frozen-data ReportLab builder for the economy analysis PDF.

This module never imports runtime Garden catalogs.  A catalog hash mismatch or
failed correctness or configuration assertion prevents authoring, so the PDF
cannot silently mix two source snapshots.  Balance-target misses remain visible
but non-blocking: they are findings to review, not proof that the simulator is
invalid.
"""

from dataclasses import dataclass
import math
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence, Tuple


@dataclass(frozen=True)
class ReportSection:
    section_id: str
    title: str
    subtitle: str


REPORT_SECTIONS: Tuple[ReportSection, ...] = (
    ReportSection("cover", "Economy, Progression, and Rewards", "Scope and source snapshot"),
    ReportSection("scorecard", "Executive scorecard", "Release targets and top modeled risks"),
    ReportSection("catalog", "Complete catalog map", "Every purchasable and earnable record"),
    ReportSection("permanent", "Permanent purchases", "Finite costs and acquisition routes"),
    ReportSection("earnable", "Earnable and repeatable items", "Finds, consumables, and unavailable entries"),
    ReportSection("progression", "Progression pacing", "Stage and Full Bloom timing"),
    ReportSection("growth", "Growth capacity", "Shared Growth, application, and storage"),
    ReportSection("coins", "Coin economy", "Sources, sinks, and concentration"),
    ReportSection("strategy", "Affordability and strategy", "Collection-first pacing across cohorts"),
    ReportSection("consumables", "Consumables", "Value, use, and speed sensitivity"),
    ReportSection("environments", "Garden bonuses and scenery", "Effects, conditions, and payback"),
    ReportSection("finds", "Standard Finds", "Expected value, cap, and guarantee"),
    ReportSection("discoveries", "Environment discoveries", "Tier distributions and hard guarantees"),
    ReportSection("fairness", "Fairness and endgame", "Cohort normalization and post-catalog risk"),
    ReportSection("method", "Method and limitations", "Seeds, assertions, and reproducibility"),
)


REPRESENTATIVE_STRATEGY_ID = "collection_first"
REPRESENTATIVE_CASE_ID = "baseline"
REPRESENTATIVE_CHECKPOINT_DAY = 365
EXPECTED_PERMANENT_COIN_DEMAND = 19_775


def validate_frozen_report(report: Mapping[str, Any]) -> None:
    required = {
        "$schema",
        "run",
        "catalog",
        "analysis",
        "scenario_matrix",
        "statistics",
        "milestones",
        "assertions",
        "parity",
        "findings",
    }
    missing = sorted(required - set(report))
    if missing:
        raise ValueError(f"frozen report is missing keys: {missing}")
    run = report.get("run")
    catalog = report.get("catalog")
    analysis = report.get("analysis")
    if not all(isinstance(value, Mapping) for value in (run, catalog, analysis)):
        raise ValueError("run, catalog, and analysis must be objects")
    if not run.get("run_id"):
        raise ValueError("frozen report has no run_id")
    if run.get("catalog_sha256") != catalog.get("sha256"):
        raise ValueError("run/catalog hash mismatch")
    if int(run.get("seed_count", 0) or 0) <= 0:
        raise ValueError("frozen report has no seeds")
    failures = [
        row for row in report.get("assertions", ())
        if (
            isinstance(row, Mapping)
            and row.get("status") != "pass"
            and str(row.get("class", "correctness"))
            in {"correctness", "configuration"}
        )
    ]
    if failures:
        raise ValueError(f"frozen report contains failed assertions: {failures}")
    metric_refs = {
        f"{row.get('scenario_id')}|{row.get('checkpoint_day')}|{row.get('metric_id')}"
        for row in report.get("statistics", ())
        if isinstance(row, Mapping)
    }
    for finding in report.get("findings", ()):
        if not isinstance(finding, Mapping):
            continue
        unknown = sorted(set(finding.get("metric_refs", ())) - metric_refs)
        if unknown:
            raise ValueError(
                f"finding {finding.get('finding_id')} has unknown metric refs: {unknown}"
            )


def report_outline(report: Mapping[str, Any]) -> Sequence[Mapping[str, str]]:
    validate_frozen_report(report)
    return tuple({
        "section_id": section.section_id,
        "title": section.title,
        "subtitle": section.subtitle,
    } for section in REPORT_SECTIONS)


def _cohort_ids(report: Mapping[str, Any]) -> Tuple[str, ...]:
    matrix = report.get("scenario_matrix", {})
    if not isinstance(matrix, Mapping):
        return ()
    cohorts = matrix.get("cohorts", ())
    if not isinstance(cohorts, Sequence) or isinstance(cohorts, (str, bytes)):
        return ()
    return tuple(
        str(row.get("cohort_id", ""))
        for row in cohorts
        if isinstance(row, Mapping) and str(row.get("cohort_id", ""))
    )


def _scenario_id(
    report: Mapping[str, Any],
    cohort_id: str,
    strategy_id: str,
    case_id: str,
) -> str:
    matrix = report.get("scenario_matrix", {})
    scenarios = matrix.get("scenarios", ()) if isinstance(matrix, Mapping) else ()
    for row in scenarios if isinstance(scenarios, Sequence) else ():
        if not isinstance(row, Mapping):
            continue
        if (
            row.get("cohort_id") == cohort_id
            and row.get("strategy_id") == strategy_id
            and row.get("case_id") == case_id
        ):
            return str(row.get("scenario_id", ""))
    return ""


def representative_statistic_rows(
    report: Mapping[str, Any],
    metric_id: str,
    *,
    checkpoint_day: int = REPRESENTATIVE_CHECKPOINT_DAY,
    strategy_id: str = REPRESENTATIVE_STRATEGY_ID,
    case_id: str = REPRESENTATIVE_CASE_ID,
) -> Sequence[Mapping[str, Any]]:
    """Return one declared-policy row for every cohort, in matrix order.

    Alphabetical truncation made the old report look comprehensive while it
    happened to show only the first few scenarios.  The explicit policy here
    keeps every metric page comparable and ensures all six approved cohorts are
    represented.
    """

    rows = {
        str(row.get("scenario_id", "")): row
        for row in report.get("statistics", ())
        if (
            isinstance(row, Mapping)
            and row.get("metric_id") == metric_id
            and int(row.get("checkpoint_day", 0) or 0) == checkpoint_day
            and row.get("strategy_id") == strategy_id
            and row.get("case_id") == case_id
        )
    }
    selected = []
    for cohort_id in _cohort_ids(report):
        scenario_id = _scenario_id(report, cohort_id, strategy_id, case_id)
        if scenario_id in rows:
            selected.append(rows[scenario_id])
    return tuple(selected)


def _statistic(
    report: Mapping[str, Any],
    *,
    cohort_id: str,
    metric_id: str,
    strategy_id: str = REPRESENTATIVE_STRATEGY_ID,
    case_id: str = REPRESENTATIVE_CASE_ID,
    checkpoint_day: int = REPRESENTATIVE_CHECKPOINT_DAY,
) -> Optional[Mapping[str, Any]]:
    scenario_id = _scenario_id(report, cohort_id, strategy_id, case_id)
    return next((
        row for row in report.get("statistics", ())
        if (
            isinstance(row, Mapping)
            and row.get("scenario_id") == scenario_id
            and row.get("metric_id") == metric_id
            and int(row.get("checkpoint_day", 0) or 0) == checkpoint_day
        )
    ), None)


def _criterion(
    criterion_id: str,
    status: str,
    criterion: str,
    evidence: str,
    target: str,
) -> Mapping[str, str]:
    return {
        "criterion_id": criterion_id,
        "status": status,
        "criterion": criterion,
        "evidence": evidence,
        "target": target,
    }


def _numeric_status(value: Any, predicate) -> str:
    if not isinstance(value, (int, float)):
        return "not modeled"
    return "pass" if predicate(float(value)) else "attention"


def balance_scorecard_rows(report: Mapping[str, Any]) -> Sequence[Mapping[str, str]]:
    """Evaluate supplied release targets without turning them into build gates."""

    analysis = report.get("analysis", {})
    analysis = analysis if isinstance(analysis, Mapping) else {}
    growth = analysis.get("growth", {})
    growth = growth if isinstance(growth, Mapping) else {}
    coins = analysis.get("coins", {})
    coins = coins if isinstance(coins, Mapping) else {}

    rows = []
    full_bloom = growth.get("full_bloom_growth")
    base_growth = growth.get("base_growth_per_review")
    if (
        isinstance(full_bloom, (int, float))
        and isinstance(base_growth, (int, float))
        and base_growth > 0
    ):
        base_cards = math.ceil(float(full_bloom) / float(base_growth))
        active_days = math.ceil(base_cards / 10)
        status = "pass" if active_days <= 365 else "attention"
        evidence = f"{active_days:,} active days ({base_cards:,} base cards)"
    else:
        status = "not modeled"
        evidence = "Threshold or base Growth is unavailable"
    rows.append(_criterion(
        "PACE-10-FIRST-FULL-BLOOM",
        status,
        "10 cards/day reaches a first Full Bloom",
        evidence,
        "Within 365 active days",
    ))

    for criterion_id, cohort_id, label, low, high in (
        ("PACE-25-FULL-BLOOMS", "light", "25-card cohort Full Blooms", 2, None),
        ("PACE-100-FULL-BLOOMS", "headline", "100-card cohort Full Blooms", 8, 10),
    ):
        statistic = _statistic(report, cohort_id=cohort_id, metric_id="plants.full_bloom")
        median = statistic.get("p50") if statistic else None
        predicate = (
            (lambda value, minimum=low: value >= minimum)
            if high is None
            else (lambda value, minimum=low, maximum=high: minimum <= value <= maximum)
        )
        rows.append(_criterion(
            criterion_id,
            _numeric_status(median, predicate),
            label,
            f"Median {_fmt(median, 0)} plants at day 365",
            f"At least {low}" if high is None else f"{low} to {high}",
        ))

    core_cost = sum(
        int(coins.get("permanent_cost_by_category", {}).get(category, 0) or 0)
        for category in ("species", "garden_bonus", "scenery")
    ) if isinstance(coins.get("permanent_cost_by_category", {}), Mapping) else 0
    light_coins = _statistic(report, cohort_id="light", metric_id="coins.gross")
    light_gross = light_coins.get("p50") if light_coins else None
    rows.append(_criterion(
        "COINS-25-CORE-AFFORDABILITY",
        (
            _numeric_status(light_gross, lambda value: value >= core_cost)
            if core_cost > 0 else "not modeled"
        ),
        "25-card cohort gross Coin sufficiency for the core catalog",
        f"Median gross {_fmt(light_gross, 0)} Coins vs {_fmt(core_cost, 0)} required",
        "Gross Coins at least core plant, bonus, and scenery cost",
    ))

    record_counts = {}
    catalog = report.get("catalog", {})
    records = catalog.get("records", ()) if isinstance(catalog, Mapping) else ()
    for record in records if isinstance(records, Sequence) else ():
        if isinstance(record, Mapping):
            category = str(record.get("category", ""))
            record_counts[category] = record_counts.get(category, 0) + 1
    landmark_target = record_counts.get("landmark", 0)
    mastery_target = record_counts.get("species", 0) * record_counts.get("mastery", 0)

    def endgame_status(cohort_id: str) -> Tuple[str, str]:
        landmarks = _statistic(
            report,
            cohort_id=cohort_id,
            strategy_id="optimal_coin",
            case_id="landmark_mastery",
            metric_id="landmarks.owned",
        )
        mastery = _statistic(
            report,
            cohort_id=cohort_id,
            strategy_id="optimal_coin",
            case_id="landmark_mastery",
            metric_id="mastery.owned",
        )
        landmark_max = landmarks.get("max") if landmarks else None
        mastery_max = mastery.get("max") if mastery else None
        if (
            landmark_target <= 0
            or mastery_target <= 0
            or not all(
                isinstance(value, (int, float))
                for value in (landmark_max, mastery_max)
            )
        ):
            return "not modeled", "Endgame scenario unavailable"
        open_for_every_seed = (
            float(landmark_max) < landmark_target
            or float(mastery_max) < mastery_target
        )
        return (
            "pass" if open_for_every_seed else "attention",
            (
                f"max {_fmt(landmark_max, 0)}/{landmark_target} Landmarks; "
                f"{_fmt(mastery_max, 0)}/{mastery_target} Mastery"
            ),
        )

    headline_status, headline_evidence = endgame_status("headline")
    rows.append(_criterion(
        "ENDGAME-100-REMAINS-OPEN",
        headline_status,
        "100-card cohort retains permanent endgame demand",
        headline_evidence,
        "At least one Landmark or Mastery target remains in every seed",
    ))
    endgame_results = [endgame_status(cohort_id) for cohort_id in ("heavy", "power")]
    if any(status == "not modeled" for status, _evidence in endgame_results):
        endgame_combined_status = "not modeled"
    else:
        endgame_combined_status = (
            "pass" if all(status == "pass" for status, _evidence in endgame_results)
            else "attention"
        )
    rows.append(_criterion(
        "ENDGAME-200-400-REMAINS-OPEN",
        endgame_combined_status,
        "200- and 400-card cohorts retain an endgame target",
        "; ".join(
            f"{cohort}: {evidence}"
            for cohort, (_status, evidence) in zip(("200", "400"), endgame_results)
        ),
        "At least one Landmark or Mastery target remains in every seed",
    ))

    permanent_total = coins.get("permanent_cost_total")
    rows.append(_criterion(
        "COINS-PERMANENT-DEMAND",
        _numeric_status(
            permanent_total,
            lambda value: value == EXPECTED_PERMANENT_COIN_DEMAND,
        ),
        "Long-term permanent Coin demand matches the release specification",
        f"{_fmt(permanent_total, 0)} Coins",
        f"{EXPECTED_PERMANENT_COIN_DEMAND:,} Coins",
    ))

    speed_rows = analysis.get("optional_speed_sensitivity", {})
    speed_rows = speed_rows.get("rows", ()) if isinstance(speed_rows, Mapping) else ()
    fertilizers = [
        row for row in speed_rows
        if isinstance(row, Mapping) and str(row.get("item_id", "")).startswith("fertilizer_")
    ] if isinstance(speed_rows, Sequence) else []
    if not fertilizers:
        fertilizer_status = "not modeled"
        fertilizer_evidence = "No purchasable Fertilizer rows"
    else:
        invariant = all(
            row.get("growth_per_coin_is_speed_invariant") is True
            for row in fertilizers
        )
        fertilizer_status = "pass" if invariant else "attention"
        fertilizer_evidence = f"{len(fertilizers)} tiers; " + (
            "all invariant" if invariant else "speed variance detected"
        )
    rows.append(_criterion(
        "FAIRNESS-FERTILIZER-SPEED",
        fertilizer_status,
        "Purchased Fertilizer value is independent of review speed",
        fertilizer_evidence,
        "Every purchasable tier is speed-invariant",
    ))
    return tuple(rows)


def _fmt(value: Any, digits: int = 1) -> str:
    if value is None or value == "":
        return "Not reached"
    if isinstance(value, float):
        return f"{value:,.{digits}f}"
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def catalog_record_price_status(
    category: str,
    definition: Mapping[str, Any],
) -> str:
    """Return the compact acquisition/cost label used by catalog pages."""

    price = next((
        definition.get(key) for key in (
            "purchase_price_coins",
            "price_coins",
            "cost_coins",
            "price",
            "unlock_cost",
            "coin_cost",
        ) if definition.get(key) is not None
    ), None)
    growth_cost = definition.get("growth_cost")
    if category == "species" and isinstance(price, (int, float)):
        return f"{int(price):,} C; one starter free"
    if category in {"landmark", "mastery"} and all(
        isinstance(value, (int, float)) for value in (growth_cost, price)
    ):
        suffix = " / species" if category == "mastery" else ""
        return f"{int(growth_cost):,} G + {int(price):,} C{suffix}"
    if category == "bed":
        if definition.get("included") is True:
            return "Included"
        achievement = str(definition.get("source_achievement_id", "")).strip()
        if achievement:
            return "Achievement: " + achievement.replace("_", " ").title()
    if isinstance(price, (int, float)):
        return f"{int(price):,} Coins"
    achievement = str(definition.get("source_achievement_id", "")).strip()
    if achievement:
        return "Achievement: " + achievement.replace("_", " ").title()
    raw_status = (
        definition.get("status")
        or definition.get("acquisition")
        or "Earned/included"
    )
    if isinstance(raw_status, Sequence) and not isinstance(raw_status, (str, bytes)):
        return "/".join(map(str, raw_status))
    return str(raw_status)


def _fmt_fixed(value: Any, digits: int = 3) -> str:
    if not isinstance(value, Mapping):
        return "-"
    scale = int(value.get("scale", 0) or 0)
    if scale <= 0:
        return "-"
    return f"{int(value.get('scaled_integer', 0)) / scale:.{digits}f}"


def build_pdf(report: Mapping[str, Any], output_path: Path) -> Path:
    """Create the deterministic 15-page PDF from one validated frozen report."""

    validate_frozen_report(report)
    try:
        from reportlab import rl_config
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER, TA_LEFT
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import inch
        from reportlab.pdfgen import canvas
        from reportlab.platypus import (
            KeepTogether,
            PageBreak,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
    except ImportError as error:
        raise RuntimeError(
            "ReportLab is required. Use the bundled Codex workspace Python runtime."
        ) from error

    rl_config.invariant = 1
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    page_width, page_height = letter
    palette = {
        "ink": colors.HexColor("#20362E"),
        "muted": colors.HexColor("#61746B"),
        "leaf": colors.HexColor("#4F8063"),
        "mist": colors.HexColor("#EAF1EC"),
        "cream": colors.HexColor("#FAF7EF"),
        "gold": colors.HexColor("#C79A45"),
        "high": colors.HexColor("#A8483D"),
        "watch": colors.HexColor("#B7792B"),
    }

    class InvariantCanvas(canvas.Canvas):
        def __init__(self, *args, **kwargs):
            kwargs.setdefault("invariant", 1)
            kwargs.setdefault("pageCompression", 1)
            super().__init__(*args, **kwargs)
            self._page_number = 0
            self.setTitle("Anki Garden Economy, Progression, and Rewards Analysis")
            self.setAuthor("Anki Garden source analysis")
            self.setSubject(str(report["run"]["run_id"]))

        def showPage(self):
            self._page_number += 1
            self.saveState()
            self.setStrokeColor(palette["mist"])
            self.line(0.65 * inch, 0.52 * inch, page_width - 0.65 * inch, 0.52 * inch)
            self.setFillColor(palette["muted"])
            self.setFont("Helvetica", 7)
            self.drawString(0.65 * inch, 0.30 * inch, "Anki Garden 2.2.0 balance analysis")
            self.drawRightString(
                page_width - 0.65 * inch,
                0.30 * inch,
                f"{self._page_number} / {len(REPORT_SECTIONS)}",
            )
            self.restoreState()
            super().showPage()

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        "PageTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=19,
        leading=22,
        textColor=palette["ink"],
        spaceAfter=5,
    ))
    styles.add(ParagraphStyle(
        "PageSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        textColor=palette["muted"],
        spaceAfter=12,
    ))
    styles.add(ParagraphStyle(
        "Small",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=8,
        leading=11,
        textColor=palette["ink"],
    ))
    styles.add(ParagraphStyle(
        "Tiny",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=6.7,
        leading=8.4,
        textColor=palette["ink"],
    ))
    styles.add(ParagraphStyle(
        "Cover",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=27,
        leading=31,
        alignment=TA_LEFT,
        textColor=palette["ink"],
        spaceAfter=18,
    ))
    styles.add(ParagraphStyle(
        "CoverMeta",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=15,
        textColor=palette["muted"],
    ))

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=letter,
        rightMargin=0.65 * inch,
        leftMargin=0.65 * inch,
        topMargin=0.62 * inch,
        bottomMargin=0.68 * inch,
        title="Anki Garden Economy, Progression, and Rewards Analysis",
        author="Anki Garden source analysis",
    )

    def table(data, widths=None, tiny=False, micro=False):
        value = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
        body_size = 5.2 if micro else (6.3 if tiny else 7.2)
        body_leading = 6.1 if micro else (7.6 if tiny else 9)
        vertical_padding = 1.25 if micro else 3
        value.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), palette["ink"]),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), body_size),
            ("LEADING", (0, 0), (-1, -1), body_leading),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, palette["cream"]]),
            ("GRID", (0, 0), (-1, -1), 0.25, palette["mist"]),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), vertical_padding),
            ("BOTTOMPADDING", (0, 0), (-1, -1), vertical_padding),
        ]))
        return value

    def heading(section: ReportSection):
        return [
            Paragraph(section.title, styles["PageTitle"]),
            Paragraph(section.subtitle, styles["PageSubtitle"]),
        ]

    story = []
    run = report["run"]
    catalog = report["catalog"]
    analysis = report["analysis"]
    findings = list(report.get("findings", ()))

    # Page 1: cover.
    story.extend([
        Spacer(1, 1.05 * inch),
        Paragraph("Anki Garden", styles["CoverMeta"]),
        Paragraph("Economy, Progression,<br/>and Rewards Analysis", styles["Cover"]),
        Paragraph(
            "A source-frozen review of the implemented 2.2.0 balance. It reports "
            "catalog definitions and modeled outcomes; it does not constitute "
            "release approval.",
            styles["CoverMeta"],
        ),
        Spacer(1, 0.48 * inch),
        table([
            ["Release target", "Seeds", "Catalog snapshot", "Run ID"],
            [
                str(run.get("release_target", "")),
                _fmt(run.get("seed_count"), 0),
                str(catalog.get("sha256", ""))[:14],
                str(run.get("run_id", ""))[:14],
            ],
        ], widths=[1.2 * inch, 1.0 * inch, 2.1 * inch, 2.1 * inch]),
    ])

    # Page 2: scorecard.
    story.append(PageBreak())
    story.extend(heading(REPORT_SECTIONS[1]))
    criteria_data = [["Status", "Release criterion", "Evidence", "Target"]]
    for row in balance_scorecard_rows(report):
        criteria_data.append([
            str(row.get("status", "not modeled")).upper(),
            Paragraph(str(row.get("criterion", "")), styles["Tiny"]),
            Paragraph(str(row.get("evidence", "")), styles["Tiny"]),
            Paragraph(str(row.get("target", "")), styles["Tiny"]),
        ])
    story.append(table(
        criteria_data,
        widths=[0.72 * inch, 2.15 * inch, 2.25 * inch, 1.63 * inch],
        micro=True,
    ))
    story.append(Spacer(1, 7))
    scorecard_findings = []
    for severity in ("high", "watch", "unknown"):
        scorecard_findings.extend([
            row for row in findings
            if row.get("severity") == severity
        ][:1])
    finding_data = [["Level", "Domain", "Finding", "Observed"]]
    for row in scorecard_findings:
        finding_data.append([
            str(row.get("severity", "unknown")).upper(),
            str(row.get("domain", "")),
            Paragraph(str(row.get("title", "")), styles["Tiny"]),
            _fmt(row.get("observed")),
        ])
    if len(finding_data) == 1:
        finding_data.append(["INFO", "analysis", "No heuristic threshold triggered.", "-"])
    story.append(table(
        finding_data,
        widths=[0.7 * inch, 0.9 * inch, 4.25 * inch, 0.9 * inch],
        micro=True,
    ))
    story.append(Spacer(1, 7))
    story.append(Paragraph(
        "ATTENTION means the supplied release target is missed in the named model; "
        "NOT MODELED means evidence is unavailable. These balance findings do not "
        "block authoring. Correctness and configuration assertions must pass, and "
        "neither a PASS nor this PDF constitutes release approval.",
        styles["Small"],
    ))

    # Page 3: complete catalog.
    story.append(PageBreak())
    story.extend(heading(REPORT_SECTIONS[2]))
    category_counts = {}
    for record in catalog.get("records", ()):
        category = str(record.get("category", "unknown"))
        category_counts[category] = category_counts.get(category, 0) + 1
    story.append(table(
        [["Category", "Records"]]
        + [[key.replace("_", " ").title(), value] for key, value in sorted(category_counts.items())],
        widths=[4.9 * inch, 1.1 * inch],
    ))
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        "The machine-readable catalog, not copied report prose, is the authority. "
        "The companion catalog CSV retains each complete definition.",
        styles["Small"],
    ))

    # Pages 4 and 5: every catalog record, split by permanent/value scope.
    records = list(catalog.get("records", ()))
    permanent_categories = {
        "species", "garden_bonus", "scenery", "cosmetic", "landmark", "mastery", "bed"
    }
    record_groups = (
        [row for row in records if row.get("category") in permanent_categories],
        [row for row in records if row.get("category") not in permanent_categories],
    )
    for selected, section_index in zip(record_groups, (3, 4)):
        story.append(PageBreak())
        story.extend(heading(REPORT_SECTIONS[section_index]))
        if section_index == 3:
            costs = analysis.get("coins", {}).get("permanent_cost_by_category", {})
            story.append(table([
                ["Pre-endgame cost", "All permanent cost", "Category costs"],
                [
                    _fmt(analysis.get("coins", {}).get("pre_endgame_permanent_cost_total"), 0),
                    _fmt(analysis.get("coins", {}).get("permanent_cost_total"), 0),
                    ", ".join(
                        f"{key}: {_fmt(value, 0)}"
                        for key, value in sorted(costs.items())
                    ),
                ],
            ], widths=[1.35 * inch, 1.35 * inch, 3.6 * inch], micro=True))
            story.append(Spacer(1, 5))
        data = [["Category", "ID", "Price/status"]]
        for record in selected:
            definition = record.get("definition", {})
            if not isinstance(definition, Mapping):
                definition = {}
            category = str(record.get("category", ""))
            status = catalog_record_price_status(category, definition)
            data.append([
                category.replace("_", " ").title(),
                str(record.get("item_id", "")),
                status,
            ])
        story.append(table(
            data,
            widths=[1.25 * inch, 3.15 * inch, 1.9 * inch],
            micro=True,
        ))
        if section_index == 3:
            story.append(Spacer(1, 5))
            story.append(Paragraph(
                "G = Stored Growth; C = Garden Coins. Mastery costs apply to each "
                "species independently, and one starter species is free.",
                styles["Tiny"],
            ))

    metric_pages = (
        (5, "plants.full_bloom", ["Cohort", "P10", "Median", "P90"]),
        (6, "growth.stored_units", ["Cohort", "P10", "Median", "P90"]),
        (7, "coins.gross", ["Cohort", "P10", "Median", "P90"]),
        (8, "catalog.completion_day", ["Cohort", "Reach", "Median", "P90"]),
        (9, "inventory.units", ["Cohort", "P10", "Median", "P90"]),
        (10, "growth.total_units", ["Cohort", "P10", "Median", "P90"]),
        (11, "finds.total", ["Cohort", "P10", "Median", "P90"]),
        (12, "environments.discovered", ["Cohort", "P10", "Median", "P90"]),
        (13, "growth.total_units_per_answer", ["Cohort", "P10", "Median", "P90"]),
    )
    for section_index, metric_id, headers in metric_pages:
        story.append(PageBreak())
        story.extend(heading(REPORT_SECTIONS[section_index]))
        if section_index == 5:
            stage_data = [["Stage", "Growth", "Increment", "Stage Coins", "Cumulative"]]
            for row in analysis.get("growth", {}).get("stage_rows", ()):  # type: ignore[union-attr]
                stage_data.append([
                    str(row.get("stage_id", "")),
                    _fmt(row.get("threshold_growth"), 0),
                    _fmt(row.get("incremental_growth"), 0),
                    _fmt(row.get("stage_coin_reward"), 0),
                    _fmt(row.get("cumulative_coin_reward"), 0),
                ])
            story.append(table(stage_data, widths=[1.35 * inch] * 5, tiny=True))
            story.append(Spacer(1, 7))
        elif section_index == 6:
            growth_analysis = analysis.get("growth", {})
            story.append(table([
                ["Base Growth/card", "Shared per other plant", "Exact units/Growth", "Full Bloom"],
                [
                    _fmt(growth_analysis.get("base_growth_per_review"), 0),
                    f"{growth_analysis.get('shared_growth_numerator', 0)}/{growth_analysis.get('shared_growth_denominator', 1)}",
                    _fmt(growth_analysis.get("units_per_displayed_growth"), 0),
                    _fmt(growth_analysis.get("full_bloom_growth"), 0),
                ],
            ], widths=[1.45 * inch, 1.75 * inch, 1.45 * inch, 1.45 * inch], tiny=True))
            story.append(Spacer(1, 7))
        elif section_index == 7:
            coin_analysis = analysis.get("coins", {})
            story.append(table([
                ["Daily activity", "Valid completion", "Seven-day streak", "Pre-endgame permanent cost"],
                [
                    _fmt(coin_analysis.get("daily_activity"), 0),
                    _fmt(coin_analysis.get("valid_completion"), 0),
                    _fmt(coin_analysis.get("weekly_streak"), 0),
                    _fmt(coin_analysis.get("pre_endgame_permanent_cost_total"), 0),
                ],
            ], widths=[1.4 * inch, 1.5 * inch, 1.45 * inch, 1.95 * inch], tiny=True))
            story.append(Spacer(1, 7))
        elif section_index == 9:
            repeatable_data = [["Item", "Coins", "Growth value"]]
            for row in analysis.get("repeatable_items", ()):
                repeatable_data.append([
                    str(row.get("item_id", "")),
                    _fmt(row.get("price_coins"), 0),
                    _fmt(row.get("growth_value"), 0),
                ])
            story.append(table(
                repeatable_data,
                widths=[4.0 * inch, 1.0 * inch, 1.3 * inch],
                tiny=True,
            ))
            story.append(Spacer(1, 7))
        elif section_index == 10:
            effect_data = [["Bonus / scenery", "Coins", "Growth@100", "Coin payback"]]
            for row in analysis.get("environment_effects", ()):
                numerator = row.get("coin_payback_completion_numerator")
                denominator = row.get("coin_payback_completion_denominator")
                payback = (
                    f"{numerator}/{denominator} completions"
                    if numerator is not None and denominator else "No Coin return"
                )
                growth_numerator = row.get("growth_equivalent_numerator", 0)
                growth_denominator = row.get("growth_equivalent_denominator", 1)
                effect_data.append([
                    str(row.get("item_id", "")),
                    _fmt(row.get("price_coins"), 0),
                    f"{growth_numerator}/{growth_denominator}",
                    payback,
                ])
            story.append(table(
                effect_data,
                widths=[2.2 * inch, 0.75 * inch, 1.05 * inch, 2.3 * inch],
                micro=True,
            ))
            story.append(Spacer(1, 6))
        elif section_index == 11:
            find_analysis = analysis.get("standard_finds", {})
            expected_coins = find_analysis.get("expected_coins", {})
            expected_growth = find_analysis.get("expected_growth_equivalent", {})
            story.append(table([
                ["Mean gap / guarantee", "Daily caps 10/200/400", "Expected Coins/find", "Growth equivalent/find"],
                [
                    (
                        _fmt_fixed(find_analysis.get("schedule_adjusted_expected_gap_cards_fixed_6"))
                        + " / "
                        + _fmt(find_analysis.get("guarantee_answer"), 0)
                    ),
                    "/".join(map(str, find_analysis.get("daily_caps_at_10_200_400_answers", ()))),
                    (
                        _fmt_fixed(find_analysis.get("schedule_adjusted_expected_coins_fixed_6"))
                        + f" (base {expected_coins.get('numerator', 0)}/{expected_coins.get('denominator', 1)})"
                    ),
                    (
                        _fmt_fixed(find_analysis.get("schedule_adjusted_expected_growth_equivalent_fixed_6"))
                        + f" (base {expected_growth.get('numerator', 0)}/{expected_growth.get('denominator', 1)})"
                    ),
                ],
            ], widths=[1.2 * inch, 1.65 * inch, 1.55 * inch, 1.9 * inch], tiny=True))
            story.append(Spacer(1, 7))
        elif section_index == 12:
            tier_data = [["Tier", "Natural chance", "Card guarantee", "Completion guarantee", "Items"]]
            for row in analysis.get("environment_tiers", ()):
                tier_data.append([
                    str(row.get("tier_id", "")),
                    f"1/{_fmt(row.get('base_denominator'), 0)}",
                    _fmt(row.get("card_guarantee"), 0),
                    _fmt(row.get("completion_guarantee"), 0),
                    _fmt(row.get("item_count"), 0),
                ])
            story.append(table(
                tier_data,
                widths=[1.55 * inch, 1.15 * inch, 1.2 * inch, 1.45 * inch, 0.65 * inch],
                tiny=True,
            ))
            story.append(Spacer(1, 7))
        elif section_index == 13:
            speed_rows = analysis.get("optional_speed_sensitivity", {}).get("rows", ())
            speed_data = [["Consumable", "Growth", "Coins", "Growth/Coin", "30/100/300 cph"]]
            for row in speed_rows:
                speed_data.append([
                    str(row.get("item_id", "")),
                    _fmt(row.get("maximum_growth"), 0),
                    _fmt(row.get("price_coins"), 0),
                    f"{row.get('growth_per_coin_numerator', 0)}/{row.get('growth_per_coin_denominator', 1)}",
                    "Invariant" if row.get("growth_per_coin_is_speed_invariant") else "Varies",
                ])
            story.append(table(
                speed_data,
                widths=[2.2 * inch, 0.8 * inch, 0.7 * inch, 1.15 * inch, 1.45 * inch],
                tiny=True,
            ))
            story.append(Spacer(1, 7))
        data = [headers]
        for row in representative_statistic_rows(report, metric_id):
            first = _fmt(row.get("reach_rate"), 2) if metric_id == "catalog.completion_day" else _fmt(row.get("p10"))
            cohort_id = str(row.get("scenario_id", "")).partition(":")[0]
            data.append([
                cohort_id.replace("_", " ").title(),
                first,
                _fmt(row.get("p50")),
                _fmt(row.get("p90")),
            ])
        if len(data) == 1:
            data.append(["No modeled row", "-", "-", "-"])
        story.append(table(data, widths=[3.7 * inch, 0.85 * inch, 0.85 * inch, 0.85 * inch], tiny=True))
        story.append(Spacer(1, 9))
        units_note = (
            " Growth quantities use exact hundredth units; 100 units equal "
            "1 displayed Growth."
            if metric_id in {
                "growth.stored_units",
                "growth.total_units",
                "growth.total_units_per_answer",
            }
            else ""
        )
        story.append(Paragraph(
            f"Metric: {metric_id}. Rows use the collection-first baseline for all "
            "six cohorts in scenario-matrix order. Values are paired across the "
            f"fixed seed manifest;{units_note} quantiles use the nearest-rank method.",
            styles["Small"],
        ))

    # Page 15: methodology and source manifest.
    story.append(PageBreak())
    story.extend(heading(REPORT_SECTIONS[14]))
    story.append(table([
        ["Method field", "Frozen value"],
        ["Model", str(run.get("model", ""))],
        ["RNG", str(run.get("rng", ""))],
        ["Seed count", _fmt(run.get("seed_count"), 0)],
        ["Quantiles", str(run.get("quantiles", ""))],
        ["Catalog SHA-256", str(run.get("catalog_sha256", ""))],
        ["Run ID", str(run.get("run_id", ""))],
        ["Git commit", str(run.get("git_commit", ""))],
    ], widths=[1.45 * inch, 5.1 * inch], tiny=True))
    story.append(Spacer(1, 10))
    assertion_data = [["Assertion", "Status", "Observed", "Expected"]]
    for row in report.get("assertions", ()):
        assertion_data.append([
            str(row.get("assertion_id", "")),
            str(row.get("status", "")).upper(),
            _fmt(row.get("observed"), 0),
            _fmt(row.get("expected"), 0),
        ])
    story.append(table(assertion_data, widths=[3.8 * inch, 0.8 * inch, 0.8 * inch, 0.8 * inch], tiny=True))
    story.append(Spacer(1, 9))
    story.append(Paragraph(
        "Limitations: cohort schedules, completion patterns, purchase strategies, and "
        "session timing are modeled assumptions. The accelerated random kernel is "
        "catalog-oracle compatible; production engine trace comparison remains a "
        "separate release test. Balance-target misses are non-blocking findings, not "
        "simulator failures. This analysis does not constitute release approval.",
        styles["Small"],
    ))

    doc.build(story, canvasmaker=InvariantCanvas)
    return output_path
