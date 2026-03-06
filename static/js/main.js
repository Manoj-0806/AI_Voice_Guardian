// State variables
let isListening = true; // Auto-start by default
let emergencyTriggered = false;
let map = null;
let mediaRecorder = null;
let audioChunks = [];
let voiceStream = null;
let chunkInterval = null;
let locationInterval = null;
let marker = null;
let audioContext = null;
let analyser = null;
let micSource = null;
let scriptProcessor = null;
let energyThreshold = 0.035;   // Amplitude threshold for VAD
let isVoiceDetected = false;
let autoStartMic = true;
let alertAudioContext = null;

// DOM Elements
const toggleBtn = document.getElementById('toggle-listening-btn');
const sosBtn = document.getElementById('sos-btn');
const btnText = document.getElementById('btn-text');
const btnIcon = toggleBtn.querySelector('i');
const statusIndicator = document.getElementById('status-indicator');
const statusText = document.getElementById('safety-status-text');
const scoreText = document.getElementById('danger-score');
const scoreProgress = document.getElementById('score-progress');
const triggersDisplay = document.getElementById('triggers-display');
const transcriptContainer = document.getElementById('transcript-container');
const mapOverlay = document.getElementById('map-overlay');
const locationStatus = document.getElementById('location-status');
const emergencyBanner = document.getElementById('emergency-banner');
const recordingStatus = document.getElementById('recording-status');
const genderStatusEl = document.getElementById('gender-status');
const genderTextEl = document.getElementById('gender-text');
const genderIconEl = genderStatusEl ? genderStatusEl.querySelector('i') : null;
const restrictedBanner = document.getElementById('restricted-banner');

// ==========================================
//  INITIALIZATION
// ==========================================
document.addEventListener('DOMContentLoaded', () => {
    initMap();
    toggleBtn.addEventListener('click', toggleListening);
    if (sosBtn) {
        sosBtn.addEventListener('click', triggerManualSOS);
    }

    // Auto-start microphone for continuous listening
    if (autoStartMic) {
        setTimeout(() => startContinuousListeningOnLoad(), 1000);
    }

    // Browser hack: Resume audio context on first user interaction
    const resumeAudio = () => {
        if (audioContext && audioContext.state === 'suspended') {
            audioContext.resume();
        }
        if (alertAudioContext && alertAudioContext.state === 'suspended') {
            alertAudioContext.resume();
        }
        window.removeEventListener('click', resumeAudio);
        window.removeEventListener('touchstart', resumeAudio);
    };
    window.addEventListener('click', resumeAudio);
    window.addEventListener('touchstart', resumeAudio);
});

async function startContinuousListeningOnLoad() {
    appendTranscript("Initializing passive safety monitoring...", true);
    await startContinuousRecording(true);
}

// Initialize map (Leaflet)
function initMap() {
    map = L.map('map').setView([0, 0], 2);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{y}.png', {
        attribution: '&copy; OpenStreetMap contributors'
    }).addTo(map);
}

function updateMapLocation(lat, lng) {
    if (!map) initMap();
    map.setView([lat, lng], 15);

    if (marker) {
        marker.setLatLng([lat, lng]);
    } else {
        marker = L.marker([lat, lng]).addTo(map)
            .bindPopup('Emergency Location')
            .openPopup();
    }

    mapOverlay.style.display = 'none';
    locationStatus.textContent = 'Active - Sharing';
    locationStatus.classList.add('active');
    setTimeout(() => { map.invalidateSize(); }, 200);
}

