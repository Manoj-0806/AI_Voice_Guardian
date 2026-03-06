import speech_recognition as sr

def transcribe_audio(wav_buffer):
    """
    Takes a cleanly processed WAV BytesIO buffer and uses Google Web Speech API
    to transcribe it to text.
    """
    recognizer = sr.Recognizer()
    
    try:
        # Load the audio into the recognizer
        wav_buffer.seek(0)
        with sr.AudioFile(wav_buffer) as source:
            # Adjust for ambient noise briefly
            recognizer.adjust_for_ambient_noise(source, duration=0.2)
            audio_data = recognizer.record(source)
            
        print("[STT] Sending audio to Google Speech-to-Text...")
        
        # We use the Google recognizer with Indian Accent support as requested
        text = recognizer.recognize_google(audio_data, language='en-IN')
        print(f"[STT] Detected: '{text}'")
        return text.lower()
        
    except sr.UnknownValueError:
        print("[STT] Google Speech Recognition could not understand audio")
        return ""
    except sr.RequestError as e:
        print(f"[STT] Could not request results from Google Speech Recognition service; {e}")
        return ""
    except Exception as e:
        print(f"[STT] Unexpected error during transcription: {e}")
        return ""
