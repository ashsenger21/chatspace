/**
 * app.js – ChatSpace Application Core
 *
 * This file handles:
 *  - Theme management (dark/light)
 *  - Current user data
 *  - Conversation list loading and rendering
 *  - Searching users and conversations
 *  - Starting new chats
 *  - Toast notifications
 *  - Avatar generation (initials + color)
 *  - Profile modal
 */

"use strict";

// ─── Global State ───────────────────────────────────────────
let currentUser    = null;   // Logged-in user object
let conversations  = [];     // All loaded conversations
let activeConvId   = null;   // Currently open conversation ID

// ─── Avatar Colors (deterministic by user ID) ───────────────
const AVATAR_COLORS = [
    "#25D366", "#128C7E", "#075E54", "#34B7F1",
    "#9C27B0", "#FF5722", "#2196F3", "#FF9800",
    "#E91E63", "#009688", "#795548", "#607D8B"
];

function getAvatarColor(userId) {
    return AVATAR_COLORS[userId % AVATAR_COLORS.length];
}

// ─── Theme ──────────────────────────────────────────────────
function toggleTheme() {
    const html     = document.documentElement;
    const isDark   = html.getAttribute("data-theme") === "dark";
    const newTheme = isDark ? "light" : "dark";
    html.setAttribute("data-theme", newTheme);
    localStorage.setItem("theme", newTheme);
    updateThemeIcon();
}

function updateThemeIcon() {
    const isDark = document.documentElement.getAttribute("data-theme") === "dark";
    const btn    = document.getElementById("themeBtn");
    if (!btn) return;
    btn.innerHTML = isDark
        ? `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
             <circle cx="12" cy="12" r="5"/>
             <line x1="12" y1="1" x2="12" y2="3"/>
             <line x1="12" y1="21" x2="12" y2="23"/>
             <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/>
             <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/>
             <line x1="1" y1="12" x2="3" y2="12"/>
             <line x1="21" y1="12" x2="23" y2="12"/>
             <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/>
             <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
           </svg>`
        : `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
             <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
           </svg>`;
}

// ─── Toast Notifications ────────────────────────────────────
/**
 * Show a brief toast message at the bottom of the screen.
 * @param {string} message
 * @param {'success'|'error'|''} type
 * @param {number} duration milliseconds
 */
function showToast(message, type = "", duration = 3000) {
    const container = document.getElementById("toastContainer");
    if (!container) return;

    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    toast.textContent = message;
    container.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = "0";
        toast.style.transform = "translateY(12px)";
        toast.style.transition = "0.3s";
        setTimeout(() => toast.remove(), 300);
    }, duration);
}

// ─── Avatar Rendering ───────────────────────────────────────
/**
 * Set an avatar element to show either a profile picture or initials.
 * @param {HTMLElement} imgEl   - The <img> element inside the avatar
 * @param {HTMLElement} initEl  - The <span> that shows initials
 * @param {object}      user    - User object with username, id, profile_picture
 * @param {HTMLElement} [wrapper] - The outer .avatar div (for color)
 */
function setAvatar(imgEl, initEl, user, wrapper) {
    const color = getAvatarColor(user.id);
    if (wrapper) wrapper.style.background = color;

    if (user.profile_picture) {
        imgEl.src         = user.profile_picture;
        imgEl.style.display = "block";
        if (initEl) initEl.style.display = "none";
    } else {
        imgEl.style.display = "none";
        if (initEl) {
            initEl.style.display = "block";
            initEl.textContent   = user.username[0].toUpperCase();
        }
    }
}

// ─── Load Current User ──────────────────────────────────────
async function loadCurrentUser() {
    try {
        const res  = await fetch("/api/me");
        if (!res.ok) { window.location.href = "/login"; return; }
        currentUser = await res.json();

        // Update sidebar header
        const imgEl  = document.getElementById("sidebarAvatarImg");
        const initEl = document.getElementById("sidebarAvatarInitial");
        const wrapper = document.getElementById("sidebarAvatar");
        const nameEl = document.getElementById("sidebarUsername");

        if (nameEl) nameEl.textContent = currentUser.username;
        if (imgEl && initEl && wrapper) setAvatar(imgEl, initEl, currentUser, wrapper);
    } catch (e) {
        console.error("Failed to load user:", e);
    }
}

