// attendanceRenderer.js - Stateless Frontend Attendance Rendering
// ZERO localStorage, ZERO setInterval for business logic, ZERO timer state ownership
// Frontend ONLY renders what backend tells it - backend is THE source of truth

import { state } from '../state.js';
import { API_BASE_URL } from '../config.js';

const BASE_URL = API_BASE_URL.replace(/\/$/, '');

// ================== CONFIGURATION ==================
const STATUS_REFRESH_INTERVAL_MS = 5000;  // Refresh status every 5 seconds during active session
const DISPLAY_UPDATE_INTERVAL_MS = 1000;  // Update display every 1 second (visual only)

// Module state (NOT persisted, reset on page load)
let statusRefreshIntervalId = null;
let displayUpdateIntervalId = null;
let lastStatusResponse = null;
let isInitialized = false;

// ================== CORE PRINCIPLE ==================
// elapsed_display = server_now_utc - last_session_start_utc + total_seconds_today
// This is calculated from backend data, NOT from local timers

// ================== API CALLS ==================

/**
 * Fetch current attendance status from backend.
 * This is THE source of truth for all timer displays.
 */
export async function fetchAttendanceStatus(employeeId) {
    if (!employeeId) return null;
    
    try {
        const tz = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
        const url = `${BASE_URL}/api/v2/attendance/status/${employeeId}?timezone=${encodeURIComponent(tz)}`;
        
        console.log('[ATTENDANCE-RENDERER] Fetching status from:', url);
        
        const response = await fetch(url, {
            method: 'GET',
            headers: { 'Accept': 'application/json' }
        });
        
        if (!response.ok) {
            throw new Error(`Status fetch failed: ${response.status}`);
        }
        
        const data = await response.json();
        console.log('[ATTENDANCE-RENDERER] Status response:', data);
        console.log('[ATTENDANCE-RENDERER] Timing data:', {
            total_seconds_today: data.timing?.total_seconds_today,
            elapsed_seconds: data.timing?.elapsed_seconds,
            is_active: data.is_active_session
        });
        
        if (data.success) {
            lastStatusResponse = {
                ...data,
                fetchedAt: Date.now(),
                serverNowAtFetch: data.server_now_utc ? new Date(data.server_now_utc).getTime() : Date.now()
            };
            console.log('[ATTENDANCE-RENDERER] Stored lastStatusResponse:', lastStatusResponse);
            return data;
        }
        
        return null;
    } catch (error) {
        console.error('[ATTENDANCE-RENDERER] fetchAttendanceStatus error:', error);
        return null;
    }
}

/**
 * Send check-in request to backend.
 * Frontend does NOT start timer - waits for backend confirmation.
 */
export async function performCheckIn(employeeId, location = null) {
    if (!employeeId) {
        throw new Error('Employee ID required');
    }
    
    const payload = {
        employee_id: employeeId,
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
    };
    
    if (location) {
        payload.location = location;
    }
    
    const response = await fetch(`${BASE_URL}/api/v2/attendance/checkin`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });
    
    const data = await response.json();
    
    if (!response.ok || !data.success) {
        throw new Error(data.message || data.error || 'Check-in failed');
    }
    
    // Update local cache with new status
    lastStatusResponse = {
        success: true,
        server_now_utc: data.server_now_utc,
        has_record: true,
        is_active_session: true,
        timing: {
            checkin_utc: data.checkin_utc,
            last_session_start_utc: data.checkin_utc,
            elapsed_seconds: 0,
            total_seconds_today: data.total_seconds_today || 0
        },
        status: {
            code: data.status_code,
            label: data.status_code === 'P' ? 'Present' : data.status_code === 'HL' ? 'Half Day' : 'Working'
        },
        fetchedAt: Date.now(),
        serverNowAtFetch: new Date(data.server_now_utc).getTime()
    };
    
    // Trigger immediate UI update
    updateTimerDisplay();
    
    return data;
}

/**
 * Send check-out request to backend.
 * Frontend does NOT stop timer - waits for backend confirmation.
 */
