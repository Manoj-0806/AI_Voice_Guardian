import os
from flask import Flask, render_template, request, jsonify

# Inject local FFmpeg into PATH
ffmpeg_path = os.path.join(os.path.dirname(__file__), 'ffmpeg_bin', 'ffmpeg-master-latest-win64-gpl', 'bin')
if os.path.exists(ffmpeg_path) and ffmpeg_path not in os.environ['PATH']:
    os.environ['PATH'] = ffmpeg_path + os.pathsep + os.environ['PATH']

from audio_processing import convert_webm_to_wav, apply_noise_reduction, apply_vad
from speech_recognition_module import transcribe_audio
from distress_detection import analyze_speech
from emergency_alert import trigger_emergency_response
from database_manager import get_settings, update_settings, get_profile, update_profile, get_analytics, log_analytic, reset_analytics, log_alert, log_location, log_incident, get_incidents, get_notification_logs

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB max

@app.route('/')
def index():
    return render_template('index.html', title="Home | Voice Dashboard")

@app.route('/analytics')
def analytics():
    return render_template('analytics.html', title="Analytics")

@app.route('/settings')
def settings():
    return render_template('settings.html', title="Settings")

@app.route('/profile')
def profile():
    return render_template('profile.html', title="Profile")

# === API ENDPOINTS FOR HACKATHON DASHBOARD ===
@app.route('/api/stats', methods=['GET'])
def fetch_stats():
    # Adding incidents so the charts can plot trends later
    stats = get_analytics()
    stats['incidents'] = get_incidents()
    stats['notification_logs'] = get_notification_logs()
    return jsonify(stats)

@app.route('/api/reset_stats', methods=['POST'])
def reset_stats_api():
    """Resets the SQLite analytics for hackathon demo runs"""
    reset_analytics()
    return jsonify({"status": "success", "message": "Demo stats reset"})

@app.route('/api/settings', methods=['GET', 'POST'])
def handle_settings():
    if request.method == 'POST':
        data = request.json
        update_settings(data)
        return jsonify({"status": "success", "message": "Settings updated"})
    return jsonify(get_settings())

@app.route('/api/profile', methods=['GET', 'POST'])
def handle_profile():
    if request.method == 'POST':
        data = request.json
        update_profile(data)
        return jsonify({"status": "success", "message": "Profile updated"})
    return jsonify(get_profile())

@app.route('/api/location', methods=['POST'])
def handle_location():
    data = request.json
    log_location(data.get('lat'), data.get('lng'))
    return jsonify({"status": "logged"})

@app.route('/api/sos', methods=['POST'])
def handle_sos():
    data = request.json
    # Manual SOS Button Trigger
    log_analytic('distress_alerts')
    log_alert('Button SOS', 'Manual Trigger', 100)
    if 'lat' in data and 'lng' in data:
        log_location(data['lat'], data['lng'])
        trigger_emergency_response(100, ['Manual SOS Button'], {'lat': data['lat'], 'lng': data['lng']})
    else:
        trigger_emergency_response(100, ['Manual SOS Button'], None)
    return jsonify({"status": "Emergency protocol activated via SOS button."})

@app.route('/api/report', methods=['POST'])
def handle_report():
    data = request.json
    # Basic API validation
    if not data or 'description' not in data:
        return jsonify({"status": "error", "message": "Invalid report payload"}), 400
        
    log_incident(
        location=data.get('location', 'Unknown'),
        description=data.get('description', ''),
        category=data.get('category', 'General')
    )
    return jsonify({"status": "success", "message": "Incident logged securely."})

# === CORE MICROPHONE ROUTES ===

@app.route('/process_audio', methods=['POST'])
def handle_process_audio():
    """
    Main Pipeline Endpoint:
    Receives audio chunks -> WAV -> Noise Reduce -> VAD -> STT -> Distress Detection -> Response.
    """
    if 'audio' not in request.files:
        return jsonify({"error": "No audio file provided"}), 400
    
    file = request.files['audio']
    audio_bytes = file.read()
    
    if len(audio_bytes) == 0:
        return jsonify({"error": "Empty audio chunk"}), 400

    # 1. Convert incoming WebM to WAV properly for processing
    wav_buffer = convert_webm_to_wav(audio_bytes)
    if not wav_buffer:
        return jsonify({"error": "Failed to decode standard audio"}), 400

    # 2. Noise Reduction (using purely Numpy fallback or noisereduce)
    clean_wav = apply_noise_reduction(wav_buffer)
    
    # 3. Voice Activity Detection (VAD)
    # If no speech is detected, we ignore the chunk to prevent STT hallucinations
    has_voice, clean_wav = apply_vad(clean_wav)
    if not has_voice:
        return jsonify({"message": "Silence detected, ignoring.", "text": "", "status": "Safe", "danger_score": 0, "triggers": []}), 200

    # Track voice inputs
    log_analytic('voice_inputs')
    log_analytic('total_interactions')

    # 4. Speech-to-Text (using SpeechRecognition)
    text = transcribe_audio(clean_wav)
    if not text:
        return jsonify({"message": "Could not recognize speech.", "text": "", "status": "Safe", "danger_score": 0, "triggers": []}), 200

    # 5. Distress Detection
    analysis = analyze_speech(text)
    
    # Check if we should trigger an emergency based on alert_status
    if analysis.get('alert_status') == "EMERGENCY":
        log_analytic('distress_alerts')
        log_alert('Voice EMERGENCY', ', '.join(analysis.get('triggers', ['Speech Trigger'])), analysis.get('danger_score', 100))
        
        # Extract location if sent along with the form
        location_data = None
        if 'lat' in request.form and 'lng' in request.form:
            location_data = {'lat': request.form['lat'], 'lng': request.form['lng']}
            log_location(location_data['lat'], location_data['lng'])
            
        trigger_emergency_response(analysis.get('danger_score', 100), analysis.get('triggers', ['Speech Trigger']), location_data)
    else:
        log_analytic('normal_interactions')

    # Combine response for frontend and required JSON structure
    # The return format MUST be: {"threat_score": value, "detected_text": text, "alert_status": "NORMAL" or "EMERGENCY"}
    # We add extra fields for dashboard UI compatibility
    
    response_data = analysis.copy()
    response_data['status'] = "Emergency" if analysis['alert_status'] == "EMERGENCY" else "Safe"
    
    if response_data['status'] == "Safe":
        response_data['message'] = "No emergency detected."
    else:
        response_data['message'] = "Emergency protocol activated."

    return jsonify(response_data), 200


@app.route('/trigger_emergency', methods=['POST'])
def handle_emergency():
    """Legacy endpoint for UI-driven emergencies (optional but good to keep)."""
    data = request.json
    score = data.get('danger_score', 0)
    triggers = data.get('triggers', [])
    location = data.get('location', None)
    
    trigger_emergency_response(score, triggers, location)
    return jsonify({"status": "Emergency protocol activated."}), 200

if __name__ == '__main__':
    import socket
    
    def is_port_in_use(port):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(('127.0.0.1', port)) == 0

    port = 5000
    if is_port_in_use(port):
        print(f"Port {port} is in use, falling back to 5001")
        port = 5001
        
    app.run(debug=True, port=port)
