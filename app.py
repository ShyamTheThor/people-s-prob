import os
import json
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from typing import Literal, Dict, TypedDict

# =====================================================================
# Structured Output & Type Definitions
# =====================================================================

class ComplaintAnalysis(BaseModel):
    category: Literal["Education", "Healthcare", "Roads & Infrastructure", "Water Supply", "Other"]
    urgency: Literal["High", "Medium", "Low"]
    detected_location: str = Field(description="Extract the location or return 'Unspecified'")
    actionable_summary: str = Field(description="A 1-sentence English summary")

class WardConstraint(TypedDict):
    remaining_budget: float
    distance_to_nearest_hospital_km: float
    population_density: float

class RankResult(TypedDict):
    priority_score: float
    recommended_action: Literal["Fast-Track", "Review Required", "Routine Backlog", "Rejected due to constraints (Insufficient Budget)"]
    ward_evaluated: str
    reasoning: str

# =====================================================================
# Mock Data
# =====================================================================

# Mock public dataset representing infrastructure constraints for three fictional wards
MOCK_WARD_CONSTRAINTS: Dict[str, WardConstraint] = {
    "Ward A (Downtown)": {
        "remaining_budget": 50000.0,
        "distance_to_nearest_hospital_km": 1.2,
        "population_density": 8500.0
    },
    "Ward B (Suburbs)": {
        "remaining_budget": 12000.0,
        "distance_to_nearest_hospital_km": 8.5,
        "population_density": 1200.0
    },
    "Ward C (Rural Fringe)": {
        "remaining_budget": 3000.0,
        "distance_to_nearest_hospital_km": 18.0,
        "population_density": 350.0
    }
}

# Estimated cost of resolving issues in each category (used for hard budget constraint check)
ESTIMATED_REPAIR_COSTS: Dict[str, float] = {
    "Education": 10000.0,
    "Healthcare": 15000.0,
    "Roads & Infrastructure": 20000.0,
    "Water Supply": 5000.0,
    "Other": 2000.0
}

# =====================================================================
# Core Functions
# =====================================================================

def resolve_ward(detected_location: str) -> str:
    """
    Maps a detected location string to one of our three mock fictional wards.
    
    Args:
        detected_location (str): The location name extracted from the complaint.
        
    Returns:
        str: Resolved ward name.
    """
    loc_lower = detected_location.lower()
    if "sector 4" in loc_lower or "suburb" in loc_lower or "ward b" in loc_lower:
        return "Ward B (Suburbs)"
    elif "sector 9" in loc_lower or "rural" in loc_lower or "ward c" in loc_lower:
        return "Ward C (Rural Fringe)"
    else:
        return "Ward A (Downtown)"

def analyze_complaint(complaint_text: str) -> dict:
    """
    Parses a raw, unstructured citizen complaint string and returns a structured dictionary.
    
    Args:
        complaint_text (str): The citizen complaint text.
        
    Returns:
        dict: A dictionary containing 'category', 'urgency', 'detected_location', 
              and 'actionable_summary'.
    """
    # Handle initialization using an environment variable for the API key
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable is not set. Please set the GEMINI_API_KEY environment variable.")

    # Initialize the Google GenAI Client
    client = genai.Client(api_key=api_key)

    # Construct the prompt with strict formatting instructions
    prompt = (
        "Analyze the following citizen complaint and extract the structured information. "
        "You MUST output a strict JSON object (with no markdown wrapping) containing the following fields:\n"
        '- "category": One of "Education", "Healthcare", "Roads & Infrastructure", "Water Supply", or "Other"\n'
        '- "urgency": One of "High", "Medium", or "Low"\n'
        '- "detected_location": Extract the location or return "Unspecified"\n'
        '- "actionable_summary": A 1-sentence English summary\n\n'
        f"Complaint:\n{complaint_text}"
    )

    # Use the Google GenAI SDK with the model 'gemini-3.5-flash'
    response = client.models.generate_content(
        model='gemini-3.5-flash',
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ComplaintAnalysis,
        ),
    )

    # Parse response text as JSON
    try:
        return json.loads(response.text)
    except json.JSONDecodeError as e:
        # Fallback to strip markdown if the model somehow returned markdown despite instructions
        text = response.text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines[-1].startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        return json.loads(text)

