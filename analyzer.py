from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
import re

analyzer = SentimentIntensityAnalyzer()

# List of distress keywords that might be hidden in normal conversation
DISTRESS_KEYWORDS = [
    "help", "stop", "please", "leave me alone", "scared", "terrified",
    "danger", "emergency", "hurt", "pain", "someone is following me",
    "follow", "stranger", "weapon", "call the police", "911", "police",
    "save me", "don't touch me"
]

def analyze_speech(text):
    """
    Analyzes the transcribed text for distress keywords and sentiment stress.
    Returns a danger score and identified triggers.
    """
    if not text:
        return {"danger_score": 0, "status": "Safe", "triggers": [], "sentiment": 0}

    text_lower = text.lower()
    
    # 1. Check for distress keywords
    found_keywords = []
    for keyword in DISTRESS_KEYWORDS:
        # Using word boundaries to avoid partial matches depending on the keyword
        if re.search(r'\b' + re.escape(keyword) + r'\b', text_lower):
            found_keywords.append(keyword)
            
    # Calculate score from keywords (each keyword adds to the danger score, maxing out at some point)
    keyword_score = min(len(found_keywords) * 30, 80) # up to 80 points just from keywords
    
    # 2. Perform Sentiment Analysis
    # VADER sentiment score: compound ranges from -1 (most extreme negative) to +1 (most extreme positive)
    sentiment_dict = analyzer.polarity_scores(text)
    compound_score = sentiment_dict['compound']
    
    # We are looking for extreme negative sentiment (fear, anger, stress)
    # Map -1 to 0 (high stress) to a score of 40 to 0
    sentiment_stress_score = 0
    if compound_score < 0:
        sentiment_stress_score = abs(compound_score) * 40 # Max 40 points
        
    # Total Danger Score (Max ~ 120, capped at 100)
    danger_score = min(int(keyword_score + sentiment_stress_score), 100)
    
    status = "Safe"
    if danger_score >= 70:
        status = "Emergency"
    elif danger_score >= 40:
        status = "Warning"
        
    return {
        "danger_score": danger_score,
        "status": status,
        "triggers": found_keywords,
        "sentiment": compound_score
    }
