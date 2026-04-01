// ============================================================
// ui_utils.js — Cookie helpers and view-toggle functions
// Exported as ES6 modules; consumed by app.js.
// ============================================================

/** Read a cookie value by name. Returns null when absent. */
export function getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    return parts.length === 2 ? parts.pop().split(';').shift() : null;
}

/** Set a cookie that persists for 1 year. */
export function setCookie(name, value) {
    const expires = new Date(Date.now() + 365 * 864e5).toUTCString();
    document.cookie = `${name}=${value}; expires=${expires}; path=/; SameSite=Lax`;
}

/** Delete a cookie by expiring it. */
export function delCookie(name) {
    document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;`;
}

/** Transition from the login card to the main app view. */
export function showApp(email) {
    document.getElementById('loginSection').classList.add('hidden');
    document.getElementById('mainContent').classList.remove('hidden');
    document.getElementById('userBadge').classList.remove('hidden');
    document.getElementById('userBadge').classList.add('flex');
    document.getElementById('userEmail').textContent = email;
}

/** Transition back to the login card. */
export function showLogin() {
    document.getElementById('loginSection').classList.remove('hidden');
    document.getElementById('mainContent').classList.add('hidden');
    document.getElementById('userBadge').classList.add('hidden');
    document.getElementById('userBadge').classList.remove('flex');
}
