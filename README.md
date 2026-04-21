# InsightAir--Air-Quality-Trend-Analysis-System
# 🌍 InsightAir — Air Quality Trends Analysis System

> A full-stack platform for monitoring, analyzing, and forecasting air quality using real-world data and intelligent insights.

---

## 🚀 Overview

**InsightAir** is an end-to-end air quality analytics system that aggregates pollution data (PM2.5, PM10), performs advanced analytics, and delivers actionable insights through visual dashboards and reports.

It combines **data engineering + analytics + AI + full-stack development** into one practical, real-world application.

---

## ✨ Features

- 📊 **Multi-source Data Aggregation**
  - Collects and normalizes PM2.5 & PM10 data from multiple sources

- 🌆 **City-wise Comparative Analytics**
  - Compare pollution levels across cities with interactive charts

- 📈 **Time-Series Forecasting**
  - Predict future air quality trends with confidence intervals

- 📄 **Automated PDF Reports**
  - Generate detailed downloadable reports using ReportLab

- 🔐 **JWT Authentication**
  - Secure login system with tiered access

---

## 🏗️ Tech Stack

### Frontend
- React (Vite)
- Tailwind CSS
- Recharts

### Backend
- FastAPI
- SQLAlchemy
- Uvicorn

### Database
- SQLite (Development)
- MySQL (Optional Production)

### Other Tools
- ReportLab (PDF generation)

---

## 📂 Project Structure

InsightAir/
│
├── backend/ # FastAPI backend
│ ├── app/
│ ├── models/
│ └── routes/
│
├── frontend/ # React frontend
│ ├── src/
│ └── components/
│
└── README.md


---

## ⚙️ Getting Started

### 1️⃣ Clone the Repository

git clone https://github.com/your-username/InsightAir.git
cd InsightAir

---

### 2️⃣ Run Backend(FastAPI)

cd backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

---

### 3️⃣ Run Frontend (React + Vite)

cd frontend
npm install
npm run dev -- --host 0.0.0.0 --port 5173

---

### 🔐 Environment Variables

Create a .env file in backend:

ALLOWED_ORIGINS=http://localhost:5173
SECRET_KEY=your_secret_key

If port changes:

ALLOWED_ORIGINS=http://localhost:5174

---

⭐ If you like this project...

Give it a ⭐ on GitHub and share it!
