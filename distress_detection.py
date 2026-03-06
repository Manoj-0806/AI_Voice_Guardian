import json
import logging
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from database_manager import get_settings

analyzer = SentimentIntensityAnalyzer()

def analyze_speech(text):
    """
    Analyzes transcribed text for distress signals, keywords, and sentiment
    using dynamically loaded configurations.
    Returns:
        dict: containing danger_score, sentiment, status, and triggers.
    """
    if not text:
        return {
            "danger_score": 0,
            "sentiment": 0.0,
            "status": "Safe",
            "triggers": []
        }

    # Load dynamic settings
    settings = get_settings()
    DISTRESS_KEYWORDS = settings.get("keywords", [])
    SECRET_PHRASES = settings.get("secret_phrases", [])
    sensitivity = settings.get("sensitivity", "medium")

    text_lower = text.lower()
    triggers = []
    base_score = 0
    
    # Sensitivity Multipliers
    multiplier = 1.0
    if sensitivity == "high":
        multiplier = 1.5
    elif sensitivity == "low":
        multiplier = 0.5

    # 1. Check for secret distress phrases (High Priority)
    for phrase in SECRET_PHRASES:
        if phrase in text_lower:
            triggers.append(phrase)
            base_score += 100 # Immediate maximum emergency

    # 2. Check for general distress keywords
    for keyword in DISTRESS_KEYWORDS:
        if keyword in text_lower:
            triggers.append(keyword)
            base_score += 40 * multiplier # Increased from 30

    # 3. Sentiment Analysis (Panic Tone)
    sentiment_result = analyzer.polarity_scores(text)
    compound = sentiment_result['compound'] 
    
    # Increase score if sentiment is strongly negative (panic tone)
    if compound < -0.3:
        # If keywords are present + panic tone, push towards Level 2/3
        if len(triggers) > 0:
            base_score += 30 * multiplier # Increased from 20
        else:
            base_score += 20 * multiplier # Pure panic tone without keywords = Suspicious
        
    # Cap score at 100
    danger_score = min(int(max(base_score, 0)), 100)
    
    # Determine Status based on a 4-level threat system
    # Level 0 (Safe) : 0-25
    # Level 1 (Suspicious) : 26-50
    # Level 2 (Danger) : 51-75
    # Level 3 (Emergency) : 76-100
    
    if danger_score >= 76:
        status = "Emergency" # Level 3
        level = 3
    elif danger_score >= 51:
        status = "Danger" # Level 2
        level = 2
    elif danger_score >= 26:
        status = "Suspicious" # Level 1
        level = 1
    else:
        status = "Safe" # Level 0
        level = 0
        
    return {
        "danger_score": danger_score,
        "sentiment": round(compound, 4),
        "status": status,
        "level": level,
        "triggers": list(set(triggers)) # Unique triggers
    }
