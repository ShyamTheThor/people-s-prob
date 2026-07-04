import os
import psycopg2
from server import get_fallback_extraction
from app import analyze_complaint, rank_priority_works, MOCK_WARD_CONSTRAINTS

# Highly realistic dataset of citizen complaints representing diverse categories, wards, duplicates, and emergencies
COMPLAINTS = [
    # Cluster 1: Sector 4 Water Pump (Resolved to Ward B - Suburbs, budget $12k)
    "The main water pump in Sector 4 is broken and leaking mud. We have no clean drinking water.",
    "There is water leaking everywhere near the Sector 4 community center pump, it is cracked.",
    "Water supply is disrupted in Sector 4 suburbs because the local water pump is completely broken.",
    "Paani ki tanki in Sector 4 has cracked, and mud water is coming in supply taps.",
    
    # Cluster 2: Sector 9 Healthcare Emergency (Resolved to Ward C - Rural Fringe, budget $3k, distance 18km)
    # Highlights Emergency Override and massive Proximity Boost overriding low budget
    "Severe lack of medical supplies at Sector 9 health post. We need bandages and first-aid stock immediately.",
    "Urgent: The health clinic in Sector 9 is out of life-saving medicine and essential medical supplies.",
    
    # Cluster 3: Downtown Roads (Resolved to Ward A - Downtown, budget $50k)
    "Main road in Downtown has massive potholes causing high danger at night.",
    "Dangerous potholes along Downtown Main Street are causing flat tires and accidents.",
    "Sadak near Sector 3 is completely broken. Government must fix this road immediately.",
    
    # Education issues in Sector 5 (Resolved to Ward A - Downtown)
    "Primary School building roof in Sector 5 is leaking during heavy rains.",
    "No textbooks and notebooks have arrived for students at Sector 5 government school.",
    "Sector 5 government school needs new teacher, classes are empty.",
    
    # Healthcare issues in Sector 2 (Resolved to Ward B - Suburbs)
    "Government hospital in Sector 2 suburbs has broken power generator, causing severe risk for patients.",
    
    # Low urgency roads / infrastructure in Suburbs (Resolved to Ward B - Suburbs)
    "Streetlights are completely off in Sector 3 suburbs, making it dangerous for women to walk at night.",
    
    # Water issues in Sector 1 (Resolved to Ward A - Downtown)
    "Drainage system in Sector 1 is choked, causing sewage water to overflow on roads.",
    "Paani supply has bad smell in Sector 1 for two weeks, citizens falling sick.",
    
    # Ward C Roads / Infrastructure (Disqualified due to remaining budget constraints: Roads cost is $20k, budget is $3k)
    "Bridge crossing the local stream in Sector 9 rural fringe is broken, school kids cannot cross.",
    "Street pothole near sector 9 rural houses is deep, needs gravel."
]

def seed():
    """
    Directly processes the realistic complaints and inserts them into Supabase (PostgreSQL),
    bypassing the need for a running FastAPI server.
    """
    DATABASE_URL = os.environ.get("DATABASE_URL")
    if not DATABASE_URL:
        print("ERROR: DATABASE_URL environment variable is not set.")
        print("Set it to your Supabase connection string and try again.")
        return

    print("=" * 75)
    print(f"Starting direct database seeding for {len(COMPLAINTS)} citizen complaints...")
    print("Target: Supabase PostgreSQL")
    print("=" * 75)
    
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    
    # Ensure table exists
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
    
    api_key = os.environ.get("GEMINI_API_KEY")
    success_count = 0
    
    for idx, text in enumerate(COMPLAINTS, 1):
        try:
            if api_key:
                try:
                    extracted = analyze_complaint(text)
                except Exception as e:
                    extracted = get_fallback_extraction(text)
            else:
                extracted = get_fallback_extraction(text)
                
            ranked = rank_priority_works(extracted, MOCK_WARD_CONSTRAINTS)
            
            category = extracted.get("category", "Other")
            urgency = extracted.get("urgency", "Low")
            detected_location = extracted.get("detected_location", "Unspecified")
            actionable_summary = extracted.get("actionable_summary", "Unspecified")
            priority_score = ranked.get("priority_score", 0.0)
            recommended_action = ranked.get("recommended_action", "Review Required")
            ward_evaluated = ranked.get("ward_evaluated", "Ward A (Downtown)")
            reasoning = ranked.get("reasoning", "")
            
            cursor.execute('''
                INSERT INTO complaints (
                    raw_text, category, urgency, detected_location, actionable_summary,
                    priority_score, recommended_action, ward_evaluated, reasoning
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (
                text, category, urgency, detected_location, actionable_summary,
                priority_score, recommended_action, ward_evaluated, reasoning
            ))
            
            print(f"[{idx:02d}/{len(COMPLAINTS)}] SUCCESS: {category:<15} | Ward: {ward_evaluated:<22} | Score: {priority_score:<4} | Action: {recommended_action}")
            success_count += 1
        except Exception as e:
            print(f"[{idx:02d}/{len(COMPLAINTS)}] FAILED: {e}")
            
    conn.commit()
    cursor.close()
    conn.close()
            
    print("=" * 75)
    print(f"Seeding complete. Successfully inserted {success_count} out of {len(COMPLAINTS)} complaints into Supabase.")
    print("=" * 75)

if __name__ == "__main__":
    seed()
