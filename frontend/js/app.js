// ============================================================
// app.js — Main application initialisation (ES6 module)
// Wires login/logout, sample-question clicks, and the
// vanna-chat web component fallback.
// ============================================================

import { getCookie, setCookie, delCookie, showApp, showLogin } from './ui_utils.js';

document.addEventListener('DOMContentLoaded', () => {
    // Auto-login when a session cookie already exists
    const email = getCookie('vanna_email');
    if (email) showApp(email);

    // --- Login ---
    document.getElementById('loginBtn').addEventListener('click', () => {
        const selectedEmail = document.getElementById('emailSelect').value;
        if (!selectedEmail) {
            alert('Please select a role');
            return;
        }
        setCookie('vanna_email', selectedEmail);
        showApp(selectedEmail);
    });

    // --- Logout ---
    document.getElementById('logoutBtn').addEventListener('click', () => {
        delCookie('vanna_email');
        showLogin();
    });

    // Enter key on the role selector triggers login
    document.getElementById('emailSelect').addEventListener('keypress', (e) => {
        if (e.key === 'Enter') document.getElementById('loginBtn').click();
    });

    // --- Sample questions → paste into the vanna-chat input ---
    document.querySelectorAll('.sample-q').forEach((btn) => {
        btn.addEventListener('click', () => {
            const chat = document.querySelector('vanna-chat');
            if (chat && chat.shadowRoot) {
                const input = chat.shadowRoot.querySelector('textarea, input[type="text"]');
                if (input) {
                    input.value = btn.textContent.trim();
                    input.dispatchEvent(new Event('input', { bubbles: true }));
                    input.focus();
                }
            }
        });
    });

    // --- Fallback if the web component doesn't load within 3 s ---
    setTimeout(() => {
        if (!customElements.get('vanna-chat')) {
            const el = document.querySelector('vanna-chat');
            if (el) {
                el.innerHTML =
                    '<div class="p-10 text-center text-gray-500">' +
                    '<p class="font-medium">Chat component loading...</p>' +
                    '<p class="text-sm mt-1">If this persists, check your internet connection.</p></div>';
            }
        }
    }, 3000);
});