def rank_priority_works(complaint_data: dict, local_constraints: Dict[str, WardConstraint]) -> RankResult:
    """
    Evaluates the parsed complaint JSON against local infrastructure constraints.
    Implements a constraint satisfaction prioritization system using adaptive rules:
      - Immediately disqualifies projects exceeding remaining budget (Hard constraint).
      - Adjusts scores based on proximity to nearest hospital (Critical threshold boost).
      - Adjusts scores based on population density (Impact scale boost).
      
    Args:
        complaint_data (dict): The output dictionary from analyze_complaint.
        local_constraints (dict): Mock dataset dictionary with ward-level constraints.
        
    Returns:
        RankResult: Evaluated priority score (0-100), recommended action, and reasoning.
    """
    category = complaint_data.get("category", "Other")
    urgency = complaint_data.get("urgency", "Low")
    detected_location = complaint_data.get("detected_location", "Unspecified")
    
    # 1. Resolve which ward constraints apply
    ward_name = resolve_ward(detected_location)
    ward_info = local_constraints.get(ward_name)
    
    if not ward_info:
        # Safeguard fallback
        ward_info = {
            "remaining_budget": 0.0,
            "distance_to_nearest_hospital_km": 0.0,
            "population_density": 0.0
        }
        
    remaining_budget = ward_info["remaining_budget"]
    distance_to_hospital = ward_info["distance_to_nearest_hospital_km"]
    population_density = ward_info["population_density"]
    
    reasoning_steps = []
    
    # --- HARD CONSTRAINT SATISFACTION CHECK ---
    # Immediately disqualify project if repair cost exceeds remaining budget,
    # EXCEPT for emergency healthcare or water supply issues (High urgency) which bypass budget checks.
    estimated_cost = ESTIMATED_REPAIR_COSTS.get(category, 2000.0)
    is_emergency = (urgency == "High" and category in ["Healthcare", "Water Supply"])
    
    if remaining_budget < estimated_cost and not is_emergency:
        reasoning_steps.append(
            f"DISQUALIFIED: Estimated repair cost (${estimated_cost:,.2f}) "
            f"exceeds remaining ward budget (${remaining_budget:,.2f})."
        )
        return {
            "priority_score": 0.0,
            "recommended_action": "Rejected due to constraints (Insufficient Budget)",
            "ward_evaluated": ward_name,
            "reasoning": " | ".join(reasoning_steps)
        }
    elif remaining_budget < estimated_cost and is_emergency:
        reasoning_steps.append(
            f"EMERGENCY OVERRIDE: Estimated cost (${estimated_cost:,.2f}) exceeds remaining budget (${remaining_budget:,.2f}), "
            "but critical emergency status bypasses budget restriction."
        )
        
    # --- ADAPTIVE PRIORITIZATION SCORING ---
    score = 0.0
    
    # A. Base score from complaint urgency
    urgency_points = {"High": 50.0, "Medium": 30.0, "Low": 10.0}
    base_urgency = urgency_points.get(urgency, 10.0)
    score += base_urgency
    reasoning_steps.append(f"Base Urgency ({urgency}) adds {base_urgency} pts.")
    
    # B. Category importance boost
    category_points = {
        "Healthcare": 15.0,
        "Water Supply": 15.0,
        "Roads & Infrastructure": 10.0,
        "Education": 5.0,
        "Other": 0.0
    }
    base_category = category_points.get(category, 0.0)
    score += base_category
    reasoning_steps.append(f"Category '{category}' adds {base_category} pts.")
    
    # C. Adaptive Boost: Distance to nearest hospital for health-related / water supply issues
    # If the hospital is far away (> 5.0 km) in a health/utility issue, the severity and urgency increases
    if category in ["Healthcare", "Water Supply"]:
        if distance_to_hospital > 5.0:
            score += 20.0
            reasoning_steps.append(
                f"Critical distance to hospital ({distance_to_hospital} km) exceeds 5 km threshold, boosting priority by 20.0 pts."
            )
            
    # D. Scale boost based on population density
    if population_density > 5000.0:
        score += 15.0
        reasoning_steps.append(f"High population density ({population_density}/km²) increases community impact, adding 15.0 pts.")
    elif population_density > 1000.0:
        score += 5.0
        reasoning_steps.append(f"Moderate population density ({population_density}/km²) adds 5.0 pts.")
        
    # Clamp score between 0 and 100
    final_score = max(0.0, min(100.0, score))
    
    # Determine recommended action based on threshold boundaries
    if final_score >= 75.0:
        recommended_action = "Fast-Track"
    elif final_score >= 40.0:
        recommended_action = "Review Required"
    else:
        recommended_action = "Routine Backlog"
        
    reasoning_steps.append(f"Budget verified: remaining budget ${remaining_budget:,.2f} is sufficient.")
    
    return {
        "priority_score": final_score,
        "recommended_action": recommended_action,
        "ward_evaluated": ward_name,
        "reasoning": " | ".join(reasoning_steps)
    }

