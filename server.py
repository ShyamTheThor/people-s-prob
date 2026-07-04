import os
import json
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List
import psycopg2
import psycopg2.extras
from app import analyze_complaint, rank_priority_works, MOCK_WARD_CONSTRAINTS, cluster_recurring_themes

app = FastAPI(
    title="Civic-Tech Complaint Prioritization API",
    description="Lightweight backend API evaluating citizen complaints against ward-level infrastructure constraints."
)

DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db_connection():
    conn = psycopg2.connect(DATABASE_URL)
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS complaints (
            id SERIAL PRIMARY KEY,
            raw_text TEXT,
            category TEXT,
            urgency TEXT,
            detected_location TEXT,
            actionable_summary TEXT,
            priority_score REAL,
            recommended_action TEXT,
            ward_evaluated TEXT,
            reasoning TEXT
        )
    ''')
    conn.commit()
    cursor.close()
    conn.close()

init_db()

class ComplaintInput(BaseModel):
    complaint_text: str

@app.post("/submit-complaint")
def submit_complaint(data: ComplaintInput):
    """
    Submits a raw complaint string. Runs it through the categorization pipeline
    (using Gemini or a robust keyword fallback if no API key is set), evaluates it
    against infrastructure constraints, and saves it to the database.
    """
    raw_text = data.complaint_text.strip()
    if not raw_text:
        raise HTTPException(status_code=400, detail="Complaint text cannot be empty.")
        
    api_key = os.environ.get("GEMINI_API_KEY")
    
    # 1. Extraction phase
    if api_key:
        try:
            extracted = analyze_complaint(raw_text)
        except Exception as e:
            print(f"Gemini API error: {e}. Defaulting to keyword fallback.")
            extracted = get_fallback_extraction(raw_text)
    else:
        extracted = get_fallback_extraction(raw_text)
        
    # 2. Ranking / Prioritization phase
    try:
        ranked = rank_priority_works(extracted, MOCK_WARD_CONSTRAINTS)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ranking engine failure: {e}")
        
    # 3. Insert into Supabase / PostgreSQL
    category = extracted.get("category", "Other")
    urgency = extracted.get("urgency", "Low")
    detected_location = extracted.get("detected_location", "Unspecified")
    actionable_summary = extracted.get("actionable_summary", "Unspecified")
    priority_score = ranked.get("priority_score", 0.0)
    recommended_action = ranked.get("recommended_action", "Review Required")
    ward_evaluated = ranked.get("ward_evaluated", "Ward A (Downtown)")
    reasoning = ranked.get("reasoning", "")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO complaints (
            raw_text, category, urgency, detected_location, actionable_summary,
            priority_score, recommended_action, ward_evaluated, reasoning
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    ''', (
        raw_text, category, urgency, detected_location, actionable_summary,
        priority_score, recommended_action, ward_evaluated, reasoning
    ))
    inserted_id = cursor.fetchone()[0]
    conn.commit()
    cursor.close()
    conn.close()
    
    return {
        "id": inserted_id,
        "raw_text": raw_text,
        "category": category,
        "urgency": urgency,
        "detected_location": detected_location,
        "actionable_summary": actionable_summary,
        "priority_score": priority_score,
        "recommended_action": recommended_action,
        "ward_evaluated": ward_evaluated,
        "reasoning": reasoning
    }

@app.get("/complaints")
def get_complaints():
    """
    Returns the complete list of processed complaints, sorted by priority_score from highest to lowest.
    """
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cursor.execute('SELECT * FROM complaints ORDER BY priority_score DESC')
    complaints = cursor.fetchall()
    cursor.close()
    conn.close()
    return [dict(row) for row in complaints]

@app.get("/themes")
def get_themes():
    """
    Returns aggregated recurring complaint themes based on category, location and keyword similarity,
    sorted by their aggregate priority score.
    """
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cursor.execute('SELECT * FROM complaints')
    complaints = cursor.fetchall()
    cursor.close()
    conn.close()
    return cluster_recurring_themes([dict(row) for row in complaints])

def get_fallback_extraction(text: str) -> dict:
    """
    A smart keyword-based heuristic fallback to generate realistic mock extractions
    when the Gemini API is unavailable.
    """
    text_lower = text.lower()
    
    # Category detection
    if any(k in text_lower for k in ["water", "pump", "leak", "pipe", "sewage", "drain"]):
        category = "Water Supply"
        detected_location = "Sector 4" if "sector 4" in text_lower else "Sector 9" if "sector 9" in text_lower else "Sector 1"
        actionable_summary = "Water supply issue reported."
    elif any(k in text_lower for k in ["hospital", "clinic", "health", "medical", "nurse", "doctor", "medicine", "supplies"]):
        category = "Healthcare"
        detected_location = "Sector 9" if "sector 9" in text_lower else "Sector 4" if "sector 4" in text_lower else "Sector 2"
        actionable_summary = "Healthcare facilities or supply deficiency."
    elif any(k in text_lower for k in ["road", "highway", "bridge", "pothole", "street", "traffic", "pavement"]):
        category = "Roads & Infrastructure"
        detected_location = "Main Street" if "main" in text_lower else "Sector 3"
        actionable_summary = "Roads or infrastructure repair required."
    elif any(k in text_lower for k in ["school", "education", "teacher", "class", "book", "student", "classroom"]):
        category = "Education"
        detected_location = "Sector 5"
        actionable_summary = "Educational facility improvement requested."
    else:
        category = "Other"
        detected_location = "Unspecified"
        actionable_summary = "General citizen complaint received."

    # Urgency detection
    if any(k in text_lower for k in ["urgent", "emergency", "broken", "burst", "leak", "danger", "severe", "outage", "flooding", "risk"]):
        urgency = "High"
    elif any(k in text_lower for k in ["need", "fix", "repair", "please", "problem", "broken"]):
        urgency = "Medium"
    else:
        urgency = "Low"
        
    return {
        "category": category,
        "urgency": urgency,
        "detected_location": detected_location,
        "actionable_summary": actionable_summary
    }

# Ensure static files directory exists
os.makedirs("static", exist_ok=True)

# Mount the static directory
app.mount("/static", StaticFiles(directory="static"), name="static")

# Serve index.html at root route
@app.get("/", response_class=FileResponse)
def read_root():
    index_path = os.path.join("static", "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    raise HTTPException(status_code=404, detail="static/index.html not found.")
