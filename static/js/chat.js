/**
 * chat.js – Real-Time Chat Logic
 *
 * This file handles:
 *  - WebSocket (SocketIO) connection and all real-time events
 *  - Opening conversations and loading messages
 *  - Rendering message bubbles (text, image, video, audio)
 *  - Sending text messages via WebSocket
 *  - Uploading and sending media (image/video/audio) via HTTP + WebSocket
 *  - Typing indicator (send and receive)
 *  - Online/offline status updates
 *  - In-chat message search
 *  - Infinite scroll (load older messages)
 */

"use strict";

// ─── State ──────────────────────────────────────────────────
let socket          = null;   // The SocketIO connection object
let currentConvId   = null;   // ID of the open conversation
let currentOtherUser = null;  // The other user in the active chat
let typingTimer     = null;   // Debounce timer for typing events
let isTyping        = false;  // Are we currently sending "typing" events?
let oldestMsgId     = null;   // For pagination (load older messages)
let hasMoreMessages = false;  // Whether there are older messages to load
let pendingMedia    = null;   // { file, type } waiting to be sent
let activeReply     = null;   // Currently active reply target { id, sender_username, text, type }

// ─── WebSocket Initialisation ────────────────────────────────
/**
 * Connect to the Flask-SocketIO server.
 * SocketIO automatically handles reconnections.
 */
function initSocket() {
    // Connect to same host (no URL needed when served from Flask)
    socket = io({ transports: ["websocket", "polling"] });

    // ── Connection events ──────────────────────────────────
    socket.on("connect", () => {
        console.log("✅ WebSocket connected:", socket.id);
        // Re-join current conversation room if we were in one
        if (currentConvId) {
            socket.emit("join_conversation", { conversation_id: currentConvId });
        }
    });

    socket.on("disconnect", () => {
        console.log("❌ WebSocket disconnected.");
    });

    socket.on("connect_error", (err) => {
        console.error("WebSocket connection error:", err);
        showToast("Real-time connection failed. Messages may be delayed.", "error");
    });

    // ── Receive a new message ──────────────────────────────
    socket.on("new_message", (msg) => {
        // Only append if this message belongs to the currently open conversation
        if (msg.conversation_id === currentConvId) {
            appendMessage(msg);
            scrollToBottom();

            // If we received (not sent) this message, mark it read immediately
            if (msg.sender_id !== currentUser.id) {
                socket.emit("message_read", { conversation_id: currentConvId });
                fetch(`/api/conversation/${currentConvId}/read`, { method: "POST" });
            }
        }
        // Always refresh the sidebar conversation list to update preview + unread count
        loadConversations();
    });

    // ── Conversation sidebar update ────────────────────────
    socket.on("conversation_updated", () => {
        loadConversations();
    });

    // ── Typing indicator ───────────────────────────────────
    socket.on("typing_indicator", (data) => {
        if (data.conversation_id !== currentConvId) return;
        const indicator = document.getElementById("typingIndicator");
        const text      = document.getElementById("typingText");

        if (data.is_typing) {
            if (text) text.textContent = `${data.username} is typing…`;
            indicator.style.display = "flex";
        } else {
            indicator.style.display = "none";
        }
    });

    // ── Online / offline status ────────────────────────────
    socket.on("user_status", (data) => {
        // Update the chat header status if this is the person we're chatting with
        if (currentOtherUser && data.user_id === currentOtherUser.id) {
            updateChatHeaderStatus(data.is_online, data.last_seen);
        }

        // Update conversation list avatars
        const convItem = document.querySelector(`[data-user-id="${data.user_id}"] .avatar`);
        if (convItem) {
            convItem.classList.toggle("online", data.is_online);
        }
    });

    // ── Read receipts ──────────────────────────────────────
    socket.on("messages_read", (data) => {
        if (data.conversation_id === currentConvId) {
            // Update all sent message ticks to "read"
            document.querySelectorAll(".read-tick").forEach(el => {
                el.classList.add("read");
                el.textContent = "✓✓";
            });
        }
    });
}