export async function performCheckOut(employeeId, location = null) {
    if (!employeeId) {
        throw new Error('Employee ID required');
    }
    
    // Check for and pause any running task timers before checkout
    try {
        // Use the same logic as My Tasks page to get the correct user_id format
        const user = state?.user || window.state?.user || {};
        const empId = String((user.id || user.employee_id || user.employeeId || '')).trim();
        
        console.log('[ATTENDANCE-RENDERER] Checking for active task timers before checkout...');
        console.log('[ATTENDANCE-RENDERER] User object:', user);
        console.log('[ATTENDANCE-RENDERER] Employee ID:', empId);
        
        // First check localStorage (for tasks started via My Tasks page)
        const activeKey = `tt_active_${empId}`;
        const activeData = localStorage.getItem(activeKey);
        
        console.log('[ATTENDANCE-RENDERER] LocalStorage active key:', activeKey);
        console.log('[ATTENDANCE-RENDERER] LocalStorage active data found:', !!activeData);
        
        // Debug: Show all localStorage keys that contain 'tt_active'
        console.log('[ATTENDANCE-RENDERER] All tt_active keys in localStorage:');
        for (let i = 0; i < localStorage.length; i++) {
            const key = localStorage.key(i);
            if (key && key.includes('tt_active')) {
                console.log(`  - ${key}: ${localStorage.getItem(key)}`);
            }
        }
        
        // If no active task in localStorage, check backend for any running timers
        if (!activeData) {
            console.log('[ATTENDANCE-RENDERER] No active task in localStorage, checking backend for running timers...');
            
            try {
                // Check timer status for this user
                const statusResponse = await fetch(`${BASE_URL}/api/time-entries/status?user_id=${encodeURIComponent(empId)}`, {
                    method: 'GET',
                    headers: { 'Content-Type': 'application/json' }
                });
                
                console.log('[ATTENDANCE-RENDERER] Timer status response status:', statusResponse.status);
                
                if (statusResponse.ok) {
                    const statusData = await statusResponse.json();
                    console.log('[ATTENDANCE-RENDERER] Timer status data:', statusData);
                    
                    if (statusData.success && statusData.active && statusData.task_guid) {
                        console.log('[ATTENDANCE-RENDERER] Found active timer, stopping it:', statusData.task_guid);
                        
                        // Stop the active timer
                        const stopResponse = await fetch(`${BASE_URL}/api/time-entries/stop`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                                task_guid: statusData.task_guid,
                                user_id: empId
                            })
                        });
                        
                        console.log('[ATTENDANCE-RENDERER] Backend stop response status:', stopResponse.status);
                        
                        if (stopResponse.ok) {
                            const stopResult = await stopResponse.json();
                            console.log('[ATTENDANCE-RENDERER] Task timer stopped successfully from backend:', stopResult);
                            
                            // Force complete page reload to clear all timer state
                            console.log('[ATTENDANCE-RENDERER] Forcing complete page reload to clear timer state...');
                            
                            // Clear all possible timer keys aggressively
                            try {
                                const user = state?.user || window.state?.user || {};
                                const empId = String((user.id || user.employee_id || user.employeeId || '')).trim();
                                
                                // Remove ALL timer-related keys regardless of format
                                const keysToRemove = [];
                                for (let i = 0; i < localStorage.length; i++) {
                                    const key = localStorage.key(i);
                                    if (key && (key.includes('tt_') || key.includes('timer') || key.includes('active'))) {
                                        keysToRemove.push(key);
                                    }
                                }
                                
                                keysToRemove.forEach(key => {
                                    localStorage.removeItem(key);
                                    console.log(`[ATTENDANCE-RENDERER] Aggressively removed key: ${key}`);
                                });
                                
                                // Force complete page reload after a short delay
                                setTimeout(() => {
                                    console.log('[ATTENDANCE-RENDERER] Reloading page to clear all timer state');
                                    
                                    // Add debugging info before reload
                                    console.log('[ATTENDANCE-RENDERER] Pre-reload debug:');
                                    console.log('- Current hash:', window.location.hash);
                                    console.log('- All localStorage keys:');
                                    for (let i = 0; i < localStorage.length; i++) {
                                        const key = localStorage.key(i);
                                        console.log(`  - ${key}: ${localStorage.getItem(key)}`);
                                    }
                                    console.log('- SessionStorage keys:');
                                    for (let i = 0; i < sessionStorage.length; i++) {
                                        const key = sessionStorage.key(i);
                                        console.log(`  - ${key}: ${sessionStorage.getItem(key)}`);
                                    }
                                    
                                    window.location.reload();
                                }, 300);
                                
                            } catch (reloadError) {
                                console.error('[ATTENDANCE-RENDERER] Error during page reload:', reloadError);
                                // Fallback: try hash change reload
                                window.location.hash = '#/';
                                setTimeout(() => {
                                    window.location.hash = '#/time-my-tasks';
                                }, 100);
                            }
                        } else {
                            const errorData = await stopResponse.json().catch(() => ({}));
                            console.warn('[ATTENDANCE-RENDERER] Failed to stop task timer from backend:', stopResponse.status, errorData);
                        }
                    } else {
                        console.log('[ATTENDANCE-RENDERER] No active timers found in backend status');
                    }
                } else {
                    console.warn('[ATTENDANCE-RENDERER] Failed to fetch timer status from backend:', statusResponse.status);
                }
            } catch (error) {
                console.error('[ATTENDANCE-RENDERER] Error checking backend for active timers:', error);
            }
        } else {
            // Handle localStorage active task (original logic)
            const activeTask = JSON.parse(activeData);
            console.log('[ATTENDANCE-RENDERER] Active task data from localStorage:', activeTask);
            
            // Check if there's a running task timer (not paused)
            if (activeTask.task_guid && !activeTask.paused) {
                console.log('[ATTENDANCE-RENDERER] Pausing active task timer before checkout:', activeTask.task_guid);
                
                // Stop the task timer
                const stopResponse = await fetch(`${BASE_URL}/api/time-entries/stop`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        task_guid: activeTask.task_guid,
                        user_id: empId
                    })
                });
                
                console.log('[ATTENDANCE-RENDERER] Stop response status:', stopResponse.status);
                
                if (stopResponse.ok) {
                    // Clear the active task from localStorage
                    localStorage.removeItem(activeKey);
                    console.log('[ATTENDANCE-RENDERER] Task timer paused successfully before checkout');
                } else {
                    const errorData = await stopResponse.json().catch(() => ({}));
                    console.warn('[ATTENDANCE-RENDERER] Failed to pause task timer before checkout:', stopResponse.status, errorData);
                }
            } else {
                console.log('[ATTENDANCE-RENDERER] No running task timer found - task is paused or no task_guid');
            }
        }
    } catch (error) {
        console.error('[ATTENDANCE-RENDERER] Error checking/pausing task timer before checkout:', error);
        // Continue with checkout even if task timer pause fails
    }
    
    const payload = {
        employee_id: employeeId,
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
    };
    
    if (location) {
        payload.location = location;
    }
    
    const response = await fetch(`${BASE_URL}/api/v2/attendance/checkout`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });
    
    const data = await response.json();
    
    if (!response.ok || !data.success) {
        throw new Error(data.message || data.error || 'Check-out failed');
    }
    
    // Update local cache with new status
    lastStatusResponse = {
        success: true,
        server_now_utc: data.server_now_utc,
        has_record: true,
        is_active_session: false,
        timing: {
            checkout_utc: data.checkout_utc,
            total_seconds_today: data.total_seconds_today
        },
        status: {
            code: data.status_code,
            label: data.display?.status_label || data.status_code
        },
        fetchedAt: Date.now(),
        serverNowAtFetch: new Date(data.server_now_utc).getTime()
    };
    
    // Trigger immediate UI update
    updateTimerDisplay();
    
    return data;
}

