# 🏛️ CivicPriority — AI-Powered Citizen Complaint Prioritization Engine

> A civic-tech platform that analyzes and prioritizes citizen complaints against real-world infrastructure constraints using Gemini AI and a constraint-satisfaction algorithm.

🌐 **Live Demo**: [https://people-s-prob.onrender.com](https://people-s-prob.onrender.com)

---

## 📌 Overview

CivicPriority is a lightweight, AI-powered backend and dashboard that:
- **Accepts** raw, unstructured citizen complaints (in any language/format)
- **Categorizes** them into `Healthcare`, `Water Supply`, `Roads & Infrastructure`, `Education`, or `Other`
- **Evaluates** each complaint against real ward-level infrastructure constraints (budget, hospital proximity, population density)
- **Prioritizes** them using a constraint-satisfaction scoring algorithm
- **Clusters** recurring complaints into aggregated meta-themes
- **Serves** all data through a REST API and a live dashboard UI

---

## 🧠 How It Works

```
Citizen Complaint (raw text)
        │
        ▼
┌───────────────────┐
│  Gemini 3.5 Flash │  ← Structured extraction (category, urgency, location)
│  (or fallback)    │
└───────────────────┘
        │
        ▼
┌───────────────────────────┐
│  Constraint Satisfaction  │  ← Evaluates against ward budget, hospital
│  Prioritization Engine    │     distance, and population density
└───────────────────────────┘
        │
        ▼
┌───────────────────┐
│  Supabase         │  ← Persisted to PostgreSQL cloud database
│  PostgreSQL       │
└───────────────────┘
        │
        ▼
┌───────────────────┐
│  FastAPI REST API │  ← Served via live Render deployment
│  + Dashboard UI   │
└───────────────────┘
```

---

## ⚙️ Tech Stack

| Layer | Technology |
|---|---|
| **AI / NLP** | Google Gemini 3.5 Flash (`google-genai`) |
| **Backend** | FastAPI + Uvicorn |
| **Database** | Supabase (PostgreSQL via `psycopg2`) |
| **Deployment** | Render (Docker) |
| **Frontend** | Vanilla HTML + Tailwind CSS |

---

## 🗂️ Project Structure

```
.
├── app.py              # Core AI & prioritization logic
├── server.py           # FastAPI server & REST endpoints
├── seed_data.py        # Direct DB seeding script (no server needed)
├── requirements.txt    # Python dependencies
├── Dockerfile          # Docker container config for Render
├── Procfile            # Process config for PaaS deployments
├── .dockerignore       # Files excluded from Docker build
├── .gitignore          # Files excluded from git
└── static/
    └── index.html      # Dashboard frontend UI
```

---

## 🚀 API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Dashboard UI |
| `GET` | `/complaints` | All complaints sorted by priority score |
| `GET` | `/themes` | Aggregated recurring complaint themes |
| `POST` | `/submit-complaint` | Submit a new citizen complaint |

### Submit a Complaint (Example)
```bash
curl -X POST https://people-s-prob.onrender.com/submit-complaint \
  -H "Content-Type: application/json" \
  -d '{"complaint_text": "The water pump in Sector 4 has been broken for 3 days."}'
```

---

## 🏗️ Prioritization Algorithm

Each complaint is scored (0–100) using a **multi-factor constraint satisfaction** system:

| Factor | Points |
|---|---|
| Urgency: High | +50 |
| Urgency: Medium | +30 |
| Urgency: Low | +10 |
| Category: Healthcare / Water Supply | +15 |
| Category: Roads & Infrastructure | +10 |
| Category: Education | +5 |
| Hospital Distance > 5km (Health/Water) | +20 |
| Population Density > 5,000/km² | +15 |
| Population Density > 1,000/km² | +5 |

**Hard Constraint**: If estimated repair cost exceeds ward budget, the complaint is **rejected** — *unless* it is a High urgency Healthcare or Water Supply issue (emergency override).

**Recommended Actions**:
- Score ≥ 75 → **Fast-Track**
- Score ≥ 40 → **Review Required**
- Score < 40 → **Routine Backlog**
- Over budget → **Rejected**

---

## 🛠️ Local Setup

### Prerequisites
- Python 3.11+
- A [Supabase](https://supabase.com) account (free)
- A [Gemini API Key](https://aistudio.google.com/apikey) (free)

### 1. Clone the repository
```bash
git clone https://github.com/ShyamTheThor/people-s-prob.git
cd people-s-prob
```

### 2. Create a virtual environment
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Set environment variables
```bash
export DATABASE_URL="postgresql://postgres.xxxx:password@aws-0-region.pooler.supabase.com:5432/postgres"
export GEMINI_API_KEY="your_gemini_api_key"
```

### 4. Seed the database
```bash
python seed_data.py
```

### 5. Start the server
```bash
uvicorn server:app --reload
```

Open **http://127.0.0.1:8000** in your browser.

---

## ☁️ Deployment (Render + Supabase)

1. **Supabase**: Create a project → get the **Session Pooler** connection string (IPv4 compatible)
2. **Render**: Connect your GitHub repo → select **Web Service** → auto-detects `Dockerfile`
3. **Environment Variables** on Render:

| Key | Value |
|---|---|
| `DATABASE_URL` | Your Supabase session pooler URI |
| `GEMINI_API_KEY` | Your Gemini API key |

4. Deploy — your live URL will be available in ~3 minutes.

---

## 🌍 Ward Constraints (Mock Data)

| Ward | Budget | Hospital Distance | Population Density |
|---|---|---|---|
| Ward A (Downtown) | $50,000 | 1.2 km | 8,500/km² |
| Ward B (Suburbs) | $12,000 | 8.5 km | 1,200/km² |
| Ward C (Rural Fringe) | $3,000 | 18.0 km | 350/km² |

---

## 📄 License

MIT License — feel free to use, modify, and distribute.

---

> Built for **Code for Communities — Track 1** 🏆
