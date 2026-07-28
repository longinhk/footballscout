"""PDF report generation."""

from __future__ import annotations

import math
import unicodedata
from collections.abc import Mapping, Sequence
from typing import Any

from fpdf import FPDF


_TRANSLITERATION = str.maketrans(
    {
        "Đ": "D",
        "đ": "d",
        "Ł": "L",
        "ł": "l",
        "Ø": "O",
        "ø": "o",
        "Þ": "Th",
        "þ": "th",
        "ı": "i",
    }
)


def _pdf_text(value: Any) -> str:
    """Return text that core PDF fonts can render without crashing."""
    normalized = unicodedata.normalize("NFKD", str(value).translate(_TRANSLITERATION))
    without_marks = "".join(
        character for character in normalized if not unicodedata.combining(character)
    )
    return without_marks.encode("latin-1", errors="replace").decode("latin-1")


def _included_items(
    player: Mapping[str, Any], plural_key: str, fallback_key: str
) -> str:
    values = player.get(plural_key)
    if isinstance(values, list) and values:
        return ", ".join(str(value) for value in values)
    return str(player.get(fallback_key) or "Unknown")


class _ComparisonPDF(FPDF):
    def footer(self) -> None:
        self.set_y(-12)
        self.set_font("Arial", "", 8)
        self.set_text_color(100, 110, 106)
        self.cell(0, 7, f"Footy-Scout | Page {self.page_no()}", align="C")


def _finite_value(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Valuation values must be numeric.") from exc
    if not math.isfinite(number):
        raise ValueError("Valuation values must be finite.")
    return number


def _blended(values: Mapping[str, Any]) -> float:
    if not values:
        raise ValueError("Each player needs at least one valuation method.")
    finite_values = [_finite_value(value) for value in values.values()]
    return sum(finite_values) / len(finite_values)


def _display_stat(value: Any, decimals: int = 0) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "-"
    if not math.isfinite(number):
        return "-"
    return f"{number:.{decimals}f}"


def _performance_line(player: Mapping[str, Any]) -> str:
    position = str(player.get("position") or "").lower()
    rating = _display_stat(player.get("rating"), 2)
    if "goalkeeper" in position:
        return (
            f"Rating {rating} | {player.get('saves') or 0} saves | "
            f"{player.get('conceded') or 0} conceded | "
            f"{_display_stat(player.get('clean_sheets'))} clean sheets"
        )
    if "defender" in position:
        return (
            f"Rating {rating} | {player.get('tackles') or 0} tackles | "
            f"{player.get('interceptions') or 0} interceptions | "
            f"{player.get('goals') or 0} goals"
        )
    return (
        f"Rating {rating} | {player.get('goals') or 0} goals | "
        f"{player.get('assists') or 0} assists | {player.get('tackles') or 0} tackles"
    )


def generate_valuation_pdf(
    players: Sequence[Mapping[str, Any]],
    valuations: Sequence[Mapping[str, Any]],
) -> bytes:
    """Build a compact, validated comparison report entirely in memory."""
    if not players:
        raise ValueError("At least one player is required for a report.")
    if len(players) != len(valuations):
        raise ValueError("Players and valuations must have matching lengths.")

    blended_values = [_blended(values) for values in valuations]
    pdf = _ComparisonPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_title("Footy-Scout comparison")
    pdf.set_author("Footy-Scout")
    pdf.add_page()

    pdf.set_fill_color(18, 66, 48)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Arial", "B", 20)
    pdf.cell(0, 13, "Footy-Scout Comparison", ln=True, align="C", fill=True)
    pdf.set_text_color(65, 78, 73)
    pdf.set_font("Arial", "", 9)
    pdf.cell(
        0,
        7,
        "Educational estimates - not official market valuations",
        ln=True,
        align="C",
    )
    pdf.ln(3)

    if len(players) == 2:
        margin = abs(blended_values[0] - blended_values[1])
        if margin < 0.005:
            summary = "The blended estimates are level."
        else:
            leader = players[0] if blended_values[0] > blended_values[1] else players[1]
            summary = (
                f"{leader.get('name', 'Player')} leads the blended estimate "
                f"by EUR {margin:.2f}M."
            )
        pdf.set_font("Arial", "B", 11)
        pdf.set_text_color(18, 66, 48)
        pdf.multi_cell(0, 7, _pdf_text(summary), border=1, align="C")
        pdf.ln(5)

    for player, values, blended in zip(players, valuations, blended_values):
        if pdf.get_y() > 225:
            pdf.add_page()

        pdf.set_text_color(20, 31, 27)
        pdf.set_font("Arial", "B", 14)
        pdf.multi_cell(0, 8, _pdf_text(player.get("name") or "Unknown player"))
        pdf.set_font("Arial", "", 10)
        teams = _included_items(player, "teams", "team")
        competitions = _included_items(player, "competitions", "league")
        position = player.get("position") or "Unknown position"
        season = player.get("season") or "Unknown season"
        details = (
            f"{teams} | {position} | Age {player.get('age') or '-'} | "
            f"{player.get('games') or 0} appearances | {player.get('minutes') or 0} minutes"
        )
        pdf.multi_cell(0, 6, _pdf_text(details))
        pdf.multi_cell(0, 6, _pdf_text(_performance_line(player)))
        pdf.set_text_color(65, 78, 73)
        pdf.multi_cell(0, 6, _pdf_text(f"{competitions} | Season {season}"))

        pdf.set_text_color(20, 31, 27)
        for label, value in values.items():
            pdf.cell(
                0, 6, _pdf_text(f"{label}: EUR {_finite_value(value):.2f}M"), ln=True
            )
        pdf.set_font("Arial", "B", 10)
        pdf.cell(0, 7, f"Blended (equal weight): EUR {blended:.2f}M", ln=True)
        pdf.ln(5)

    output = pdf.output(dest="S")
    return output.encode("latin-1") if isinstance(output, str) else bytes(output)
