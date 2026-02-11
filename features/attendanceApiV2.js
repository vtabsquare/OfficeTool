// attendanceApiV2.js - Backend-Authoritative Attendance API Layer
// All endpoints return server-calculated values
// Frontend NEVER calculates duration or elapsed time

import { API_BASE_URL } from '../config.js';

const BASE_URL = API_BASE_URL.replace(/\/$/, '');
const API_VERSION = '/api/v2/attendance';

// ================== CORE ENDPOINTS ==================

/**
 * Check-in to start attendance session.
 * Backend creates/resumes session and returns authoritative timestamps.
 */
export async function checkIn(employeeId, location = null) {
    const payload = {
        employee_id: employeeId,
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
    };

    if (location) {
        payload.location = location;
    }

    const response = await fetch(`${BASE_URL}${API_VERSION}/checkin`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });

    const data = await response.json();

    if (!response.ok || !data.success) {
        const error = new Error(data.message || data.error || 'Check-in failed');
        error.code = data.error;
        throw error;
    }

    return data;
}

/**
 * Check-out to end attendance session.
 * Backend calculates duration and returns final totals.
 */
export async function checkOut(employeeId, location = null) {
    const payload = {
        employee_id: employeeId,
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
    };

    if (location) {
        payload.location = location;
    }

    const response = await fetch(`${BASE_URL}${API_VERSION}/checkout`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });

    const data = await response.json();

    if (!response.ok || !data.success) {
        const error = new Error(data.message || data.error || 'Check-out failed');
        error.code = data.error;
        throw error;
    }

    return data;
}

/**
 * Get current attendance status.
 * This is THE source of truth for timer display.
 * Called on page load, refresh, and periodically.
 */
export async function getStatus(employeeId) {
    const tz = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
    const url = `${BASE_URL}${API_VERSION}/status/${employeeId}?timezone=${encodeURIComponent(tz)}`;

    const response = await fetch(url, {
        method: 'GET',
        headers: { 'Accept': 'application/json' }
    });

    const data = await response.json();

    if (!response.ok || !data.success) {
        const error = new Error(data.message || data.error || 'Status fetch failed');
        error.code = data.error;
        throw error;
    }

    return data;
}

/**
 * Get monthly attendance records.
 * Returns server-calculated totals for each day.
 */
export async function getMonthlyAttendance(employeeId, year, month) {
    const tz = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
    const url = `${BASE_URL}${API_VERSION}/${employeeId}/${year}/${month}?timezone=${encodeURIComponent(tz)}`;

    const response = await fetch(url, {
        method: 'GET',
        headers: { 'Accept': 'application/json' }
    });

    const data = await response.json();

    if (!response.ok || !data.success) {
        const error = new Error(data.message || data.error || 'Fetch failed');
        error.code = data.error;
        throw error;
    }

    return data;
}

/**
 * Get team monthly attendance.
 * Aggregates attendance for multiple employees.
 */
export async function getTeamMonthlyAttendance(employeeIds, year, month) {
    const ids = employeeIds.filter(Boolean).map(id => String(id).toUpperCase());
    if (!ids.length) return { records: {} };

    const params = new URLSearchParams();
    params.set('year', String(year));
    params.set('month', String(month));
    params.set('employee_ids', ids.join(','));
    params.set('timezone', Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC');

    const response = await fetch(`${BASE_URL}${API_VERSION}/team-month?${params.toString()}`, {
        method: 'GET',
        headers: { 'Accept': 'application/json' }
    });

    const data = await response.json();

    if (!response.ok || !data.success) {
        const error = new Error(data.message || data.error || 'Team fetch failed');
        error.code = data.error;
        throw error;
    }

    return data;
}

// ================== ADMIN ENDPOINTS ==================

/**
 * Admin: Lock a day's attendance (no further edits allowed)
 */
export async function adminLockDay(date, employeeId = null) {
    const payload = { date };
    if (employeeId) {
        payload.employee_id = employeeId;
    }

    const response = await fetch(`${BASE_URL}${API_VERSION}/admin/lock-day`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });

    const data = await response.json();

    if (!response.ok || !data.success) {
        throw new Error(data.message || data.error || 'Lock failed');
    }

    return data;
}

/**
 * Admin: Manual status override
 */
export async function adminManualOverride(employeeId, date, status, totalSeconds = null, reason = '') {
    const payload = {
        employee_id: employeeId,
        date,
        status,
        reason
    };

    if (totalSeconds !== null) {
        payload.total_seconds = totalSeconds;
    }

    const response = await fetch(`${BASE_URL}${API_VERSION}/admin/manual-override`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });

    const data = await response.json();

    if (!response.ok || !data.success) {
        throw new Error(data.message || data.error || 'Override failed');
    }

    return data;
}

// ================== UTILITY FUNCTIONS ==================

/**
 * Parse status response into display-ready format
 */
export function parseStatusForDisplay(statusResponse) {
    if (!statusResponse || !statusResponse.success) {
        return {
            isCheckedIn: false,
            totalSeconds: 0,
            elapsedSeconds: 0,
            statusCode: null,
            statusLabel: 'Not Checked In',
            checkinTime: null,
            checkoutTime: null
        };
    }

    const { is_active_session, timing, status, display } = statusResponse;

    return {
        isCheckedIn: is_active_session,
        totalSeconds: timing?.total_seconds_today || 0,
        elapsedSeconds: timing?.elapsed_seconds || 0,
        statusCode: status?.code,
        statusLabel: status?.label,
        checkinTime: display?.checkin_local,
        checkoutTime: display?.checkout_local,
        elapsedText: display?.elapsed_text || display?.total_text,
        serverNow: statusResponse.server_now_utc
    };
}

/**
 * Format seconds to HH:MM:SS
 */
export function formatTimeHHMMSS(totalSeconds) {
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;

    return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
}

/**
 * Format seconds to human readable
 */
export function formatDuration(totalSeconds) {
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    return `${hours} hours ${minutes} minutes`;
}

/**
 * Format seconds to short form
 */
export function formatDurationShort(totalSeconds) {
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    return `${hours}h ${minutes}m`;
}

// ================== BACKWARD COMPATIBILITY ==================

// These exports maintain compatibility with old API layer
export { checkIn, checkOut };
export { getMonthlyAttendance as fetchMonthlyAttendance };
export { getStatus as fetchStatus };