function updateSystemStatus(state, text) {
    if (!statusIndicator) return;

    statusIndicator.className = 'pulse-indicator';
    statusText.className = 'status-text';

    if (state === 'listening') {
        statusIndicator.classList.add('safe');
        statusText.classList.add('safe-text');
        statusText.textContent = 'Listening for voice...';
    } else if (state === 'voice-detected') {
        statusIndicator.classList.add('warning');
        statusText.classList.add('warning-text');
        statusText.textContent = 'Voice detected';
    } else if (state === 'processing') {
        statusIndicator.classList.add('warning');
        statusText.classList.add('warning-text');
        statusText.textContent = 'Analyzing speech';
    } else if (state === 'danger') {
        statusIndicator.classList.add('danger');
        statusText.classList.add('danger-text');
        playAlertSound(); // Trigger siren
    } else {
        statusIndicator.classList.add('safe');
    }

    if (state !== 'listening' && state !== 'voice-detected' && state !== 'processing') {
        statusText.textContent = text;
    }

    if (genderTextEl) {
        genderStatusEl.classList.remove('hidden');
        genderTextEl.textContent = text;
        if (state === 'danger') {
            genderStatusEl.className = 'gender-badge male'; // Emergency theme
            genderIconEl.className = 'fa-solid fa-triangle-exclamation';
        } else if (state === 'voice-detected' || state === 'processing') {
            genderStatusEl.className = 'gender-badge analyzing';
            genderIconEl.className = 'fa-solid fa-waveform-lines fa-spin';
        } else {
            genderStatusEl.className = 'gender-badge listening';
            genderIconEl.className = 'fa-solid fa-microphone';
        }
    }
}

function resetToIdle() {
    isListening = true;
    btnText.textContent = "Assistant Active";
    btnIcon.className = "fa-solid fa-microphone";
    toggleBtn.classList.add('recording');
}

// Emergency Alarm Sound (Siren Effect)
function playAlertSound() {
    try {
        if (!alertAudioContext) {
            alertAudioContext = new (window.AudioContext || window.webkitAudioContext)();
        }

        const oscillator = alertAudioContext.createOscillator();
        const gainNode = alertAudioContext.createGain();

        oscillator.type = 'sawtooth';
        oscillator.frequency.setValueAtTime(440, alertAudioContext.currentTime); // A4
        oscillator.frequency.exponentialRampToValueAtTime(880, alertAudioContext.currentTime + 0.5);
        oscillator.frequency.exponentialRampToValueAtTime(440, alertAudioContext.currentTime + 1.0);

        oscillator.loop = true;

        gainNode.gain.setValueAtTime(0.1, alertAudioContext.currentTime);
        gainNode.gain.exponentialRampToValueAtTime(0.01, alertAudioContext.currentTime + 2.0);

        oscillator.connect(gainNode);
        gainNode.connect(alertAudioContext.destination);

        oscillator.start();
        oscillator.stop(alertAudioContext.currentTime + 2.0); // Play for 2 seconds
    } catch (e) {
        console.error("Audio playback error:", e);
    }
}

// ==========================================
//  CONTINUOUS AUDIO PIPELINE
// ==========================================
async function startContinuousRecording(onLoad = false) {
    isListening = true;
    btnText.textContent = "Assistant Active";
    btnIcon.className = "fa-solid fa-microphone";
    toggleBtn.classList.add('recording');

    try {
        if (!voiceStream) {
            voiceStream = await navigator.mediaDevices.getUserMedia({ audio: true });
        }

        setupFrontendVAD();
        startChunkingInterval();

        updateSystemStatus('listening', 'Listening for voice...');
    } catch (err) {
        console.error("Mic access denied:", err);
        updateSystemStatus('danger', 'Mic Access Denied');
        appendTranscript("Error: Microphone access denied. Please enable it in browser settings.", true);
    }
}

function setupFrontendVAD() {
    if (audioContext) return;

    try {
        audioContext = new (window.AudioContext || window.webkitAudioContext)();
        analyser = audioContext.createAnalyser();
        analyser.fftSize = 256;
        micSource = audioContext.createMediaStreamSource(voiceStream);
        scriptProcessor = audioContext.createScriptProcessor(2048, 1, 1);

        micSource.connect(analyser);
        analyser.connect(scriptProcessor);
        scriptProcessor.connect(audioContext.destination);

        scriptProcessor.onaudioprocess = () => {
            const array = new Uint8Array(analyser.frequencyBinCount);
            analyser.getByteFrequencyData(array);

            let values = 0;
            for (let i = 0; i < array.length; i++) {
                values += array[i];
            }
            const average = values / array.length;
            const energy = average / 255;

            if (energy > energyThreshold) {
                if (!isVoiceDetected) {
                    isVoiceDetected = true;
                    updateSystemStatus('voice-detected', 'Voice detected');
                }
            } else {
                if (isVoiceDetected) {
                    isVoiceDetected = false;
                    if (!emergencyTriggered) {
                        updateSystemStatus('listening', 'Listening for voice...');
                    }
                }
            }
        };
    } catch (e) {
        console.error("VAD setup error:", e);
    }
}

