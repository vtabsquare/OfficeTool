
import { state } from '../state.js';
import { API_BASE_URL } from '../config.js';

export const updateTimerDisplay = () => {
    const timerDisplay = document.getElementById('timer-display');
    if (!timerDisplay) return;
    
    if (!state.timer.isRunning || !state.timer.startTime) {
        timerDisplay.textContent = '00:00:00';
        return;
    }
    
    const elapsed = Date.now() - state.timer.startTime;
    const seconds = Math.floor((elapsed / 1000) % 60).toString().padStart(2, '0');
    const minutes = Math.floor((elapsed / (1000 * 60)) % 60).toString().padStart(2, '0');
    const hours = Math.floor(elapsed / (1000 * 60 * 60)).toString().padStart(2, '0');
    timerDisplay.textContent = `${hours}:${minutes}:${seconds}`;
};

const startTimer = async () => {
    try {
        const uid = String(state.user.id || '').toUpperCase();
        console.log(`🔄 Starting check-in for user: ${uid}`);
        
        // Import and call the checkIn API
        const { checkIn } = await import('./attendanceApi.js');
        const result = await checkIn(uid);
        
        console.log('✅ Check-in successful:', result);
        
        // Start the frontend timer
        state.timer.isRunning = true;
        state.timer.startTime = Date.now();
        state.timer.intervalId = setInterval(updateTimerDisplay, 1000);
        localStorage.setItem('timerState', JSON.stringify({ isRunning: true, startTime: state.timer.startTime }));
        updateTimerButton();
        
        // Show success message
        alert(`✅ Check-in successful!\nTime: ${result.checkin_time}\nAttendance ID: ${result.attendance_id}`);
        
    } catch (err) {
        console.error('❌ Check-in failed:', err);
        alert(`❌ Check-in failed: ${err.message || err}`);
    }
};

const stopTimer = async () => {
    try {
        const uid = String(state.user.id || '').toUpperCase();
        console.log(`🔄 Starting check-out for user: ${uid}`);
        
        // Import and call the checkOut API
        const { checkOut } = await import('./attendanceApi.js');
        const result = await checkOut(uid);
        
        console.log('✅ Check-out successful:', result);
        
        // Stop the frontend timer
        if(state.timer.intervalId) clearInterval(state.timer.intervalId);
        state.timer.isRunning = false;
        state.timer.intervalId = null;
        state.timer.startTime = null;
        localStorage.removeItem('timerState');
        updateTimerDisplay();
        updateTimerButton();
        
        // Show success message
        alert(`✅ Check-out successful!\nTime: ${result.checkout_time}\nDuration: ${result.duration}\nTotal Hours: ${result.total_hours}`);
        
        // Refresh attendance data after check-out
        try {
            const { renderMyAttendancePage } = await import('../pages/attendance.js');
            await renderMyAttendancePage();
        } catch (err) {
            console.warn('Failed to refresh attendance after check-out:', err);
        }
        
    } catch (err) {
        console.error('❌ Check-out failed:', err);
        alert(`❌ Check-out failed: ${err.message || err}`);
        
        // Still stop the timer even if API call fails
        if(state.timer.intervalId) clearInterval(state.timer.intervalId);
        state.timer.isRunning = false;
        state.timer.intervalId = null;
        state.timer.startTime = null;
        localStorage.removeItem('timerState');
        updateTimerDisplay();
        updateTimerButton();
    }
};

export const handleTimerClick = async () => {
    if (state.timer.isRunning) {
        await stopTimer();
    } else {
        await startTimer();
    }
};

export const updateTimerButton = () => {
    const timerBtn = document.getElementById('timer-btn');
    if (timerBtn) {
        if (state.timer.isRunning) {
            timerBtn.classList.remove('check-in');
            timerBtn.classList.add('check-out');
            timerBtn.innerHTML = `<span id="timer-display"></span> CHECK OUT`;
        } else {
            timerBtn.classList.remove('check-out');
            timerBtn.classList.add('check-in');
            timerBtn.innerHTML = `<span id="timer-display">00:00:00</span> CHECK IN`;
        }
        updateTimerDisplay();
    }
};

export const loadTimerState = async () => {
    const savedState = localStorage.getItem('timerState');
    if (savedState) {
        const { isRunning, startTime } = JSON.parse(savedState);
        if (isRunning) {
            // Check with backend if user is actually checked in
            try {
                const uid = String(state.user.id || '').toUpperCase();
                const base = API_BASE_URL.replace(/\/$/, '');
                const response = await fetch(`${base}/api/status/${uid}`);
                const statusData = await response.json();
                
                if (statusData.checked_in) {
                    // User is actually checked in, restore timer state
                    state.timer.isRunning = true;
                    state.timer.startTime = startTime;
                    state.timer.intervalId = setInterval(updateTimerDisplay, 1000);
                    console.log('✅ Timer state restored - user is checked in');
                } else {
                    // User is not checked in, clear timer state
                    localStorage.removeItem('timerState');
                    console.log('⚠️ Timer state cleared - user is not checked in');
                }
            } catch (err) {
                console.warn('Failed to verify check-in status:', err);
                // Fallback to local state
                state.timer.isRunning = true;
                state.timer.startTime = startTime;
                state.timer.intervalId = setInterval(updateTimerDisplay, 1000);
            }
        }
    }
};