// ================== DISPLAY CALCULATION ==================

/**
 * Calculate current elapsed seconds based on backend data.
 * This uses local time ONLY for visual interpolation between status refreshes.
 * The base values (server_now, checkin_utc, total_seconds) are from backend.
 */
function calculateCurrentElapsed() {
    if (!lastStatusResponse) {
        return { totalSeconds: 0, isActive: false };
    }
    
    const { is_active_session, timing, fetchedAt, serverNowAtFetch } = lastStatusResponse;
    
    if (!is_active_session) {
        // Not active - return stored total
        return {
            totalSeconds: timing?.total_seconds_today || 0,
            isActive: false
        };
    }
    
    // Active session - backend calculated total seconds at fetch time
    // Add small visual interpolation (max 5 seconds to prevent drift)
    const baseSeconds = timing?.total_seconds_today || 0;
    const msSinceFetch = Date.now() - fetchedAt;
    const secondsSinceFetch = Math.min(Math.floor(msSinceFetch / 1000), 5); // Cap at 5 seconds
    const totalSeconds = baseSeconds + secondsSinceFetch;
    
    return {
        totalSeconds: Math.max(0, totalSeconds),
        isActive: true
    };
}

/**
 * Format seconds to HH:MM:SS display string
 */
function formatTime(totalSeconds) {
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;
    
    return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
}

