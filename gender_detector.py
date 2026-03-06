import numpy as np
import soundfile as sf
import io
import pydub


def extract_pitch_autocorrelation(y, sr, fmin=50, fmax=500):
    """
    Extract fundamental frequency (F0) using autocorrelation method.
    Works with numpy only — no scipy or librosa required.
    
    Args:
        y: Audio signal as numpy array
        sr: Sample rate
        fmin: Minimum expected frequency (Hz)
        fmax: Maximum expected frequency (Hz)
    
    Returns:
        mean_pitch: Mean F0 in Hz (0.0 if no voiced frames detected)
        voiced_count: Number of voiced frames detected
    """
    # Frame parameters
    frame_length = int(0.03 * sr)   # 30ms frames
    hop_length = int(0.01 * sr)     # 10ms hop
    
    # Lag range corresponding to fmin and fmax
    min_lag = int(sr / fmax)
    max_lag = int(sr / fmin)
    
    pitches = []
    
    num_frames = (len(y) - frame_length) // hop_length + 1
    
    for i in range(num_frames):
        start = i * hop_length
        frame = y[start : start + frame_length]
        
        # Skip very quiet frames (likely silence)
        energy = np.sum(frame ** 2) / len(frame)
        if energy < 1e-6:
            continue
        
        # Normalize frame
        frame = frame - np.mean(frame)
        
        # Compute autocorrelation using numpy correlate
        # We only need lags from min_lag to max_lag
        autocorr = np.correlate(frame, frame, mode='full')
        autocorr = autocorr[len(autocorr) // 2:]  # Keep positive lags only
        
        # Search for peak in the valid lag range
        if max_lag >= len(autocorr):
            continue
            
        search_region = autocorr[min_lag:max_lag + 1]
        
        if len(search_region) == 0:
            continue
        
        # Find the peak
        peak_idx = np.argmax(search_region)
        peak_lag = peak_idx + min_lag
        peak_value = search_region[peak_idx]
        
        # Voiced/unvoiced decision: peak should be significant relative to zero-lag
        if autocorr[0] > 0 and peak_value / autocorr[0] > 0.3:
            pitch = sr / peak_lag
            pitches.append(pitch)
    
    if len(pitches) == 0:
        return 0.0, 0
    
    mean_pitch = float(np.mean(pitches))
    return round(mean_pitch, 2), len(pitches)


def extract_mfcc_simple(y, sr, n_mfcc=13):
    """
    Simplified MFCC extraction using numpy only.
    Uses a basic mel-filterbank + DCT approach.
    """
    # Frame and FFT parameters
    frame_length = int(0.025 * sr)  # 25ms
    hop_length = int(0.01 * sr)     # 10ms
    n_fft = 512
    
    # Pad frame_length to n_fft if needed
    if frame_length > n_fft:
        n_fft = 2 ** int(np.ceil(np.log2(frame_length)))
    
    num_frames = (len(y) - frame_length) // hop_length + 1
    
    if num_frames <= 0:
        return [0.0] * n_mfcc
    
    # Compute power spectrum for each frame
    power_frames = []
    for i in range(num_frames):
        start = i * hop_length
        frame = y[start:start + frame_length]
        # Apply Hamming window
        windowed = frame * np.hamming(len(frame))
        # Zero-pad to n_fft
        padded = np.zeros(n_fft)
        padded[:len(windowed)] = windowed
        # FFT
        spectrum = np.abs(np.fft.rfft(padded)) ** 2
        power_frames.append(spectrum)
    
    power_frames = np.array(power_frames)
    
    # Create mel filterbank
    n_mels = 26
    low_freq_mel = 0
    high_freq_mel = 2595 * np.log10(1 + (sr / 2) / 700)
    mel_points = np.linspace(low_freq_mel, high_freq_mel, n_mels + 2)
    hz_points = 700 * (10 ** (mel_points / 2595) - 1)
    bin_points = np.floor((n_fft + 1) * hz_points / sr).astype(int)
    
    fbank = np.zeros((n_mels, n_fft // 2 + 1))
    for m in range(1, n_mels + 1):
        f_m_minus = bin_points[m - 1]
        f_m = bin_points[m]
        f_m_plus = bin_points[m + 1]
        
        for k in range(f_m_minus, f_m):
            if f_m != f_m_minus:
                fbank[m - 1, k] = (k - f_m_minus) / (f_m - f_m_minus)
        for k in range(f_m, f_m_plus):
            if f_m_plus != f_m:
                fbank[m - 1, k] = (f_m_plus - k) / (f_m_plus - f_m)
    
    # Apply filterbank
    filter_banks = np.dot(power_frames, fbank.T)
    filter_banks = np.where(filter_banks == 0, np.finfo(float).eps, filter_banks)
    filter_banks = 20 * np.log10(filter_banks)
    
    # DCT (Type-II) to get MFCCs — manual implementation
    num_ceps = n_mfcc
    n = filter_banks.shape[1]
    dct_matrix = np.zeros((num_ceps, n))
    for i in range(num_ceps):
        for j in range(n):
            dct_matrix[i, j] = np.cos(np.pi * i * (2 * j + 1) / (2 * n))
    
    mfccs = np.dot(filter_banks, dct_matrix.T)
    
    # Return mean MFCCs across all frames
    return np.mean(mfccs, axis=0).tolist()


def classify_gender(audio_bytes):
    """
    Classify speaker gender using pitch-based thresholding.
    
    Typical vocal ranges:
      - Male:   85 Hz  – 180 Hz  (mean ~120 Hz)
      - Female: 165 Hz – 255 Hz  (mean ~210 Hz)
    
    Threshold: 170 Hz
      - F0 > 170 Hz  → Female
      - F0 <= 170 Hz → Male
      - No voiced frames → Unknown
    
    Returns dict with gender, confidence, and extracted features.
    """
    PITCH_THRESHOLD = 170.0  # Hz
    
    try:
        # Load audio from bytes buffer
        audio_buffer = io.BytesIO(audio_bytes)
        
        # Convert WebM/Opus or other formats to WAV using pydub
        audio_segment = pydub.AudioSegment.from_file(audio_buffer)
        
        # Export to a new BytesIO buffer in WAV format
        wav_buffer = io.BytesIO()
        audio_segment.export(wav_buffer, format="wav")
        wav_buffer.seek(0)
        
        # Read the WAV buffer with soundfile
        y, sr = sf.read(wav_buffer)
        
        # Convert to mono if stereo
        if len(y.shape) > 1:
            y = np.mean(y, axis=1)
        y = y.astype(np.float32)
    except Exception as e:
        return {
            "gender": "unknown",
            "confidence": 0.0,
            "mean_pitch": 0.0,
            "voiced_frames": 0,
            "message": f"Could not read audio format: {str(e)}"
        }
    
    # Resample to 22050 Hz for consistent analysis (simple decimation)
    if sr != 22050:
        ratio = 22050 / sr
        new_length = int(len(y) * ratio)
        indices = np.linspace(0, len(y) - 1, new_length).astype(int)
        y = y[indices]
        sr = 22050
    
    # Extract pitch
    mean_pitch, voiced_frames = extract_pitch_autocorrelation(y, sr)
    
    # Extract MFCCs (for informational purposes)
    mfcc_mean = extract_mfcc_simple(y, sr)
    
    # Need at least some voiced frames for a reliable classification
    if voiced_frames < 8 or mean_pitch == 0.0:
        return {
            "gender": "unknown",
            "confidence": 0.0,
            "mean_pitch": mean_pitch,
            "voiced_frames": voiced_frames,
            "mfcc_mean": mfcc_mean,
            "message": "No clear speech detected. Speak for at least 3 seconds."
        }
        
    CONFIDENCE_THRESHOLD = 0.75
    
    # Classify based on pitch threshold
    if mean_pitch > PITCH_THRESHOLD:
        gender = "female"
        # Heuristic confidence based on distance from the boundary (max 100Hz distance for full confidence)
        distance = mean_pitch - PITCH_THRESHOLD
        confidence = min(distance / 60.0, 1.0) 
    else:
        gender = "male"
        distance = PITCH_THRESHOLD - mean_pitch
        confidence = min(distance / 60.0, 1.0)
    
    # Check against confidence threshold
    if confidence < CONFIDENCE_THRESHOLD:
        return {
            "gender": "unknown",
            "confidence": round(confidence, 2),
            "mean_pitch": mean_pitch,
            "voiced_frames": voiced_frames,
            "mfcc_mean": mfcc_mean,
            "message": "Speech analysis inconclusive. Please speak louder and closer to the mic."
        }
    
    return {
        "gender": gender,
        "confidence": round(confidence, 2),
        "mean_pitch": mean_pitch,
        "voiced_frames": voiced_frames,
        "mfcc_mean": mfcc_mean,
        "message": f"{gender.capitalize()} voice verified (confidence: {round(confidence*100)}%)"
    }
