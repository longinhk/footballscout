"""Generate a portable comparison PDF in memory."""

from __future__ import annotations

from fpdf import FPDF

from valuation import ValuationResult


def generate_valuation_pdf(
    players: list[dict], values: list[ValuationResult], explanation: str
) -> bytes:
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Arial", "B", 20)
    pdf.cell(0, 12, "FootballScout Comparison", ln=True, align="C")
    pdf.set_font("Arial", "", 9)
    pdf.cell(0, 7, "Portfolio demonstration - not an official market valuation", ln=True, align="C")
    pdf.ln(6)
    for player, result in zip(players, values):
        pdf.set_font("Arial", "B", 14)
        pdf.cell(0, 9, player["name"], ln=True)
        pdf.set_font("Arial", "", 10)
        summary = (
            f"{player['team']} | {player['position']} | Age {player['age']} | "
            f"{player['appearances']} appearances | {player['goals']} goals | "
            f"{player['assists']} assists | Rating {player['rating']}"
        )
        pdf.multi_cell(0, 6, summary)
        pdf.cell(0, 7, f"Regression estimate: EUR {result.value_millions:.2f}M", ln=True)
        pdf.ln(4)
    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 8, "Model explanation", ln=True)
    pdf.set_font("Arial", "", 10)
    pdf.multi_cell(0, 6, explanation.encode("latin-1", "replace").decode("latin-1"))
    output = pdf.output(dest="S")
    return output.encode("latin-1") if isinstance(output, str) else bytes(output)