function startChunkingInterval() {
    if (!voiceStream) return;

    mediaRecorder = new MediaRecorder(voiceStream, { mimeType: 'audio/webm' });
    let currentChunks = [];

    mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) currentChunks.push(e.data);
    };

    mediaRecorder.onstop = () => {
        if (currentChunks.length > 0) {
            const audioBlob = new Blob(currentChunks, { type: 'audio/webm' });
            sendAudioChunkForProcessing(audioBlob);
            currentChunks = [];
        }

        if (isListening) {
            if (mediaRecorder.state === 'inactive') {
                mediaRecorder.start();
            }
        }
    };

    mediaRecorder.start();

    chunkInterval = setInterval(() => {
        // Only stop/restart to capture chunk if recorder is active
        if (mediaRecorder.state === 'recording') {
            mediaRecorder.stop();
        }
    }, 4500); // 4.5 second chunks

    if (navigator.geolocation && !locationInterval) {
        locationInterval = setInterval(() => {
            navigator.geolocation.getCurrentPosition(pos => {
                fetch('/api/location', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ lat: pos.coords.latitude, lng: pos.coords.longitude })
                });
            });
        }, 30000);
    }
}

async function sendAudioChunkForProcessing(blob) {
    // Basic threshold to skip purely silent chunks from network processing
    if (!isVoiceDetected && blob.size < 6000) return;

    updateSystemStatus('processing', 'Analyzing speech');

    const formData = new FormData();
    formData.append('audio', blob, 'chunk.webm');

    if (navigator.geolocation && emergencyTriggered) {
        try {
            navigator.geolocation.getCurrentPosition(pos => {
                formData.append('lat', pos.coords.latitude);
                formData.append('lng', pos.coords.longitude);
            });
        } catch (e) { }
    }

    try {
        const response = await fetch('/process_audio', {
            method: 'POST',
            body: formData
        });

        if (response.ok) {
            const data = await response.json();
            if (data.text) {
                appendTranscript(data.text, true);
                updateDashboardStatus(data);

                if (data.level >= 2) {
                    updateSystemStatus('danger', data.status || 'Emergency detected');
                    appendTranscript("⚠️ DANGER DETECTED! Level " + data.level, true);
                    showPushNotification();
                    setTimeout(() => updateSystemStatus('danger', 'Alert notification sent to trusted contact'), 1500);
                } else if (data.level === 1) {
                    updateSystemStatus('voice-detected', 'Suspicious activity detected');
                    appendTranscript("🔍 Suspicious activity noted.", true);
                } else {
                    // Optional feedback for normal interactions
                    updateSystemStatus('listening', 'Analysing speech...');
                    setTimeout(() => { if (!isVoiceDetected) updateSystemStatus('listening', 'Listening for voice...'); }, 1500);
                }
            }
        }
    } catch (err) {
        console.error("Error processing audio chunk:", err);
    } finally {
        if (!emergencyTriggered) {
            setTimeout(() => {
                if (!isVoiceDetected) updateSystemStatus('listening', 'Listening for voice...');
            }, 1500);
        }
    }
}

// ==========================================
//  UI UPDATES & EMERGENCY
// ==========================================
function updateDashboardStatus(data) {
    const score = data.danger_score || 0;
    const status = data.status || 'Safe';
    const triggers = data.triggers || [];
    const message = data.message || '';

    scoreText.textContent = score;
    scoreProgress.style.width = `${score}%`;

    scoreProgress.className = 'progress-bar';

    if (status === 'Safe') {
        scoreProgress.classList.add('safe-bg');
    } else if (status === 'Warning') {
        scoreProgress.classList.add('warning-bg');
        updateSystemStatus('voice-detected', 'Warning Detected');
    } else if (status === 'Emergency') {
        scoreProgress.classList.add('danger-bg');
        if (!emergencyTriggered) {
            triggerEmergencyProtocol(score, triggers);
        }
    }

    if (triggers.length > 0) {
        triggersDisplay.textContent = `Keywords detected: ${triggers.join(', ')}`;
        triggersDisplay.style.color = 'var(--danger-color)';
    } else {
        triggersDisplay.textContent = message || 'Monitoring active.';
        triggersDisplay.style.color = 'var(--text-secondary)';
    }
}