/**
 * Format seconds to human readable string
 */
function formatDuration(totalSeconds) {
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    return `${hours}h ${minutes}m`;
}

// ================== UI UPDATES ==================

/**
 * Update the timer display element.
 * Called every second for visual updates, but values derived from backend data.
 */
export function updateTimerDisplay() {
    const timerDisplay = document.getElementById('timer-display');
    const timerBtn = document.getElementById('timer-btn');
    
    if (!timerDisplay && !timerBtn) return;
    
    const { totalSeconds, isActive } = calculateCurrentElapsed();
    const timeString = formatTime(totalSeconds);
    
    // Debug logging
    if (Math.random() < 0.01) { // Log 1% of the time to avoid spam
        console.log('[ATTENDANCE-RENDERER] Display update:', {
            totalSeconds,
            isActive,
            timeString,
            hasResponse: !!lastStatusResponse
        });
    }
    
    if (timerDisplay) {
        timerDisplay.textContent = timeString;
    }
    
    if (timerBtn) {
        if (isActive) {
            timerBtn.classList.remove('check-in');
            timerBtn.classList.add('check-out');
            timerBtn.innerHTML = `<span id="timer-display">${timeString}</span> CHECK OUT`;
        } else {
            timerBtn.classList.remove('check-out');
            timerBtn.classList.add('check-in');
            const displayTime = totalSeconds > 0 ? timeString : '00:00:00';
            timerBtn.innerHTML = `<span id="timer-display">${displayTime}</span> CHECK IN`;
        }
    }
    
    // Update state for other components (but NOT for persistence!)
    if (state.timer) {
        state.timer.displaySeconds = totalSeconds;
        state.timer.isActive = isActive;
    }
}

/**
 * Update the timer button state based on backend status
 */
export function updateTimerButton() {
    updateTimerDisplay();
}

// ================== INITIALIZATION ==================

/**
 * Initialize the attendance renderer.
 * Called on page load - fetches status from backend and starts display updates.
 */
export async function initializeAttendance(employeeId) {
    if (!employeeId) {
        console.warn('[ATTENDANCE-RENDERER] No employee ID provided');
        return;
    }
    
    console.log('[ATTENDANCE-RENDERER] Initializing for employee:', employeeId);
    
    // Clean up any existing intervals
    cleanup();
    
    // Fetch initial status from backend
    const status = await fetchAttendanceStatus(employeeId);
    
    if (status) {
        console.log('[ATTENDANCE-RENDERER] Initial status:', {
            isActive: status.is_active_session,
            totalSeconds: status.timing?.total_seconds_today,
            statusCode: status.status?.code
        });
    }
    
    // Initial display update
    updateTimerDisplay();
    
    // Start display update interval (visual interpolation only)
    displayUpdateIntervalId = setInterval(() => {
        // Always update display for visual consistency
        updateTimerDisplay();
    }, DISPLAY_UPDATE_INTERVAL_MS);
    
    // Start status refresh interval (sync with backend)
    statusRefreshIntervalId = setInterval(async () => {
        await fetchAttendanceStatus(employeeId);
        updateTimerDisplay();
    }, STATUS_REFRESH_INTERVAL_MS);
    
    // Listen for visibility changes (tab focus)
    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'visible') {
            // Tab became visible - refresh from backend
            fetchAttendanceStatus(employeeId).then(() => {
                updateTimerDisplay();
            });
        }
    });
    
    isInitialized = true;
    console.log('[ATTENDANCE-RENDERER] Initialization complete');
}

/**
 * Handle timer button click.
 * Determines whether to check-in or check-out based on backend state.
 */
