Footy-Scout is a data‑driven web application that estimates football players' transfer value based on performance metrics. It allows users to compare two players side‑by‑side, view detailed statistics, and download a PDF valuation report. The project demonstrates how to integrate a public API, implement custom business logic, and build an interactive UI with minimal frontend code – all using Python and Streamlit.

✨Features

Player Comparison – Enter two player IDs and instantly compare their key stats (age, games, goals, assists).
Live Data – Fetches real‑time statistics from API-Football (via RapidAPI).
Interactive UI – Clean, responsive interface built with Streamlit.
PDF Report – Generate and download a professional one‑page summary of the comparison.
Free to Use – No API costs (using free tier) and no backend servers needed.

## ✨ Features

- **Player Comparison** – Enter two player IDs and instantly compare key stats: age, appearances, goals, assists, and more.
- **Live Data** – Fetches real-time statistics from [API-Football](https://www.api-football.com) via RapidAPI.
- **Interactive UI** – Clean, responsive interface built with Streamlit for seamless user experience.
- **PDF Report** – Generate and download a one‑page professional summary of the comparison.
- **Free to Use** – No API costs (free tier) and no backend servers needed.

---

## 🛠️ Tech Stack

- **Language**: Python 3.9+
- **Web Framework**: Streamlit
- **Data Processing**: Pandas, NumPy
- **API Integration**: Requests, API-Football (RapidAPI)
- **PDF Generation**: FPDF / ReportLab
- **Version Control**: Git, GitHub

🚀 Usage

1. Open the app in your browser (usually http://localhost:8501).
2. Enter two valid player IDs (you can find them on sites like Transfermarkt or use the API's search).
3. Click Compare to view side-by-side statistics and the estimated transfer value.
4. Download the PDF report for your records.

Note: The free API tier has request limits. If data doesn't load, wait a minute and try again.

---

🔮 Future Improvements

· Add data visualization (e.g., performance trend charts).
· Integrate a simple machine learning model to improve valuation accuracy.
· Containerize with Docker for easier deployment.
· Implement player search by name (instead of ID).
· Cache API responses to reduce calls and improve speed.

---

🤝 Contributing

Contributions, issues, and feature requests are welcome! Feel free to check the issues page.

---