// ─── Open Conversation ───────────────────────────────────────
async function openConversation(convId) {
    // Leave the old conversation room
    if (currentConvId && socket) {
        socket.emit("leave_conversation", { conversation_id: currentConvId });
    }

    currentConvId = convId;
    activeConvId  = convId;
    oldestMsgId   = null;
    hasMoreMessages = false;
    cancelReply();

    // Highlight in sidebar
    document.querySelectorAll(".conversation-item").forEach(el => {
        el.classList.toggle("active", parseInt(el.dataset.convId) === convId);
    });

    // On mobile: hide sidebar, show chat
    if (window.innerWidth <= 768) {
        document.getElementById("sidebar").classList.add("hidden");
    }

    // Show chat window
    document.getElementById("welcomeScreen").style.display = "none";
    document.getElementById("chatWindow").style.display    = "flex";

    // Immediate optimistic header update if already in memory
    const cached = conversations.find(c => c.id === convId);
    if (cached && cached.other_user) {
        currentOtherUser = cached.other_user;
        updateChatHeader(currentOtherUser);
    }

    // Clear messages
    const container = document.getElementById("messagesContainer");
    container.innerHTML = `<div style="text-align:center;padding:2rem"><div class="spinner"></div></div>`;

    // Load fresh conversation details
    try {
        const res  = await fetch(`/api/conversation/${convId}`);
        if (res.ok) {
            const data = await res.json();
            currentOtherUser = data.other_user;
            updateChatHeader(currentOtherUser);
        }
    } catch (e) {
        console.warn("Could not refresh conversation header:", e);
    }

    if (!currentOtherUser) {
        showToast("Failed to load conversation details.", "error");
    }

    // Join SocketIO room
    if (socket) {
        socket.emit("join_conversation", { conversation_id: convId });
    }

    // Load messages
    await loadMessages(convId);

    // Mark messages as read
    fetch(`/api/conversation/${convId}/read`, { method: "POST" });
    if (socket) socket.emit("message_read", { conversation_id: convId });

    // Focus composer
    const input = document.getElementById("messageInput");
    if (input) input.focus();
}

// ─── Update Chat Header ──────────────────────────────────────
function updateChatHeader(user) {
    if (!user) return;
    const imgEl   = document.getElementById("chatAvatarImg");
    const initEl  = document.getElementById("chatAvatarInitial");
    const wrapper = document.getElementById("chatAvatar");
    const nameEl  = document.getElementById("chatUsername");

    if (nameEl)    nameEl.textContent = user.username || "User";
    if (imgEl && initEl && wrapper) setAvatar(imgEl, initEl, user, wrapper);

    updateChatHeaderStatus(user.is_online, user.last_seen);
}

function updateChatHeaderStatus(isOnline, lastSeen) {
    const statusEl = document.getElementById("chatStatus");
    if (!statusEl) return;

    if (isOnline) {
        statusEl.textContent = "Online";
        statusEl.className   = "chat-status online";
    } else if (lastSeen) {
        statusEl.textContent = `Last seen ${formatLastSeen(lastSeen)}`;
        statusEl.className   = "chat-status";
    } else {
        statusEl.textContent = "Offline";
        statusEl.className   = "chat-status";
    }
}

// ─── Load Messages ───────────────────────────────────────────
async function loadMessages(convId, before = null) {
    try {
        let url = `/api/conversation/${convId}/messages?limit=50`;
        if (before) url += `&before=${before}`;

        const res      = await fetch(url);
        const messages = await res.json();

        const container = document.getElementById("messagesContainer");

        if (!before) {
            // First load — clear spinner and render fresh
            container.innerHTML = "";
            renderMessages(messages);
            scrollToBottom(false);
        } else {
            // Loading older — prepend to top, preserve scroll position
            const oldHeight = container.scrollHeight;
            renderMessages(messages, true);
            container.scrollTop = container.scrollHeight - oldHeight;
        }

        // Show "load more" button if we got a full page
        hasMoreMessages = messages.length >= 50;
        document.getElementById("loadMoreWrapper").style.display = hasMoreMessages ? "block" : "none";

        if (messages.length > 0) {
            oldestMsgId = messages[0].id;
        }
    } catch (e) {
        console.error("Failed to load messages:", e);
        showToast("Failed to load messages.", "error");
    }
}