def get_keywords(text: str) -> set:
    """Helper to extract unique normalized keywords from text, excluding common stopwords."""
    stopwords = {"the", "a", "an", "in", "of", "and", "is", "at", "has", "been", "for", "near", "on", "to", "with", "from", "that", "this", "are", "we", "have", "had", "our"}
    # Clean string punctuation
    clean_text = text.lower()
    for char in [".", ",", "-", "!", "?", "(", ")", '"', "'", ";", ":"]:
        clean_text = clean_text.replace(char, " ")
    words = clean_text.split()
    return {w for w in words if w not in stopwords and len(w) > 2}

def get_jaccard_similarity(text1: str, text2: str) -> float:
    """Calculates Jaccard similarity coefficient between two text strings based on keyword overlap."""
    words1 = get_keywords(text1)
    words2 = get_keywords(text2)
    if not words1 or not words2:
        return 0.0
    intersection = words1.intersection(words2)
    union = words1.union(words2)
    return len(intersection) / len(union)

def cluster_recurring_themes(complaints_list: list) -> list:
    """
    Groups citizen complaints into aggregated "Recurring Themes" based on:
      - Exact match on category
      - Exact match on resolved ward/location (via resolve_ward)
      - Word-overlap similarity >= 30% on actionable_summary.
      
    Args:
        complaints_list (list): List of processed complaint dictionaries.
        
    Returns:
        list: Consolidated list of Meta-Issue dictionaries sorted by aggregate priority score.
    """
    clusters = []  # List of lists of complaint dicts
    
    for complaint in complaints_list:
        category = complaint.get("category", "Other")
        location = complaint.get("detected_location", "Unspecified")
        ward = resolve_ward(location)
        summary = complaint.get("actionable_summary", "")
        
        matched_cluster = None
        for cluster in clusters:
            representative = cluster[0]
            rep_category = representative.get("category", "Other")
            rep_location = representative.get("detected_location", "Unspecified")
            rep_ward = resolve_ward(rep_location)
            rep_summary = representative.get("actionable_summary", "")
            
            # Constraints:
            # 1. Exact match on category
            # 2. Exact match on resolved ward
            # 3. Simple keyword-overlap similarity check on the actionable_summary >= 0.3
            if category == rep_category and ward == rep_ward:
                similarity = get_jaccard_similarity(summary, rep_summary)
                if similarity >= 0.3:
                    matched_cluster = cluster
                    break
        
        if matched_cluster is not None:
            matched_cluster.append(complaint)
        else:
            clusters.append([complaint])
            
    meta_issues = []
    for cluster in clusters:
        representative = cluster[0]
        category = representative.get("category", "Other")
        location = representative.get("detected_location", "Unspecified")
        ward = resolve_ward(location)
        count = len(cluster)
        
        # Overarching theme name formulation
        if location != "Unspecified":
            theme = f"{category} Issues in {location} ({ward.split(' (')[0]})"
        else:
            theme = f"{category} Issues in {ward}"
            
        # Calculate aggregate priority score with a volume multiplier
        priority_scores = [c.get("priority_score", 0.0) for c in cluster]
        avg_priority = sum(priority_scores) / count
        # Volume multiplier: +15% per additional complaint in the cluster
        volume_multiplier = 1.0 + 0.15 * (count - 1)
        aggregate_score = round(avg_priority * volume_multiplier, 1)
        
        # Get list of original complaint IDs in this theme
        complaint_ids = [c.get("id") for c in cluster if c.get("id") is not None]
        
        meta_issues.append({
            "theme": theme,
            "category": category,
            "detected_location": location,
            "ward": ward,
            "complaint_count": count,
            "aggregate_priority_score": aggregate_score,
            "complaint_ids": complaint_ids
        })
        
    # Sort by aggregate_priority_score from highest to lowest
    meta_issues.sort(key=lambda x: x["aggregate_priority_score"], reverse=True)
    return meta_issues