function triggerEmergencyProtocol(score, triggers) {
    emergencyTriggered = true;
    emergencyBanner.classList.remove('hidden');

    if (navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(
            (position) => {
                const lat = position.coords.latitude;
                const lng = position.coords.longitude;
                updateMapLocation(lat, lng);
            },
            (error) => console.error("Error getting location", error)
        );
    }
}

function appendTranscript(text, isFinal) {
    const placeholder = transcriptContainer.querySelector('.placeholder-text');
    if (placeholder) placeholder.remove();

    const p = document.createElement('p');
    p.textContent = text;
    if (!isFinal) p.style.opacity = '0.7';

    transcriptContainer.appendChild(p);

    while (transcriptContainer.children.length > 20) {
        transcriptContainer.removeChild(transcriptContainer.firstChild);
    }
    transcriptContainer.scrollTop = transcriptContainer.scrollHeight;
}

// ==========================================
//  SOS & INCIDENT REPORTS
// ==========================================
async function triggerManualSOS() {
    sosBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> <span>Sending...</span>';
    updateSystemStatus('danger', 'Emergency detected');

    let payload = {};
    if (navigator.geolocation) {
        try {
            const pos = await new Promise((resolve, reject) => {
                navigator.geolocation.getCurrentPosition(resolve, reject);
            });
            payload = { lat: pos.coords.latitude, lng: pos.coords.longitude };
            updateMapLocation(pos.coords.latitude, pos.coords.longitude);
        } catch (e) { }
    }

    try {
        await fetch('/api/sos', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        emergencyTriggered = true;
        emergencyBanner.classList.remove('hidden');
        scoreProgress.className = 'progress-bar danger-bg';
        scoreProgress.style.width = '100%';
        triggersDisplay.textContent = 'Keywords detected: Manual SOS Button Trigger';
        triggersDisplay.style.color = 'var(--danger-color)';

        setTimeout(() => updateSystemStatus('danger', 'Sending alert notification'), 1000);
        setTimeout(() => updateSystemStatus('danger', 'Alert notification sent successfully'), 2500);
    } catch (err) {
        console.error("SOS failed:", err);
        updateSystemStatus('danger', 'Failed to send alert');
    } finally {
        sosBtn.innerHTML = '<i class="fa-solid fa-bell"></i> <span>SOS</span>';
    }
}

async function submitIncidentReport() {
    const btn = document.getElementById('submit-incident-btn');
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Submitting...';

    const category = document.getElementById('incident-category').value;
    const desc = document.getElementById('incident-description').value;
    const payload = { category: category, description: desc, location: 'Unknown' };

    try {
        if (navigator.geolocation) {
            const pos = await new Promise((res, rej) => navigator.geolocation.getCurrentPosition(res, rej));
            payload.location = `${pos.coords.latitude.toFixed(4)}, ${pos.coords.longitude.toFixed(4)}`;
        }
    } catch (e) { }

    try {
        await fetch('/api/report', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        document.getElementById('incident-description').value = '';
        document.getElementById('incident-loc-status').textContent = 'Incident Saved Successfully';
    } finally {
        btn.innerHTML = '<i class="fa-solid fa-paper-plane"></i> Submit Report';
    }
}

async function toggleListening() {
    if (emergencyTriggered) {
        location.reload();
        return;
    }
    appendTranscript("Safety assistant is actively listening. Speak keywords like 'Help' or 'Emergency' to trigger alert.", true);
}

function showPushNotification() {
    const push = document.getElementById('push-notification');
    if (push) {
        push.classList.remove('hidden');
        setTimeout(() => {
            push.classList.add('hidden');
        }, 10000); // Show for 10 seconds
    }
}