function loadMoreMessages() {
    if (currentConvId && oldestMsgId) {
        loadMessages(currentConvId, oldestMsgId);
    }
}

// ─── Render Messages ─────────────────────────────────────────
function renderMessages(messages, prepend = false) {
    const container = document.getElementById("messagesContainer");
    let   lastDate  = null;
    const fragment  = document.createDocumentFragment();

    // If prepending, we need to insert before the load-more button
    const loadMoreWrapper = document.getElementById("loadMoreWrapper");

    messages.forEach(msg => {
        const msgDate = parseDate(msg.timestamp).toDateString();

        // Insert date separator when the date changes
        if (msgDate !== lastDate) {
            const sep = document.createElement("div");
            sep.className    = "date-separator";
            sep.dataset.date = msgDate;
            sep.innerHTML    = `<span>${formatDateLabel(msg.timestamp)}</span>`;
            fragment.appendChild(sep);
            lastDate = msgDate;
        }

        const wrapper = buildMessageElement(msg);
        fragment.appendChild(wrapper);
    });

    if (prepend) {
        container.insertBefore(fragment, loadMoreWrapper.nextSibling);
    } else {
        container.appendChild(fragment);
    }
}

// ─── Build a Single Message Element ─────────────────────────
function buildMessageElement(msg) {
    const isSent = msg.sender_id === currentUser.id;
    const wrapper = document.createElement("div");
    wrapper.className = `message-wrapper ${isSent ? "sent" : "received"}`;
    wrapper.dataset.msgId = msg.id;

    // Swipe reply indicator (animates behind bubble when sliding)
    const swipeIcon = document.createElement("div");
    swipeIcon.className = "swipe-reply-indicator";
    swipeIcon.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 17 4 12 9 7"/><path d="M20 18v-2a4 4 0 0 0-4-4H4"/></svg>`;
    wrapper.appendChild(swipeIcon);

    // Avatar (for received messages only)
    if (!isSent && currentOtherUser) {
        const color    = getAvatarColor(currentOtherUser.id);
        const avatarEl = document.createElement("div");
        avatarEl.className = "avatar avatar-sm";
        avatarEl.style.background = color;
        avatarEl.innerHTML = currentOtherUser.profile_picture
            ? `<img src="${currentOtherUser.profile_picture}" style="display:block;width:100%;height:100%;object-fit:cover">`
            : `<span style="color:white;font-size:0.75rem;font-weight:700">${(currentOtherUser.username || "?")[0].toUpperCase()}</span>`;
        wrapper.appendChild(avatarEl);
    }

    const bubble = document.createElement("div");
    bubble.className = "bubble";
    bubble.innerHTML = buildBubbleContent(msg, isSent);
    wrapper.appendChild(bubble);

    // Desktop hover reply button
    const replyBtn = document.createElement("button");
    replyBtn.className = "bubble-reply-btn";
    replyBtn.title = "Reply (or slide right)";
    replyBtn.setAttribute("aria-label", "Reply to message");
    replyBtn.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 17 4 12 9 7"/><path d="M20 18v-2a4 4 0 0 0-4-4H4"/></svg>`;
    replyBtn.onclick = (e) => {
        e.stopPropagation();
        setReplyTo(msg);
    };
    wrapper.appendChild(replyBtn);

    // Attach slide/swipe-to-reply gesture
    attachSwipeToReply(bubble, wrapper, msg);

    return wrapper;
}

