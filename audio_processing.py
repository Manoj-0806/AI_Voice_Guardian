import io
import os
import pydub
import numpy as np
import soundfile as sf

# Attempt to import librosa and noisereduce.
# They require scipy, which does not easily install on 32-bit Windows.
# We will use purely numpy-based fallbacks if they are not available.
try:
    import librosa
    import noisereduce as nr
    HAS_NOISEREDUCE = True
except ImportError:
    HAS_NOISEREDUCE = False

def convert_webm_to_wav(audio_bytes):
    """
    Converts incoming WebM/Opus audio blob from the browser to WAV format using pydub.
    """
    try:
        audio_buffer = io.BytesIO(audio_bytes)
        audio_segment = pydub.AudioSegment.from_file(audio_buffer)
        
        # Resample to 16kHz mono (standard for speech recognition)
        audio_segment = audio_segment.set_frame_rate(16000).set_channels(1)
        
        wav_buffer = io.BytesIO()
        audio_segment.export(wav_buffer, format="wav")
        wav_buffer.seek(0)
        
        return wav_buffer
    except Exception as e:
        print(f"[AUDIO] Conversion error: {e}")
        return None

def apply_noise_reduction(wav_buffer):
    """
    Applies noise reduction using noisereduce (if available) or a numpy spectral gate fallback.
    Returns a new WAV BytesIO buffer.
    """
    try:
        wav_buffer.seek(0)
        y, sr = sf.read(wav_buffer)
        
        if HAS_NOISEREDUCE:
            print("[AUDIO] Applying noisereduce library for noise reduction.")
            # Standard noisereduce usage
            reduced_noise = nr.reduce_noise(y=y, sr=sr, stationary=True)
        else:
            print("[AUDIO] noisereduce not found. Using numpy spectral gating fallback.")
            # Simple thresholding / spectral gate
            # A very simplified version of noise reduction based on amplitude threshold
            noise_floor = np.mean(np.abs(y[:int(sr * 0.5)])) # first 0.5s as noise profile
            # Soft thresholding
            reduced_noise = np.where(np.abs(y) > noise_floor * 1.5, y, y * 0.1)
            
        out_buffer = io.BytesIO()
        sf.write(out_buffer, reduced_noise, sr, format='WAV')
        out_buffer.seek(0)
        return out_buffer
    except Exception as e:
        print(f"[AUDIO] Noise reduction error: {e}")
        wav_buffer.seek(0)
        return wav_buffer # return original if failed

def apply_vad(wav_buffer):
    """
    Voice Activity Detection (VAD).
    Analyzes the audio and determines if there is human speech present (based on energy/RMS).
    Returns (has_voice: bool, wav_buffer).
    """
    try:
        wav_buffer.seek(0)
        y, sr = sf.read(wav_buffer)
        
        # Simple RMS Energy based VAD
        frame_length = int(0.03 * sr) # 30ms
        hop_length = int(0.01 * sr)   # 10ms
        
        energies = []
        for i in range(0, len(y) - frame_length, hop_length):
            frame = y[i:i + frame_length]
            energies.append(np.sqrt(np.mean(frame**2)))
            
        if len(energies) == 0:
            return False, wav_buffer
            
        mean_energy = np.mean(energies)
        max_energy = np.max(energies)
        median_energy = np.median(energies)
        std_energy = np.std(energies)
        
        # Heuristic: If max energy is significantly higher than background (median/mean)
        # And above an absolute minimum threshold
        # Also check for variance (std) as speech typically has high energy variance
        threshold = 0.015
        
        is_speech = (max_energy > threshold) and (max_energy > median_energy * 3) and (std_energy > mean_energy * 0.5)
        
        if is_speech:
            print(f"[AUDIO] VAD: Speech detected. (Max: {max_energy:.4f}, Std: {std_energy:.4f})")
            wav_buffer.seek(0)
            return True, wav_buffer
        else:
            print(f"[AUDIO] VAD: No speech detected (Max: {max_energy:.4f}, Median: {median_energy:.4f}).")
            return False, wav_buffer
    except Exception as e:
        print(f"[AUDIO] VAD error: {e}")
        wav_buffer.seek(0)
        return True, wav_buffer # Err on the side of processing if VAD fails
