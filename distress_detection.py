import json
import logging
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from database_manager import get_settings

analyzer = SentimentIntensityAnalyzer()

def analyze_speech(text):
    """
    Analyzes transcribed text for threat severity and SOS keywords.
    Returns JSON format:
    {
        "threat_score": value (0.0 to 1.0),
        "detected_text": text,
        "alert_status": "NORMAL" or "EMERGENCY"
    }
    """
    if not text:
        return {
            "threat_score": 0.0,
            "detected_text": "",
            "alert_status": "NORMAL"
        }

    try:
        # Load dynamic settings (sensitivity etc)
        settings = get_settings()
        DISTRESS_KEYWORDS = settings.get("keywords", [])
        SECRET_PHRASES = settings.get("secret_phrases", [])
        
        # Mandatory SOS keywords for hackathon requirements
        SOS_KEYWORDS = ["sos", "help me", "save me", "danger", "threat"]
        
        text_lower = text.lower()
        sos_detected = False
        
        # Check for SOS keywords (Immediate Trigger)
        for sos_word in SOS_KEYWORDS:
            if sos_word in text_lower:
                sos_detected = True
                break
        
        # Sentiment Analysis using VADER
        sentiment_result = analyzer.polarity_scores(text)
        compound = sentiment_result['compound'] 
        
        # Calculate threat score (0 to 1)
        # We map strongly negative sentiment (-1.0 to 0.0) to (1.0 to 0.0 threat)
        # Positive sentiment (0.0 to 1.0) maps to 0.0 threat
        base_threat = abs(min(compound, 0))
        
        # Boost threat based on dynamic DISTRESS_KEYWORDS
        keyword_hits = sum(1 for kw in DISTRESS_KEYWORDS if kw in text_lower)
        keyword_boost = min(keyword_hits * 0.2, 0.5)
        
        # Secret phrases boost to max immediately
        secret_hit = any(sp in text_lower for sp in SECRET_PHRASES)
        
        if secret_hit:
            threat_score = 1.0
        else:
            threat_score = min(base_threat + keyword_boost, 1.0)

        # Decision Rules:
        # If threat score >= 0.7 OR SOS keyword is detected -> trigger emergency alert.
        alert_status = "NORMAL"
        if threat_score >= 0.7 or sos_detected:
            alert_status = "EMERGENCY"

        return {
            "threat_score": round(threat_score, 2),
            "detected_text": text,
            "alert_status": alert_status,
            # Supporting legacy dashboard fields for UI compatibility
            "level": 3 if alert_status == "EMERGENCY" else (1 if threat_score > 0.3 else 0),
            "danger_score": int(threat_score * 100),
            "triggers": SOS_KEYWORDS if sos_detected else [] 
        }

    except Exception as e:
        logging.error(f"Detection failed: {e}. Falling back to stable output.")
        return {
            "threat_score": 0.0,
            "detected_text": text,
            "alert_status": "NORMAL",
            "error": str(e)
        }