function buildBubbleContent(msg, isSent) {
    let content = "";

    // Quoted reply message (if this message is a reply to another)
    let quotedHtml = "";
    if (msg.reply_to) {
        quotedHtml = `
            <div class="quoted-message" onclick="scrollToMessage(${msg.reply_to.id})">
                <div class="quoted-sender">${escapeHtml(msg.reply_to.sender_username)}</div>
                <div class="quoted-text">${escapeHtml(msg.reply_to.preview_text)}</div>
            </div>`;
    }

    if (msg.message_type === "text") {
        content = `<div class="bubble-text">${escapeHtml(msg.message_text)}</div>`;

    } else if (msg.message_type === "image") {
        content = `<img
            src="${msg.media_url}"
            class="chat-image"
            alt="Image"
            onclick="openLightbox('${msg.media_url}')"
            loading="lazy"
        >`;

    } else if (msg.message_type === "video") {
        content = `<video class="chat-video" controls preload="none">
            <source src="${msg.media_url}">
            Your browser does not support video.
        </video>`;

    } else if (msg.message_type === "audio") {
        // Custom voice message player
        const audioId = `audio_${msg.id}`;
        content = `
            <div class="voice-message">
                <button class="voice-play-btn" onclick="toggleVoice('${audioId}', this)" title="Play/Pause">
                    <svg viewBox="0 0 24 24" fill="currentColor">
                        <polygon points="5 3 19 12 5 21 5 3"/>
                    </svg>
                </button>
                <div class="voice-waveform" onclick="seekVoice('${audioId}', ${msg.id}, event)" style="cursor:pointer">
                    <div class="voice-waveform-progress" id="progress_${msg.id}"></div>
                </div>
                <span class="voice-duration" id="dur_${msg.id}">0:00</span>
                <audio id="${audioId}" src="${msg.media_url}" preload="metadata"
                    onloadedmetadata="initVoiceDuration('${audioId}', ${msg.id})"
                    onended="resetVoicePlayer('${audioId}', this)"
                    ontimeupdate="updateVoiceProgress('${audioId}', ${msg.id})"
                    onerror="handleVoiceError('${audioId}', ${msg.id})">
                </audio>
            </div>`;
    }

    // Prepend quoted reply above the main content
    content = quotedHtml + content;

    // Timestamp and read ticks
    const tick = isSent
        ? `<span class="read-tick ${msg.is_read ? "read" : ""}">✓✓</span>`
        : "";

    content += `
        <div class="bubble-meta">
            <span class="bubble-time">${formatFullTime(msg.timestamp)}</span>
            ${tick}
        </div>`;

    return content;
}

// ─── Voice Player Helpers ────────────────────────────────────
function toggleVoice(audioId, btn) {
    const audio = document.getElementById(audioId);
    if (!audio) return;

    if (audio.paused) {
        // Pause any other playing audio
        document.querySelectorAll("audio").forEach(a => {
            if (a.id !== audioId && !a.paused) {
                a.pause();
                const otherBtn = document.querySelector(`button[onclick*="${a.id}"]`);
                if (otherBtn) setPlayIcon(otherBtn);
            }
        });

        const playPromise = audio.play();
        if (playPromise !== undefined) {
            playPromise.then(() => {
                setPauseIcon(btn);
            }).catch(err => {
                console.error("Audio playback error:", err);
                setPlayIcon(btn);
                showToast("Could not play audio: " + (err.message || "playback error"), "error");
            });
        }
    } else {
        audio.pause();
        setPlayIcon(btn);
    }
}

function initVoiceDuration(audioId, msgId) {
    const audio = document.getElementById(audioId);
    const durEl = document.getElementById(`dur_${msgId}`);
    if (audio && durEl && !isNaN(audio.duration) && isFinite(audio.duration)) {
        durEl.textContent = formatDuration(audio.duration);
    }
}

function handleVoiceError(audioId, msgId) {
    const durEl = document.getElementById(`dur_${msgId}`);
    if (durEl) durEl.textContent = "Error";
    console.warn(`Voice audio ${audioId} failed to load from source`);
}

