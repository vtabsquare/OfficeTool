
import { getSidebarHTML, getHeaderHTML } from './components/layout.js';
import { router } from './router.js';
import { loadTimerState, updateTimerButton, handleTimerClick } from './features/timer.js';
import { closeModal } from './components/modal.js';
import { handleAttendanceNav } from './pages/attendance.js';
import { state } from './state.js';
import {
  showRequestCompOffModal,
  handleRequestCompOff,
} from "./pages/comp_off.js";
import { connectSocket } from './src/socket.js';
import { initAiAssistant as setupAiAssistant } from './components/AiAssistant.js';

// --- EVENT HANDLERS ---

const handleNavClick = (e: Event) => {
    const target = e.target as HTMLElement;
    const navLink = target.closest('.nav-link');

    if (navLink) {
        if (navLink.classList.contains('nav-toggle')) {
            e.preventDefault();
            navLink.parentElement?.classList.toggle('open');
        } else {
            // Close any open menus
            document.querySelectorAll('.nav-group.open').forEach(g => g.classList.remove('open'));
            // Set hash for router
            window.location.hash = navLink.getAttribute('href') || '#/';
        }
    }
};

type ThemeName = 'light' | 'dark' | 'sunset';

const THEME_STORAGE_KEY = 'theme';

const getTimeBasedTheme = (): ThemeName => {
    const hour = new Date().getHours();
    if (hour >= 5 && hour < 12) return 'light';      // Morning
    if (hour >= 17 && hour < 20) return 'sunset';    // Evening (warm light orange)
    if (hour >= 20 || hour < 5) return 'dark';       // Night
    return 'light';                                  // Afternoon default
};

const applyAppTheme = (theme: ThemeName) => {
    const body = document.body;
    body.classList.toggle('dark-theme', theme === 'dark');
    body.classList.toggle('sunset-theme', theme === 'sunset');
    body.setAttribute('data-theme', theme);

    const toggle = document.getElementById('theme-toggle');
    if (toggle) {
        const icon = toggle.querySelector('i');
        if (icon) {
            icon.classList.remove('fa-sun', 'fa-moon');
            // Dark theme → moon icon; Light theme → sun icon
            icon.classList.add(theme === 'dark' ? 'fa-moon' : 'fa-sun');
        }
    }
};

const initTheme = () => {
    const theme = getTimeBasedTheme();
    applyAppTheme(theme);

    const toggle = document.getElementById('theme-toggle');
    if (toggle) {
        toggle.addEventListener('click', () => {
            const currentTheme = (document.body.getAttribute('data-theme') as ThemeName) || 'light';
            const nextTheme: ThemeName = currentTheme === 'dark' ? 'light' : 'dark';
            applyAppTheme(nextTheme);
            try {
                localStorage.setItem(THEME_STORAGE_KEY, nextTheme);
            } catch {
                // ignore storage errors
            }
        });
    }
};

// --- INITIALIZATION ---

const setupRealtimeCallClient = () => {
    try {
        const user: any = (state as any)?.user || (window as any).state?.user || {};
        const rawId = String(user.id || '').trim().toUpperCase();
        const email = String((user.email || user.mail || '') || '').trim().toLowerCase();
        const isAdmin = rawId === 'EMP001' || email === 'bala.t@vtab.com' || !!user.is_admin;
        const roomId = (rawId || email || '');
        if (!roomId) return;
        const socket = connectSocket(roomId, isAdmin ? 'admin' : 'employee');
        let incomingPayload: any = null;
        let overlay: HTMLDivElement | null = null;
        let titleEl: HTMLHeadingElement | null = null;
        let textEl: HTMLParagraphElement | null = null;
        let joinBtn: HTMLButtonElement | null = null;
        let declineBtn: HTMLButtonElement | null = null;
        let audio: HTMLAudioElement | null = null;
        const stopAudio = () => {
            if (audio) {
                try {
                    audio.pause();
                    audio.currentTime = 0;
                } catch {
                }
            }
        };
        const hideOverlay = () => {
            if (overlay) {
                overlay.style.display = 'none';
            }
            incomingPayload = null;
            stopAudio();
        };
        const ensureOverlay = () => {
            if (overlay) return;
            overlay = document.createElement('div');
            overlay.id = 'global-incoming-call';
            overlay.className = 'incoming-call-overlay';
            overlay.style.display = 'none';

            const card = document.createElement('div');
            card.className = 'incoming-call-modal';

            const header = document.createElement('div');
            header.className = 'incoming-call-header';

            const iconWrap = document.createElement('div');
            iconWrap.className = 'incoming-call-icon-wrap';

            const iconSpan = document.createElement('span');
            iconSpan.textContent = '\ud83d\udcde';
            iconWrap.appendChild(iconSpan);

            const textWrap = document.createElement('div');

            titleEl = document.createElement('h2');
            titleEl.className = 'incoming-call-title';
            titleEl.textContent = 'Incoming call';

            textEl = document.createElement('p');
            textEl.className = 'incoming-call-body';
            textEl.textContent = 'You are being invited to join a meeting.';

            textWrap.appendChild(titleEl);
            textWrap.appendChild(textEl);

            header.appendChild(iconWrap);
            header.appendChild(textWrap);

            const btnRow = document.createElement('div');
            btnRow.className = 'incoming-call-actions';

            declineBtn = document.createElement('button');
            declineBtn.type = 'button';
            declineBtn.textContent = 'Decline';
            declineBtn.className = 'incoming-call-btn incoming-call-btn-decline';

            joinBtn = document.createElement('button');
            joinBtn.type = 'button';
            joinBtn.textContent = 'Join';
            joinBtn.className = 'incoming-call-btn incoming-call-btn-join';

            btnRow.appendChild(declineBtn);
            btnRow.appendChild(joinBtn);
            card.appendChild(header);
            card.appendChild(btnRow);
            overlay.appendChild(card);
            document.body.appendChild(overlay);
            if (declineBtn) {
                declineBtn.addEventListener('click', () => {
                    if (!incomingPayload) {
                        hideOverlay();
                        return;
                    }
                    try {
                        socket.emit('call:declined', {
                            call_id: incomingPayload.call_id,
                            employee_id: rawId || null,
                            email,
                        });
                    } catch {
                    }
                    hideOverlay();
                });
            }
            if (joinBtn) {
                joinBtn.addEventListener('click', () => {
                    if (!incomingPayload) {
                        hideOverlay();
                        return;
                    }
                    const link = incomingPayload.meet_url || incomingPayload.html_link;
                    try {
                        socket.emit('call:accepted', {
                            call_id: incomingPayload.call_id,
                            employee_id: rawId || null,
                            email,
                        });
                    } catch {
                    }
                    hideOverlay();
                    if (link) {
                        window.open(link, '_blank', 'noopener,noreferrer');
                    }
                });
            }
        };
        socket.on('call:ring', (payload: any) => {
            if (isAdmin) {
                return;
            }
            incomingPayload = payload;
            ensureOverlay();
            if (titleEl) {
                titleEl.textContent = payload?.title || 'Incoming call';
            }
            if (textEl) {
                textEl.textContent = 'You are being invited to join a Google Meet.';
            }
            if (overlay) {
                overlay.style.display = 'flex';
            }
            try {
                if (!audio) {
                    audio = new Audio('/ringtone.mp3');
                    audio.loop = true;
                }
                audio.currentTime = 0;
                audio.play().catch(() => {});
            } catch {
            }
        });
        socket.on('call:participant-update', (payload: any) => {
            if (!isAdmin) {
                return;
            }
            const handler = (window as any).__onParticipantUpdate;
            if (typeof handler === 'function') {
                try {
                    handler(payload);
                } catch (err) {
                    console.error('Participant update handler error', err);
                }
            }
        });
    } catch (err) {
        console.error('Failed to set up realtime client', err);
    }
};

