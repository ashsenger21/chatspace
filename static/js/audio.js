/**
 * audio.js – Voice Message Recording
 *
 * Uses the browser's MediaRecorder API to:
 *   1. Request microphone permission
 *   2. Record audio while the user holds/clicks the mic button
 *   3. Show a live recording timer
 *   4. Let the user preview and send the recording
 *   5. Upload the audio file and notify via WebSocket
 *
 * The MediaRecorder API is supported in all modern browsers.
 * It records in the browser's preferred codec (usually webm/opus).
 */

"use strict";

// ─── Recording State ─────────────────────────────────────────
let mediaRecorder   = null;   // The MediaRecorder instance
let recordedChunks  = [];     // Audio data chunks collected during recording
let recordingStream = null;   // The microphone MediaStream
let recordingTimer  = null;   // Interval that updates the timer display
let recordingSeconds = 0;     // How many seconds have been recorded

// ─── Start Recording ─────────────────────────────────────────
async function startRecording() {
    // Don't start if we're already recording
    if (mediaRecorder && mediaRecorder.state === "recording") return;

    // Don't record if no conversation is open
    if (!currentConvId) {
        showToast("Please open a conversation first.", "error");
        return;
    }

    try {
        // Ask the browser for microphone access
        // If the user denies, we catch the error below and show a helpful message
        recordingStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });

    } catch (error) {
        // Common errors:
        //   NotAllowedError  – user denied microphone permission
        //   NotFoundError    – no microphone found
        if (error.name === "NotAllowedError" || error.name === "PermissionDeniedError") {
            showToast("⚠️ Microphone access denied. Please allow it in browser settings.", "error");
        } else if (error.name === "NotFoundError") {
            showToast("⚠️ No microphone found on this device.", "error");
        } else {
            showToast(`⚠️ Could not access microphone: ${error.message}`, "error");
        }
        return;
    }

    // Determine the best supported MIME type for audio recording
    // webm is widely supported; fall back to ogg or basic audio
    const mimeType = getSupportedMimeType();
    const options  = mimeType ? { mimeType } : {};

    recordedChunks = [];
    mediaRecorder  = new MediaRecorder(recordingStream, options);

    // Each time the MediaRecorder has data ready, store it
    mediaRecorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
            recordedChunks.push(event.data);
        }
    };

    // When recording stops, we get all the data assembled
    mediaRecorder.onstop = handleRecordingStop;

    // Start recording – request data every 250ms so we have chunks
    mediaRecorder.start(250);

    // Show the recording UI
    showRecordingUI();

    // Start the timer
    recordingSeconds = 0;
    updateTimerDisplay();
    recordingTimer = setInterval(() => {
        recordingSeconds++;
        updateTimerDisplay();

        // Auto-stop after 5 minutes to prevent gigantic files
        if (recordingSeconds >= 300) {
            stopAndSendRecording();
        }
    }, 1000);

    console.log("🎙️ Recording started with MIME type:", mimeType || "default");
}

// ─── Stop and Send ───────────────────────────────────────────
function stopAndSendRecording() {
    if (!mediaRecorder || mediaRecorder.state === "inactive") return;

    // This triggers the 'onstop' event handler above
    mediaRecorder.stop();

    // Stop the microphone stream so the browser stops showing the recording indicator
    if (recordingStream) {
        recordingStream.getTracks().forEach(track => track.stop());
        recordingStream = null;
    }

    clearInterval(recordingTimer);
    hideRecordingUI();
}

// ─── Cancel Recording ────────────────────────────────────────
function cancelRecording() {
    if (mediaRecorder && mediaRecorder.state !== "inactive") {
        // Remove the onstop handler so the audio isn't sent
        mediaRecorder.onstop = null;
        mediaRecorder.stop();
    }

    if (recordingStream) {
        recordingStream.getTracks().forEach(track => track.stop());
        recordingStream = null;
    }

    clearInterval(recordingTimer);
    recordedChunks = [];
    hideRecordingUI();
    showToast("Recording cancelled.");
}

// ─── Handle Recording Finished ───────────────────────────────
async function handleRecordingStop() {
    if (recordedChunks.length === 0) {
        showToast("No audio recorded.", "error");
        return;
    }

    // Combine all chunks into a single Blob (binary file)
    const mimeType  = getSupportedMimeType() || "audio/webm";
    const audioBlob = new Blob(recordedChunks, { type: mimeType });
    recordedChunks  = [];

    // Generate a file extension from the MIME type
    const ext      = mimeType.split(";")[0].split("/")[1] || "webm";
    const filename = `voice_${Date.now()}.${ext}`;

    // Sanity check: don't upload empty or suspiciously small files
    if (audioBlob.size < 1000) {
        showToast("Recording too short to send.", "error");
        return;
    }

    // Upload the audio
    await uploadAudio(audioBlob, filename);
}

// ─── Upload Audio File ───────────────────────────────────────
async function uploadAudio(blob, filename) {
    if (!currentConvId) return;

    showToast("Sending voice message…");

    const formData = new FormData();
    formData.append("file", blob, filename);
    formData.append("type", "audio");

    try {
        const res = await fetch(`/api/conversation/${currentConvId}/send_media`, {
            method: "POST",
            body:   formData
        });

        if (!res.ok) {
            const err = await res.json();
            showToast(err.error || "Failed to send voice message.", "error");
            return;
        }

        const msg = await res.json();

        // Broadcast via WebSocket so the recipient sees it immediately
        if (socket) {
            socket.emit("media_sent", {
                message_id:      msg.id,
                conversation_id: currentConvId
            });
        }

        showToast("Voice message sent!", "success");
    } catch (e) {
        showToast("Failed to upload voice message.", "error");
        console.error("Voice upload error:", e);
    }
}

// ─── UI Helpers ──────────────────────────────────────────────
function showRecordingUI() {
    document.getElementById("recordingUI").style.display  = "flex";
    document.getElementById("composerRow").style.display  = "none";
}

function hideRecordingUI() {
    document.getElementById("recordingUI").style.display  = "none";
    document.getElementById("composerRow").style.display  = "flex";
}

function updateTimerDisplay() {
    const minutes = Math.floor(recordingSeconds / 60);
    const seconds = recordingSeconds % 60;
    const display = `${minutes}:${seconds.toString().padStart(2, "0")}`;
    const el      = document.getElementById("recordingTimer");
    if (el) el.textContent = display;
}

// ─── MIME Type Detection ─────────────────────────────────────
/**
 * Pick the best audio MIME type supported by this browser.
 * webm/opus is preferred (Chrome, Firefox, Edge).
 * ogg/opus works in Firefox.
 * audio/mp4 works in Safari.
 */
function getSupportedMimeType() {
    const types = [
        "audio/webm;codecs=opus",
        "audio/webm",
        "audio/ogg;codecs=opus",
        "audio/ogg",
        "audio/mp4",
    ];

    for (const type of types) {
        if (MediaRecorder.isTypeSupported(type)) {
            return type;
        }
    }

    return "";  // Let the browser decide
}