function seekVoice(audioId, msgId, event) {
    const audio = document.getElementById(audioId);
    const waveform = event.currentTarget;
    if (!audio || !waveform || isNaN(audio.duration) || !isFinite(audio.duration)) return;

    const rect = waveform.getBoundingClientRect();
    const clickX = event.clientX - rect.left;
    const pct = Math.max(0, Math.min(1, clickX / rect.width));
    audio.currentTime = pct * audio.duration;
    updateVoiceProgress(audioId, msgId);
}

function setPlayIcon(btn) {
    btn.innerHTML = `<svg viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>`;
}

function setPauseIcon(btn) {
    btn.innerHTML = `<svg viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>`;
}

function resetVoicePlayer(audioId, audio) {
    const btn = document.querySelector(`button[onclick*="${audioId}"]`);
    if (btn) setPlayIcon(btn);
    const msgId = audioId.replace("audio_", "");
    const progress = document.getElementById(`progress_${msgId}`);
    if (progress) progress.style.width = "0%";
    const audioEl = document.getElementById(audioId);
    const durEl = document.getElementById(`dur_${msgId}`);
    if (durEl && audioEl && !isNaN(audioEl.duration) && isFinite(audioEl.duration)) {
        durEl.textContent = formatDuration(audioEl.duration);
    } else if (durEl) {
        durEl.textContent = "0:00";
    }
}

function updateVoiceProgress(audioId, msgId) {
    const audio    = document.getElementById(audioId);
    const progress = document.getElementById(`progress_${msgId}`);
    const durEl    = document.getElementById(`dur_${msgId}`);
    if (!audio || !progress) return;

    const pct = (audio.duration && !isNaN(audio.duration) && isFinite(audio.duration))
        ? (audio.currentTime / audio.duration) * 100
        : 0;
    progress.style.width = pct + "%";

    if (durEl) {
        durEl.textContent = formatDuration(audio.currentTime);
    }
}