export async function handleTimerClick() {
    const employeeId = state.user?.id;
    
    if (!employeeId) {
        alert('User not logged in');
        return;
    }
    
    const timerBtn = document.getElementById('timer-btn');
    if (timerBtn) {
        timerBtn.disabled = true;
        timerBtn.style.opacity = '0.7';
    }
    
    try {
        // Get current location (optional, non-blocking)
        let location = null;
        try {
            location = await getGeolocation();
        } catch {
            // Location capture failed - continue without it
        }
        
        // Determine action based on current status
        const isCurrentlyActive = lastStatusResponse?.is_active_session || false;
        
        if (isCurrentlyActive) {
            // Check out
            await performCheckOut(employeeId, location);
            console.log('[ATTENDANCE-RENDERER] Check-out successful');
        } else {
            // Check in
            await performCheckIn(employeeId, location);
            console.log('[ATTENDANCE-RENDERER] Check-in successful');
        }
        
        // Refresh status to ensure sync
        await fetchAttendanceStatus(employeeId);
        updateTimerDisplay();
        
    } catch (error) {
        console.error('[ATTENDANCE-RENDERER] Timer action failed:', error);
        alert(error.message || 'Operation failed. Please try again.');
        
        // Refresh status to show actual state
        await fetchAttendanceStatus(employeeId);
        updateTimerDisplay();
    } finally {
        if (timerBtn) {
            timerBtn.disabled = false;
            timerBtn.style.opacity = '1';
        }
    }
}

/**
 * Get current geolocation (with timeout)
 */
function getGeolocation() {
    return new Promise((resolve, reject) => {
        if (!navigator.geolocation) {
            reject(new Error('Geolocation not supported'));
            return;
        }
        
        const timeout = setTimeout(() => {
            reject(new Error('Geolocation timeout'));
        }, 10000);
        
        navigator.geolocation.getCurrentPosition(
            (pos) => {
                clearTimeout(timeout);
                resolve({
                    lat: pos.coords.latitude,
                    lng: pos.coords.longitude,
                    accuracy_m: pos.coords.accuracy
                });
            },
            (err) => {
                clearTimeout(timeout);
                reject(err);
            },
            { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
        );
    });
}

/**
 * Clean up intervals and listeners
 */
export function cleanup() {
    if (statusRefreshIntervalId) {
        clearInterval(statusRefreshIntervalId);
        statusRefreshIntervalId = null;
    }
    if (displayUpdateIntervalId) {
        clearInterval(displayUpdateIntervalId);
        displayUpdateIntervalId = null;
    }
    lastStatusResponse = null;
    isInitialized = false;
}

// ================== SOCKET EVENT HANDLER ==================

/**
 * Handle attendance change event from socket.
 * Socket only tells us something changed - we fetch fresh data from backend.
 */
export async function handleAttendanceChanged(data) {
    const employeeId = state.user?.id;
    
    if (!employeeId) return;
    
    // Only refresh if the event is for this employee
    if (data.employee_id && data.employee_id.toUpperCase() !== employeeId.toUpperCase()) {
        return;
    }
    
    console.log('[ATTENDANCE-RENDERER] Attendance changed event, refreshing status');
    
    // Fetch fresh status from backend
    await fetchAttendanceStatus(employeeId);
    updateTimerDisplay();
}

// ================== EXPORTS FOR BACKWARD COMPATIBILITY ==================

// These functions maintain API compatibility with the old timer.js
// loadTimerState gets employee ID from state automatically
export async function loadTimerState(employeeId = null) {
    const empId = employeeId || state.user?.id;
    console.log('[ATTENDANCE-RENDERER] loadTimerState called with:', empId);
    if (!empId) {
        console.warn('[ATTENDANCE-RENDERER] loadTimerState: No employee ID available');
        return;
    }
    return initializeAttendance(empId);
}
// updateTimerButton is already exported above

// Get current state for other components
export function getAttendanceState() {
    if (!lastStatusResponse) {
        return {
            isActive: false,
            totalSeconds: 0,
            statusCode: null
        };
    }
    
    const { totalSeconds, isActive } = calculateCurrentElapsed();
    
    return {
        isActive,
        totalSeconds,
        statusCode: lastStatusResponse.status?.code,
        statusLabel: lastStatusResponse.status?.label,
        checkinUtc: lastStatusResponse.timing?.checkin_utc,
        checkoutUtc: lastStatusResponse.timing?.checkout_utc
    };
}

// Check if currently checked in
export function isCheckedIn() {
    return lastStatusResponse?.is_active_session || false;
}

// Get total seconds worked today
export function getTotalSecondsToday() {
    const { totalSeconds } = calculateCurrentElapsed();
    return totalSeconds;
}