// ─── Load Conversations ─────────────────────────────────────
async function loadConversations() {
    try {
        const res    = await fetch("/api/conversations");
        conversations = await res.json();
        renderConversationList(conversations);
    } catch (e) {
        console.error("Failed to load conversations:", e);
    }
}

// ─── Render Conversation List ───────────────────────────────
function renderConversationList(list) {
    const container = document.getElementById("conversationList");
    if (!container) return;

    if (list.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
                </svg>
                <p>No conversations yet.<br>Click the compose button to start one!</p>
            </div>`;
        return;
    }

    container.innerHTML = list.map(conv => buildConvItemHTML(conv)).join("");

    // Re-highlight active conversation
    if (activeConvId) {
        const active = container.querySelector(`[data-conv-id="${activeConvId}"]`);
        if (active) active.classList.add("active");
    }
}

function buildConvItemHTML(conv) {
    const user   = conv.other_user;
    const color  = getAvatarColor(user.id);
    const time   = conv.last_message ? formatTime(conv.last_message.timestamp) : "";
    const unread = conv.unread_count > 0 ? `<span class="unread-badge">${conv.unread_count}</span>` : "";

    let preview = "No messages yet";
    if (conv.last_message) {
        const type = conv.last_message.message_type;
        if (type === "text")  preview = escapeHtml(conv.last_message.message_text || "");
        if (type === "image") preview = "📷 Photo";
        if (type === "video") preview = "🎬 Video";
        if (type === "audio") preview = "🎙️ Voice message";
    }

    const avatarContent = user.profile_picture
        ? `<img src="${user.profile_picture}" alt="" style="display:block;width:100%;height:100%;object-fit:cover;">`
        : `<span style="font-weight:700;color:white">${user.username[0].toUpperCase()}</span>`;

    return `
        <div class="conversation-item"
             data-conv-id="${conv.id}"
             data-user-id="${user.id}"
             onclick="openConversation(${conv.id})">
            <div class="avatar avatar-md" style="background:${color}">
                ${avatarContent}
            </div>
            <div class="conv-content">
                <div class="conv-header">
                    <span class="conv-username">${escapeHtml(user.username)}</span>
                    <span class="conv-time">${time}</span>
                </div>
                <div class="conv-preview">
                    <span class="conv-last-msg">${preview}</span>
                    ${unread}
                </div>
            </div>
        </div>`;
}

// ─── Sidebar Search ─────────────────────────────────────────
function handleSidebarSearch(query) {
    const clearBtn = document.getElementById("clearSearch");
    if (clearBtn) clearBtn.style.display = query ? "block" : "none";

    if (!query.trim()) {
        renderConversationList(conversations);
        return;
    }
    const lower    = query.toLowerCase();
    const filtered = conversations.filter(c =>
        c.other_user.username.toLowerCase().includes(lower)
    );
    renderConversationList(filtered);
}

function clearSidebarSearch() {
    const input = document.getElementById("sidebarSearch");
    if (input) { input.value = ""; }
    document.getElementById("clearSearch").style.display = "none";
    renderConversationList(conversations);
}

// ─── New Chat ────────────────────────────────────────────────
function openNewChat() {
    document.getElementById("newChatPanel").style.display = "flex";
    document.getElementById("conversationList").style.display = "none";
    document.getElementById("userSearch").focus();
}

function closeNewChat() {
    document.getElementById("newChatPanel").style.display = "none";
    document.getElementById("conversationList").style.display = "block";
    document.getElementById("userSearch").value = "";
    document.getElementById("userSearchResults").innerHTML = "";
}

let userSearchTimer = null;

async function searchUsers(query) {
    clearTimeout(userSearchTimer);
    const results = document.getElementById("userSearchResults");

    if (!query.trim()) {
        results.innerHTML = "";
        return;
    }

    results.innerHTML = `<div style="text-align:center;padding:1rem"><div class="spinner"></div></div>`;

    userSearchTimer = setTimeout(async () => {
        try {
            const res  = await fetch(`/api/users/search?q=${encodeURIComponent(query)}`);
            const users = await res.json();

            if (users.length === 0) {
                results.innerHTML = `<div class="empty-state" style="padding:1.5rem">
                    <p>No users found for "${escapeHtml(query)}"</p>
                </div>`;
                return;
            }

            results.innerHTML = users.map(u => {
                const color  = getAvatarColor(u.id);
                const avatar = u.profile_picture
                    ? `<img src="${u.profile_picture}" style="display:block;width:100%;height:100%;object-fit:cover">`
                    : `<span style="color:white;font-weight:700">${u.username[0].toUpperCase()}</span>`;
                return `
                    <div class="user-result-item" onclick="startChat(${u.id})">
                        <div class="avatar avatar-md" style="background:${color}">${avatar}</div>
                        <div>
                            <div style="font-weight:600">${escapeHtml(u.username)}</div>
                            <div style="font-size:0.8rem;color:var(--text-muted)">${u.is_online ? "Online" : "Offline"}</div>
                        </div>
                    </div>`;
            }).join("");
        } catch (e) {
            results.innerHTML = `<div class="empty-state" style="padding:1.5rem"><p>Search failed. Try again.</p></div>`;
        }
    }, 300);
}

async function startChat(userId) {
    try {
        const res  = await fetch(`/api/conversation/start/${userId}`, { method: "POST" });
        const data = await res.json();
        if (!res.ok) { showToast(data.error, "error"); return; }

        closeNewChat();
        await loadConversations();
        openConversation(data.conversation_id);
    } catch (e) {
        showToast("Failed to start chat.", "error");
    }
}

// ─── Logout ─────────────────────────────────────────────────
async function logout() {
    if (confirm("Are you sure you want to log out?")) {
        window.location.href = "/logout";
    }
}

// ─── Profile Modal ───────────────────────────────────────────
function openProfile() {
    window.location.href = "/profile";
}

function closeProfileModal(event) {
    if (!event || event.target === document.getElementById("profileModal")) {
        document.getElementById("profileModal").style.display = "none";
    }
}

// ─── Back to conversation list (mobile & desktop) ────────────
function backToList() {
    const sidebar = document.getElementById("sidebar");
    if (sidebar) sidebar.classList.remove("hidden");

    const chatWindow = document.getElementById("chatWindow");
    if (chatWindow) chatWindow.style.display = "none";

    const welcome = document.getElementById("welcomeScreen");
    if (welcome) welcome.style.display = "flex";

    if (typeof socket !== "undefined" && socket && typeof currentConvId !== "undefined" && currentConvId) {
        socket.emit("leave_conversation", { conversation_id: currentConvId });
    }
    if (typeof activeConvId !== "undefined") activeConvId = null;
    if (typeof currentConvId !== "undefined") currentConvId = null;
    if (typeof currentOtherUser !== "undefined") currentOtherUser = null;

    document.querySelectorAll(".conversation-item").forEach(el => el.classList.remove("active"));
}

// ─── Utility: Escape HTML ────────────────────────────────────
function escapeHtml(str) {
    if (!str) return "";
    return str
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}

// ─── Utility: Parse and Format Timestamps ─────────────────────
function parseDate(isoString) {
    if (!isoString) return new Date();
    if (typeof isoString === "string") {
        // If string has 'T' and no timezone indicator (no Z and no +/- offset), treat as UTC by appending 'Z'
        if (isoString.includes("T") && !isoString.endsWith("Z") && !/[+-]\d{2}:\d{2}$/.test(isoString)) {
            isoString = isoString + "Z";
        }
    }
    const d = new Date(isoString);
    return isNaN(d.getTime()) ? new Date() : d;
}

function getDaysDifference(date, now) {
    const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
    const startOfMsgDay = new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
    return Math.round((startOfToday - startOfMsgDay) / 86400000);
}

function formatTime(isoString) {
    if (!isoString) return "";
    const date = parseDate(isoString);
    const now  = new Date();
    const days = getDaysDifference(date, now);

    if (days === 0) {
        // Today: show 12-hour time (e.g. "9:15 PM")
        return date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit", hour12: true });
    } else if (days === 1) {
        return "Yesterday";
    } else if (days > 1 && days < 7) {
        return date.toLocaleDateString([], { weekday: "short" });
    } else {
        return date.toLocaleDateString([], { month: "short", day: "numeric" });
    }
}

function formatFullTime(isoString) {
    if (!isoString) return "";
    const date = parseDate(isoString);
    return date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit", hour12: true });
}

function formatDateLabel(isoString) {
    if (!isoString) return "";
    const date = parseDate(isoString);
    const now  = new Date();
    const days = getDaysDifference(date, now);

    if (days === 0) return "Today";
    if (days === 1) return "Yesterday";
    if (days > 1 && days < 7) {
        return date.toLocaleDateString([], { weekday: "long" });
    }
    if (date.getFullYear() === now.getFullYear()) {
        return date.toLocaleDateString([], { month: "long", day: "numeric" });
    }
    return date.toLocaleDateString([], { year: "numeric", month: "long", day: "numeric" });
}

function formatLastSeen(isoString) {
    if (!isoString) return "Offline";
    const date = parseDate(isoString);
    const now  = new Date();
    const diffMs = now - date;
    const diffSec = Math.floor(diffMs / 1000);
    const diffMin = Math.floor(diffSec / 60);

    if (diffMin < 1) return "just now";
    if (diffMin < 60) return `${diffMin}m ago`;

    const days = getDaysDifference(date, now);
    const timeStr = date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit", hour12: true });
    if (days === 0) return `today at ${timeStr}`;
    if (days === 1) return `yesterday at ${timeStr}`;
    return `on ${date.toLocaleDateString([], { month: "short", day: "numeric" })}`;
}

// ─── App Init ────────────────────────────────────────────────
async function init() {
    // Apply saved theme
    const savedTheme = localStorage.getItem("theme") || "light";
    document.documentElement.setAttribute("data-theme", savedTheme);
    updateThemeIcon();

    // Load data
    await loadCurrentUser();
    await loadConversations();

    // Build emoji picker
    buildEmojiPicker();
}

// ─── Emoji Picker ────────────────────────────────────────────
const EMOJIS = [
    "😀","😂","😍","🥰","😎","😭","😤","🤩","😴","🤔",
    "👍","👎","❤️","🔥","✅","🎉","🙏","💯","😊","🥹",
    "😅","🤣","😆","😋","😜","😏","😒","😔","😢","😡",
    "👋","🤝","💪","👏","🫶","😇","🥳","🤯","💀","👀",
    "🌟","💫","⭐","🎵","🎶","🍕","🍔","🌮","☕","🎮"
];

function buildEmojiPicker() {
    const picker = document.getElementById("emojiPicker");
    if (!picker) return;
    picker.innerHTML = EMOJIS.map(e =>
        `<button class="emoji-btn" onclick="insertEmoji('${e}')">${e}</button>`
    ).join("");
}

function toggleEmojiPicker() {
    const picker = document.getElementById("emojiPicker");
    if (!picker) return;
    picker.style.display = picker.style.display === "none" ? "flex" : "none";
}

function insertEmoji(emoji) {
    const input = document.getElementById("messageInput");
    if (!input) return;
    const start = input.selectionStart;
    const end   = input.selectionEnd;
    input.value = input.value.slice(0, start) + emoji + input.value.slice(end);
    input.selectionStart = input.selectionEnd = start + emoji.length;
    input.focus();
    autoResize(input);
    // Hide picker after inserting
    document.getElementById("emojiPicker").style.display = "none";
}

function autoResize(textarea) {
    textarea.style.height = "auto";
    textarea.style.height = Math.min(textarea.scrollHeight, 120) + "px";
}

// Close emoji picker on click outside
document.addEventListener("click", (e) => {
    const picker  = document.getElementById("emojiPicker");
    const emojiBtn = document.getElementById("emojiBtn");
    if (picker && !picker.contains(e.target) && e.target !== emojiBtn && !emojiBtn?.contains(e.target)) {
        picker.style.display = "none";
    }
});

// ─── Lightbox ────────────────────────────────────────────────
function openLightbox(src) {
    const lb = document.getElementById("lightbox");
    document.getElementById("lightboxImg").src = src;
    lb.style.display = "flex";
}

function closeLightbox() {
    document.getElementById("lightbox").style.display = "none";
}

// ─── Start ───────────────────────────────────────────────────
window.addEventListener("DOMContentLoaded", init);