function formatDuration(seconds) {
    if (isNaN(seconds)) return "0:00";
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m}:${s.toString().padStart(2, "0")}`;
}

// ─── Swipe & Quoted Reply Helpers ──────────────────────────
function setReplyTo(msg) {
    if (!msg) return;

    let senderName = msg.sender_username;
    if (msg.sender_id === currentUser.id) {
        senderName = "You";
    } else if (currentOtherUser && msg.sender_id === currentOtherUser.id) {
        senderName = currentOtherUser.username;
    }
    senderName = senderName || "User";

    let preview = msg.message_text;
    if (msg.message_type === "image") preview = "📷 Photo";
    else if (msg.message_type === "video") preview = "🎬 Video";
    else if (msg.message_type === "audio") preview = "🎙️ Voice message";
    else if (!preview) preview = "Attachment";

    activeReply = {
        id: msg.id,
        sender_username: senderName,
        text: preview,
        type: msg.message_type
    };

    const bar = document.getElementById("replyPreviewBar");
    const senderEl = document.getElementById("replyPreviewSender");
    const textEl = document.getElementById("replyPreviewText");

    if (senderEl) senderEl.textContent = `Replying to ${senderName}`;
    if (textEl) textEl.textContent = (preview && preview.length > 80) ? preview.slice(0, 80) + "…" : (preview || "");
    if (bar) bar.style.display = "flex";

    const input = document.getElementById("messageInput");
    if (input) input.focus();
}

function cancelReply() {
    activeReply = null;
    const bar = document.getElementById("replyPreviewBar");
    if (bar) bar.style.display = "none";
}

function scrollToMessage(msgId) {
    if (!msgId) return;
    const targetWrapper = document.querySelector(`[data-msg-id="${msgId}"]`);
    if (!targetWrapper) {
        showToast("Original message not loaded in view", "info");
        return;
    }

    targetWrapper.scrollIntoView({ behavior: "smooth", block: "center" });
    const bubble = targetWrapper.querySelector(".bubble");
    if (bubble) {
        bubble.classList.remove("highlight-pulse");
        void bubble.offsetWidth; // Force CSS reflow to re-trigger keyframe
        bubble.classList.add("highlight-pulse");
        setTimeout(() => {
            bubble.classList.remove("highlight-pulse");
        }, 1600);
    }
}

function attachSwipeToReply(bubble, wrapper, msg) {
    if (!bubble || !wrapper) return;

    const indicator = wrapper.querySelector(".swipe-reply-indicator");
    let startX = 0;
    let startY = 0;
    let currentX = 0;
    let isDragging = false;
    let isHorizontal = null;
    let hasVibrated = false;
    const threshold = 55;
    const maxDrag   = 85;

    function onPointerDown(e) {
        if (e.pointerType === "mouse" && e.button !== 0) return;
        // Don't intercept clicks on buttons, links, video, audio, or lightbox trigger
        if (e.target.closest("button, a, video, audio, .quoted-message, .chat-image")) return;

        startX = e.clientX;
        startY = e.clientY;
        currentX = 0;
        isDragging = false;
        isHorizontal = null;
        hasVibrated = false;

        bubble.addEventListener("pointermove", onPointerMove);
        bubble.addEventListener("pointerup", onPointerUp);
        bubble.addEventListener("pointercancel", onPointerUp);
    }

    function onPointerMove(e) {
        const deltaX = e.clientX - startX;
        const deltaY = e.clientY - startY;

        if (isHorizontal === null) {
            const absX = Math.abs(deltaX);
            const absY = Math.abs(deltaY);
            if (absX > 8 || absY > 8) {
                // If moving horizontally to the right:
                if (absX > absY && deltaX > 0) {
                    isHorizontal = true;
                    isDragging = true;
                    bubble.style.touchAction = "none";
                    try { bubble.setPointerCapture(e.pointerId); } catch (_) {}
                } else {
                    isHorizontal = false;
                    cleanup(e);
                    return;
                }
            } else {
                return;
            }
        }

        if (!isHorizontal || !isDragging) return;

        const clampedDeltaX = Math.max(0, deltaX);
        currentX = Math.min(maxDrag, clampedDeltaX * 0.75);

        bubble.style.transition = "none";
        bubble.style.transform = `translateX(${currentX}px)`;

        if (indicator) {
            const progress = Math.min(1, currentX / threshold);
            indicator.style.opacity = progress;
            indicator.style.transform = `translateY(-50%) scale(${0.6 + progress * 0.4})`;

            const bubbleLeft = bubble.offsetLeft;
            indicator.style.left = `${bubbleLeft + (currentX - 28) / 2}px`;

            if (currentX >= threshold) {
                if (!indicator.classList.contains("ready")) {
                    indicator.classList.add("ready");
                    if (!hasVibrated && navigator.vibrate) {
                        try { navigator.vibrate(25); } catch (_) {}
                        hasVibrated = true;
                    }
                }
            } else {
                indicator.classList.remove("ready");
                hasVibrated = false;
            }
        }
    }

    function onPointerUp(e) {
        if (isDragging && isHorizontal) {
            bubble.style.transition = "transform 0.25s cubic-bezier(0.175, 0.885, 0.32, 1.275)";
            bubble.style.transform = "";

            if (indicator) {
                const wasReady = indicator.classList.contains("ready");
                indicator.style.transition = "opacity 0.2s, transform 0.2s";
                indicator.style.opacity = "0";
                indicator.style.transform = "translateY(-50%) scale(0.6)";
                indicator.classList.remove("ready");

                if (wasReady) {
                    setReplyTo(msg);
                }
            }
        }

        cleanup(e);
    }

    function cleanup(e) {
        if (e && e.pointerId) {
            try { bubble.releasePointerCapture(e.pointerId); } catch (_) {}
        }
        bubble.style.touchAction = "";
        bubble.removeEventListener("pointermove", onPointerMove);
        bubble.removeEventListener("pointerup", onPointerUp);
        bubble.removeEventListener("pointercancel", onPointerUp);
        isDragging = false;
        isHorizontal = null;
    }

    bubble.addEventListener("pointerdown", onPointerDown);
}

// ─── Append a Single New Message ────────────────────────────
function appendMessage(msg) {
    const container = document.getElementById("messagesContainer");
    const wrapper   = buildMessageElement(msg);

    // Check if we need a date separator
    const lastSep = container.querySelector(".date-separator:last-of-type");
    const msgDate = parseDate(msg.timestamp).toDateString();
    const lastDate = lastSep ? lastSep.dataset.date : null;

    if (msgDate !== lastDate) {
        const sep = document.createElement("div");
        sep.className    = "date-separator";
        sep.dataset.date = msgDate;
        sep.innerHTML    = `<span>${formatDateLabel(msg.timestamp)}</span>`;
        container.appendChild(sep);
    }

    container.appendChild(wrapper);
}

// ─── Scroll to Bottom ────────────────────────────────────────
function scrollToBottom(smooth = true) {
    const container = document.getElementById("messagesContainer");
    if (!container) return;
    container.scrollTo({
        top:      container.scrollHeight,
        behavior: smooth ? "smooth" : "auto"
    });
}

// ─── Send Text Message ───────────────────────────────────────
function sendTextMessage() {
    const input = document.getElementById("messageInput");
    const text  = input.value.trim();

    if (!text || !currentConvId || !socket) return;

    // Emit via WebSocket (server saves + broadcasts)
    socket.emit("send_message", {
        conversation_id: currentConvId,
        text:            text,
        reply_to_id:     activeReply ? activeReply.id : null
    });

    // Clear input
    input.value = "";
    autoResize(input);
    input.focus();
    cancelReply();

    // Stop typing indicator
    stopTyping();
}

// ─── Handle Key Events in Textarea ──────────────────────────
function handleKeyDown(event) {
    if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        sendTextMessage();
    }
    autoResize(event.target);
}

// ─── Typing Indicator ────────────────────────────────────────
function handleTyping() {
    autoResize(document.getElementById("messageInput"));

    if (!socket || !currentConvId) return;

    // Emit "typing start" only once until debounce fires
    if (!isTyping) {
        isTyping = true;
        socket.emit("typing", { conversation_id: currentConvId, is_typing: true });
    }

    clearTimeout(typingTimer);
    typingTimer = setTimeout(stopTyping, 2000);
}

function stopTyping() {
    if (isTyping && socket && currentConvId) {
        isTyping = false;
        socket.emit("typing", { conversation_id: currentConvId, is_typing: false });
    }
    clearTimeout(typingTimer);
}

// ─── File Attachment ─────────────────────────────────────────
function handleFileSelect(input) {
    if (!input.files.length) return;
    const file = input.files[0];

    // Determine media type
    const ext  = file.name.split(".").pop().toLowerCase();
    const imageExts = ["jpg","jpeg","png","gif","webp"];
    const videoExts = ["mp4","webm","mov"];
    const audioExts = ["mp3","wav","ogg","m4a","webm"];

    let mediaType = null;
    if (imageExts.includes(ext))  mediaType = "image";
    else if (videoExts.includes(ext)) mediaType = "video";
    else if (audioExts.includes(ext)) mediaType = "audio";

    if (!mediaType) {
        showToast("Unsupported file type.", "error");
        input.value = "";
        return;
    }

    // File size check (100MB)
    if (file.size > 100 * 1024 * 1024) {
        showToast("File is too large. Maximum size is 100MB.", "error");
        input.value = "";
        return;
    }

    pendingMedia = { file, type: mediaType };
    showMediaPreview(file, mediaType);
    input.value = "";
}

function showMediaPreview(file, type) {
    const preview     = document.getElementById("mediaPreview");
    const content     = document.getElementById("previewContent");
    preview.style.display = "flex";

    const objectURL = URL.createObjectURL(file);

    if (type === "image") {
        content.innerHTML = `<img src="${objectURL}" alt="Preview">`;
    } else if (type === "video") {
        content.innerHTML = `<video src="${objectURL}" controls style="max-height:120px;border-radius:8px"></video>`;
    } else if (type === "audio") {
        content.innerHTML = `<audio src="${objectURL}" controls style="max-width:200px"></audio>`;
    }

    // Add a send button in the preview
    const sendBtn = document.createElement("button");
    sendBtn.textContent = "📤 Send";
    sendBtn.style.cssText = "background:var(--accent);color:white;border:none;border-radius:20px;padding:0.4rem 1rem;cursor:pointer;font-weight:600;margin-left:auto;";
    sendBtn.onclick = sendMediaMessage;
    content.appendChild(sendBtn);
}

function cancelMediaPreview() {
    document.getElementById("mediaPreview").style.display = "none";
    document.getElementById("previewContent").innerHTML   = "";
    pendingMedia = null;
}

async function sendMediaMessage() {
    if (!pendingMedia || !currentConvId) return;

    const { file, type } = pendingMedia;
    const formData = new FormData();
    formData.append("file", file);
    formData.append("type", type);
    if (activeReply) formData.append("reply_to_id", activeReply.id);

    // Disable preview buttons while uploading
    showToast("Uploading…");

    try {
        const res  = await fetch(`/api/conversation/${currentConvId}/send_media`, {
            method: "POST",
            body:   formData
        });

        if (!res.ok) {
            const err = await res.json();
            showToast(err.error || "Upload failed.", "error");
            return;
        }

        const msg = await res.json();

        // Notify other user via WebSocket
        if (socket) {
            socket.emit("media_sent", {
                message_id:      msg.id,
                conversation_id: currentConvId
            });
        }

        cancelMediaPreview();
        cancelReply();
        showToast("Sent!", "success");
    } catch (e) {
        showToast("Failed to send media.", "error");
    }
}

// ─── In-Chat Search ──────────────────────────────────────────
function toggleChatSearch() {
    const bar = document.getElementById("chatSearchBar");
    const isVisible = bar.style.display !== "none";
    bar.style.display = isVisible ? "none" : "flex";
    if (!isVisible) document.getElementById("chatSearchInput").focus();
}

function closeChatSearch() {
    document.getElementById("chatSearchBar").style.display = "none";
    document.getElementById("chatSearchInput").value = "";
    // Clear any highlights
    document.querySelectorAll(".bubble-text").forEach(el => {
        el.innerHTML = escapeHtml(el.textContent);
    });
}

let chatSearchTimer = null;

async function searchChatMessages(query) {
    clearTimeout(chatSearchTimer);

    if (!query.trim()) {
        // Remove highlights
        document.querySelectorAll(".bubble-text").forEach(el => {
            el.textContent = el.textContent;
        });
        return;
    }

    chatSearchTimer = setTimeout(async () => {
        try {
            const res  = await fetch(`/api/conversation/${currentConvId}/search?q=${encodeURIComponent(query)}`);
            const msgs = await res.json();

            // Scroll to first result if exists
            if (msgs.length > 0) {
                const firstEl = document.querySelector(`[data-msg-id="${msgs[0].id}"]`);
                if (firstEl) firstEl.scrollIntoView({ behavior: "smooth", block: "center" });
            }

            // Highlight matching text in visible bubbles
            highlightSearchTerms(query);
        } catch (e) {
            console.error("Search failed:", e);
        }
    }, 400);
}

function highlightSearchTerms(query) {
    const escapedQuery = query.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const regex = new RegExp(`(${escapedQuery})`, "gi");

    document.querySelectorAll(".bubble-text").forEach(el => {
        const original = el.textContent;
        el.innerHTML   = escapeHtml(original).replace(
            new RegExp(`(${escapeHtml(query).replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})`, "gi"),
            `<mark class="search-highlight">$1</mark>`
        );
    });
}

// ─── Initialise ─────────────────────────────────────────────
// This runs after app.js has already called init()
window.addEventListener("DOMContentLoaded", () => {
    initSocket();
});