# =====================================================================
# Main execution & test block
# =====================================================================

if __name__ == "__main__":
    # Test case 1: Standard complaint (resolved to Ward B - Suburbs)
    sample_complaint_1 = (
        "The water pump near the community center in Sector 4 has been broken for three days. "
        "Dirty water is leaking everywhere, and we have no clean water to drink."
    )
    
    # Test case 2: Budget-constrained complaint (resolved to Ward C - Rural Fringe)
    sample_complaint_2 = (
        "There is a severe lack of basic medical supplies at the Sector 9 rural health post. "
        "We are completely out of bandaging and critical first-aid materials."
    )
    
    print("Testing Civic-Tech Prioritization Pipeline:")
    print("=" * 70)
    
    # Check if API Key is available in the environment to perform live runs
    if not os.environ.get("GEMINI_API_KEY"):
        print("Note: GEMINI_API_KEY is not set. Running with mock extraction results for demonstration.")
        print("Set GEMINI_API_KEY to run live Gemini 3.5 Flash queries.\n")
        
        # Mock extracted content for Complaint 1
        mock_extracted_1 = {
            "category": "Water Supply",
            "urgency": "High",
            "detected_location": "Sector 4",
            "actionable_summary": "Water pump in Sector 4 community center is broken, causing water leakage and shortage."
        }
        
        # Mock extracted content for Complaint 2
        mock_extracted_2 = {
            "category": "Healthcare",
            "urgency": "High",
            "detected_location": "Sector 9",
            "actionable_summary": "First-aid and bandaging supplies are completely depleted at Sector 9 health post."
        }
        
        for idx, (complaint_text, mock_extracted) in enumerate([
            (sample_complaint_1, mock_extracted_1),
            (sample_complaint_2, mock_extracted_2)
        ], 1):
            print(f"CASE {idx}: {complaint_text}")
            print("-" * 50)
            print("Extracted Data (Mocked):")
            print(json.dumps(mock_extracted, indent=2))
            print("\nEvaluating Constraints & Ranking:")
            ranked = rank_priority_works(mock_extracted, MOCK_WARD_CONSTRAINTS)
            print(json.dumps(ranked, indent=2))
            print("=" * 70)
            
    else:
        # Live run with Gemini 3.5 Flash API
        for idx, complaint_text in enumerate([sample_complaint_1, sample_complaint_2], 1):
            try:
                print(f"CASE {idx}: {complaint_text}")
                print("-" * 50)
                print("Calling Gemini 3.5 Flash for extraction...")
                extracted = analyze_complaint(complaint_text)
                print("Extracted Data (Live):")
                print(json.dumps(extracted, indent=2))
                
                print("\nEvaluating Constraints & Ranking:")
                ranked = rank_priority_works(extracted, MOCK_WARD_CONSTRAINTS)
                print(json.dumps(ranked, indent=2))
                print("=" * 70)
            except Exception as e:
                print(f"Error during execution of Case {idx}: {e}")
                print("=" * 70)