const init = async () => {
    // Render initial layout
    document.getElementById('sidebar')!.innerHTML = getSidebarHTML();
    document.getElementById('header')!.innerHTML = getHeaderHTML(state.user, state.timer);

    initTheme();

    // Initialize AI Assistant (global chatbot)
    setupAiAssistant();

    setupRealtimeCallClient();

    // Set up router and render initial page
    window.addEventListener('hashchange', () => router());
    window.addEventListener('load', async () => {
        if (!window.location.hash) {
            window.location.hash = '#/';
        }
        await router();
    });
    
    // Load timer state and update display
    await loadTimerState();
    updateTimerButton();

    // Global event listeners (delegation)
    document.body.addEventListener('click', async (e) => {
        const target = e.target as HTMLElement;
        if (target.closest('#timer-btn')) await handleTimerClick();
        if (target.id === "request-compoff-btn") showRequestCompOffModal();
        if (target.id === 'add-employee-btn') {
            const { showAddEmployeeModal } = await import('./pages/employees.js');
            showAddEmployeeModal();
        }
        if (target.id === 'apply-leave-btn') {
            const { showApplyLeaveModal } = await import('./pages/leaveTracker.js');
            showApplyLeaveModal();
        }
        if (target.closest('.modal-close-btn')) closeModal();

        // Attendance month navigation
        const navBtn = target.closest('.month-nav-btn');
        if (navBtn) {
            const direction = navBtn.getAttribute('data-direction') as 'prev' | 'next';
            handleAttendanceNav(direction);
            await router(); // Re-render the page after updating the date
        }

        // My Attendance day selection
        const dayCell = target.closest('.calendar-day');
        if (dayCell) {
            const day = dayCell.getAttribute('data-day');
            if (day) {
                state.selectedAttendanceDay = parseInt(day, 10);
                const { renderMyAttendancePage } = await import('./pages/attendance.js');
                await renderMyAttendancePage(); // Re-render only the attendance page
            }
        }
    });

    document.body.addEventListener('submit', async (e: SubmitEvent) => {
        if ((e.target as HTMLElement).id === 'modal-form') {
            if (document.getElementById("save-employee-btn")) {
              const { handleAddEmployee } = await import(
                "./pages/employees.js"
              );
              await handleAddEmployee(e);
            } else if (document.getElementById("submit-leave-btn")) {
              const { handleApplyLeave } = await import(
                "./pages/leaveTracker.js"
              );
              await handleApplyLeave(e);
            } else if (document.getElementById("submit-compoff-btn")) {
              handleRequestCompOff(e);
            } 
        }
    });

    document.body.addEventListener('input', async (e) => {
        const target = e.target as HTMLInputElement;
        if (target.id === 'employee-search-input') {
            const { renderEmployeesPage } = await import('./pages/employees.js');
            await renderEmployeesPage(target.value);
        }
    });

    document.getElementById('sidebar')!.addEventListener('click', handleNavClick);
};

// Start the application
init();