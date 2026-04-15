from fpdf import FPDF

def generate_valuation_pdf(player1, player2, val1, val2):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    
    pdf.cell(200, 10, txt="Footy-Scout Player Valuation Report", ln=True, align='C')
    pdf.ln(10)
    
    pdf.set_font("Arial", size=12)
    
    pdf.cell(200, 10, txt=f"Player 1: {player1.get('name', 'N/A')}", ln=True)
    pdf.cell(200, 10, txt=f"Estimated Value: {val1}", ln=True)
    pdf.ln(5)
    pdf.cell(200, 10, txt=f"Player 2: {player2.get('name', 'N/A')}", ln=True)
    pdf.cell(200, 10, txt=f"Estimated Value: {val2}", ln=True)
    
    return pdf.output(dest='S').encode('latin-1')
