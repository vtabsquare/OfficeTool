import { getPageContentHTML } from '../utils.js';
import { API_BASE_URL } from '../config.js';
import { timedFetch } from '../features/timedFetch.js';
import { fetchOnLeaveToday } from '../features/leaveApi.js';
import { listAllEmployees } from '../features/employeeApi.js';
import { isAdminUser } from '../utils/accessControl.js';
import { state } from '../state.js';

const BASE_URL = API_BASE_URL.replace(/\/$/, '');
const DASHBOARD_PATH = '#/admin-dashboard';
const isAdminDashboardRoute = () => String(window.location.hash || '').startsWith(DASHBOARD_PATH);

const buildAdminAuthQuery = () => {
  const qs = new URLSearchParams();
  const requesterEmployeeId = normalizeEmpId(state.user?.id || state.user?.employee_id);
  const requesterEmail = String(state.user?.email || '').trim().toLowerCase();
  if (requesterEmployeeId) qs.set('requester_employee_id', requesterEmployeeId);
  if (requesterEmail) qs.set('requester_email', requesterEmail);
  const query = qs.toString();
  return query ? `?${query}` : '';
};

let adminDashboardPollId = null;
let adminDashboardTickId = null;
let refreshInFlight = false;
let liveRefreshDebounceId = null;
let liveHooksBound = false;

const escapeHtml = (value = '') => String(value)
  .replace(/&/g, '&amp;')
  .replace(/</g, '&lt;')
  .replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;')
  .replace(/'/g, '&#39;');

const normalizeEmpId = (value = '') => String(value || '').trim().toUpperCase();

const formatDuration = (seconds = 0) => {
  const safe = Math.max(0, Number(seconds) || 0);
  const hh = Math.floor(safe / 3600).toString().padStart(2, '0');
  const mm = Math.floor((safe % 3600) / 60).toString().padStart(2, '0');
  const ss = Math.floor(safe % 60).toString().padStart(2, '0');
  return `${hh}:${mm}:${ss}`;
};

const formatCheckInTime = (timeStr = '') => {
  if (!timeStr) return '--';
  
  // Handle ISO format: 2025-03-11T09:30:00Z or 2025-03-11T09:30:00+05:30
  if (timeStr.includes('T') && (timeStr.includes('Z') || timeStr.includes('+'))) {
    try {
      const date = new Date(timeStr);
      if (isNaN(date.getTime())) return timeStr; // Return original if invalid
      
      // Get local time in HH:MM format
      const hours = date.getHours().toString().padStart(2, '0');
      const minutes = date.getMinutes().toString().padStart(2, '0');
      return `${hours}:${minutes}`;
    } catch (e) {
      return timeStr; // Return original if parsing fails
    }
  }
  
  // Handle time-only format: 09:30:00 or 09:30
  if (timeStr.match(/^\d{1,2}:\d{2}/)) {
    return timeStr.split(':').slice(0, 2).join(':');
  }
  
  // Return original if no format matches
  return timeStr;
};

const stopDashboardTimers = () => {
  if (adminDashboardPollId) {
    clearInterval(adminDashboardPollId);
    adminDashboardPollId = null;
  }
  if (adminDashboardTickId) {
    clearInterval(adminDashboardTickId);
    adminDashboardTickId = null;
  }
};

const scheduleLiveRefresh = () => {
  if (!isAdminDashboardRoute()) return;
  if (liveRefreshDebounceId) {
    clearTimeout(liveRefreshDebounceId);
    liveRefreshDebounceId = null;
  }
  liveRefreshDebounceId = setTimeout(() => {
    liveRefreshDebounceId = null;
    refreshAndRender(false);
  }, 250);
};

const bindLiveRefreshHooks = () => {
  if (liveHooksBound) return;

  window.addEventListener('taskTimerStarted', scheduleLiveRefresh);
  window.addEventListener('taskTimerStopped', scheduleLiveRefresh);
  window.addEventListener('storage', (event) => {
    const key = String(event?.key || '');
    if (!key) return;
    if (key.startsWith('tt_active_') || key.startsWith('tt_accum_')) {
      scheduleLiveRefresh();
    }
  });

  liveHooksBound = true;
};

const buildStatusDonut = (checkedIn = 0, notCheckedIn = 0) => {
  const total = Math.max(checkedIn + notCheckedIn, 1);
  const checkedPct = (checkedIn / total) * 100;
  const style = `background: conic-gradient(var(--success) 0% ${checkedPct}%, var(--danger) ${checkedPct}% 100%);`;
  return `
    <div class="admin-donut-wrap">
      <div class="admin-donut" style="${style}">
        <span>${checkedIn}/${total}</span>
      </div>
      <div class="admin-donut-legend">
        <span><i class="dot dot-present"></i> Checked In (${checkedIn})</span>
        <span><i class="dot dot-absent"></i> Not Checked In (${notCheckedIn})</span>
      </div>
    </div>
  `;
};

const buildProjectLoadBars = (items = []) => {
  if (!items.length) {
    return '<p class="placeholder-text">No active tasks right now.</p>';
  }

  const grouped = items.reduce((acc, row) => {
    const key = row.project_name || row.project_id || 'Unmapped Project';
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {});

  const rows = Object.entries(grouped)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 8);

  const max = Math.max(...rows.map(([, count]) => count), 1);

  return `
    <div class="task-load-grid">
      ${rows.map(([project, count]) => {
        const pct = Math.round((count / max) * 100);
        const intensity = pct > 66 ? 'high' : pct > 33 ? 'medium' : 'low';
        return `
          <div class="task-load-card">
            <div class="task-load-header">
              <div class="task-load-project">${escapeHtml(project)}</div>
              <div class="task-load-count">${count}</div>
            </div>
            <div class="task-load-bar-wrapper">
              <div class="task-load-bar task-load-bar-${intensity}" style="width:${pct}%"></div>
            </div>
            <div class="task-load-footer">
              <span class="task-load-label">${count === 1 ? 'task' : 'tasks'}</span>
            </div>
          </div>
        `;
      }).join('')}
    </div>
  `;
};

const buildSkeleton = () => `
  <section class="admin-dashboard">
    <div class="dashboard-grid admin-dashboard-grid">
      ${Array.from({ length: 4 }).map(() => `
        <section class="card admin-card">
          <div class="skeleton skeleton-heading-md"></div>
          <div class="skeleton skeleton-text" style="margin-top:0.6rem;width:70%"></div>
          <div class="skeleton skeleton-list-line-lg" style="margin-top:1.1rem"></div>
          <div class="skeleton skeleton-list-line-sm"></div>
        </section>
      `).join('')}
    </div>
  </section>
`;

const fetchAttendanceMonitoring = async () => {
  const res = await timedFetch(`${BASE_URL}/api/admin/attendance-monitoring/today${buildAdminAuthQuery()}`, {}, 'adminAttendanceMonitoring');
  const data = await res.json();
  if (!res.ok || !data.success) {
    throw new Error(data.error || 'Failed to load attendance monitoring');
  }
  return data;
};

const fetchActiveTaskSnapshot = async () => {
  const res = await timedFetch(`${BASE_URL}/api/admin/active-tasks${buildAdminAuthQuery()}`, {}, 'adminActiveTasks');
  const data = await res.json();
  if (!res.ok || !data.success) {
    throw new Error(data.error || 'Failed to load active tasks');
  }
  return data;
};

const loadAdminDashboardData = async () => {
  const [attendanceResult, activeTasksResult, leavesResult, employeesResult] = await Promise.allSettled([
    fetchAttendanceMonitoring(),
    fetchActiveTaskSnapshot(),
    fetchOnLeaveToday(),
    listAllEmployees(),
  ]);

  if (attendanceResult.status !== 'fulfilled') {
    throw attendanceResult.reason || new Error('Failed to load attendance monitoring');
  }

  if (activeTasksResult.status !== 'fulfilled') {
    throw activeTasksResult.reason || new Error('Failed to load active tasks');
  }

  const attendance = attendanceResult.value || {};
  const activeTasks = activeTasksResult.value || {};
  const leaves = leavesResult.status === 'fulfilled' ? (leavesResult.value || []) : [];
  const employees = employeesResult.status === 'fulfilled' ? (employeesResult.value || []) : [];

  const employeeNameMap = new Map(
    (employees || []).map((emp) => {
      const id = normalizeEmpId(emp.employee_id || emp.id);
      const name = String(emp.name || `${emp.first_name || ''} ${emp.last_name || ''}`.trim() || id);
      return [id, name];
    })
  );

  const leaveRows = (leaves || []).map((leave) => {
    const id = normalizeEmpId(leave.employee_id);
    return {
      employee_id: id,
      employee_name: employeeNameMap.get(id) || id,
      leave_type: leave.leave_type || 'Leave',
      start_date: leave.start_date || '',
      end_date: leave.end_date || leave.start_date || '',
    };
  });

  return {
    attendance,
    activeTasks: activeTasks.items || [],
    leaveRows,
  };
};

const buildDashboardLayout = (data) => {
  const checkedInList = (data.attendance.checked_in_employees || []).slice(0, 6);
  const checkedInMarkup = checkedInList.length
    ? `<ul class="mini-list">${checkedInList.map((emp) => `
      <li>
        <div>
          <h4>${escapeHtml(emp.employee_name || emp.employee_id)}</h4>
          <p>${escapeHtml(emp.employee_id || '')}</p>
        </div>
        <span class="badge">${escapeHtml(formatCheckInTime(emp.check_in))}</span>
      </li>
    `).join('')}</ul>`
    : '<p class="placeholder-text">No employees are currently checked in.</p>';

  const leaveTableRows = data.leaveRows.length
    ? data.leaveRows.map((row) => `
      <tr>
        <td>${escapeHtml(row.employee_id)}</td>
        <td>${escapeHtml(row.employee_name)}</td>
        <td>${escapeHtml(row.leave_type)}</td>
        <td>${escapeHtml(row.start_date)}</td>
        <td>${escapeHtml(row.end_date)}</td>
      </tr>
    `).join('')
    : '<tr><td colspan="5" style="color: var(--text-secondary);">No employees are on leave today.</td></tr>';

  const activeTaskRows = data.activeTasks.length
    ? data.activeTasks.map((task) => `
      <tr>
        <td>${escapeHtml(task.employee_name || task.employee_id)}</td>
        <td>${escapeHtml(task.task_name || task.task_id || task.task_guid)}</td>
        <td>${escapeHtml(task.project_name || task.project_id || '--')}</td>
        <td class="mono" data-elapsed data-started-at="${escapeHtml(task.started_at_utc || '')}">${formatDuration(task.elapsed_seconds)}</td>
      </tr>
    `).join('')
    : '<tr><td colspan="4" style="color: var(--text-secondary);">No active task sessions right now.</td></tr>';

  return `
    <section class="admin-dashboard">
      <div class="admin-kpis">
        <div class="hero-stat"><strong>${data.attendance.total_employees || 0}</strong><span>Total Employees</span></div>
        <div class="hero-stat"><strong>${data.attendance.checked_in_count || 0}</strong><span>Checked In</span></div>
        <div class="hero-stat"><strong>${data.attendance.not_checked_in_count || 0}</strong><span>Not Checked In</span></div>
        <div class="hero-stat"><strong>${data.activeTasks.length}</strong><span>Active Tasks</span></div>
      </div>

      <div class="dashboard-grid admin-dashboard-grid">
        <section class="card admin-card admin-card-span-2">
          <header class="card-heading">
            <div>
              <p class="eyebrow">Live Work</p>
              <h3>Active Tasks Across Organization</h3>
            </div>
            <span class="badge">Auto refresh: 15s</span>
          </header>
          <div class="leave-table-scroll admin-table-scroll">
            <table class="table leave-table">
              <thead>
                <tr>
                  <th>Employee</th>
                  <th>Task</th>
                  <th>Project</th>
                  <th>Running</th>
                </tr>
              </thead>
              <tbody>
                ${activeTaskRows}
              </tbody>
            </table>
          </div>
        </section>

        <section class="card admin-card admin-card-span-2">
          <header class="card-heading">
            <div>
              <p class="eyebrow">Leave</p>
              <h3>On Leave Today</h3>
            </div>
            <span class="badge">Filter: Today</span>
          </header>
          <div class="leave-table-scroll admin-table-scroll">
            <table class="table leave-table">
              <thead>
                <tr>
                  <th>Employee ID</th>
                  <th>Name</th>
                  <th>Leave Type</th>
                  <th>Start</th>
                  <th>End</th>
                </tr>
              </thead>
              <tbody>
                ${leaveTableRows}
              </tbody>
            </table>
          </div>
        </section>

        <section class="card admin-card">
          <header class="card-heading">
            <div>
              <p class="eyebrow">Attendance</p>
              <h3>Employee Monitoring</h3>
            </div>
            <span class="badge">Today</span>
          </header>
          ${buildStatusDonut(data.attendance.checked_in_count || 0, data.attendance.not_checked_in_count || 0)}
          ${checkedInMarkup}
        </section>

        <section class="card admin-card">
          <header class="card-heading">
            <div>
              <p class="eyebrow">Task Load</p>
              <h3>Active Tasks by Project</h3>
            </div>
          </header>
          ${buildProjectLoadBars(data.activeTasks)}
        </section>
      </div>
    </section>
  `;
};

const startElapsedTick = () => {
  if (adminDashboardTickId) {
    clearInterval(adminDashboardTickId);
    adminDashboardTickId = null;
  }

  adminDashboardTickId = setInterval(() => {
    if (!isAdminDashboardRoute()) {
      stopDashboardTimers();
      return;
    }
    const nowMs = Date.now();
    document.querySelectorAll('[data-elapsed][data-started-at]').forEach((el) => {
      const raw = el.getAttribute('data-started-at');
      if (!raw) return;
      const startedAt = Date.parse(raw);
      if (Number.isNaN(startedAt)) return;
      const secs = Math.floor((nowMs - startedAt) / 1000);
      el.textContent = formatDuration(secs);
    });
  }, 1000);
};

const attachRefreshAction = () => {
  const refreshBtn = document.getElementById('admin-dashboard-refresh');
  if (!refreshBtn) return;
  refreshBtn.onclick = async () => {
    refreshBtn.disabled = true;
    refreshBtn.innerHTML = '<i class="fa-solid fa-rotate fa-spin"></i> Refreshing';
    await refreshAndRender(false);
    refreshBtn.disabled = false;
    refreshBtn.innerHTML = '<i class="fa-solid fa-rotate"></i> Refresh';
  };
};

const refreshAndRender = async (showSkeleton = true) => {
  if (refreshInFlight) return;
  refreshInFlight = true;

  const appContent = document.getElementById('app-content');
  if (!appContent) {
    refreshInFlight = false;
    return;
  }

  try {
    if (showSkeleton) {
      appContent.innerHTML = getPageContentHTML('Admin Dashboard', buildSkeleton(), '<button id="admin-dashboard-refresh" class="btn btn-outline"><i class="fa-solid fa-rotate"></i> Refresh</button>');
    }

    const data = await loadAdminDashboardData();
    appContent.innerHTML = getPageContentHTML(
      'Admin Dashboard',
      buildDashboardLayout(data),
      '<button id="admin-dashboard-refresh" class="btn btn-outline"><i class="fa-solid fa-rotate"></i> Refresh</button>'
    );

    attachRefreshAction();
    startElapsedTick();
  } catch (err) {
    console.error('Failed to render admin dashboard', err);
    appContent.innerHTML = getPageContentHTML('Admin Dashboard', `
      <div class="card error-card">
        <h3>Unable to load admin dashboard</h3>
        <p class="placeholder-text">${escapeHtml(err?.message || 'Unexpected error')}</p>
      </div>
    `, '<button id="admin-dashboard-refresh" class="btn btn-outline"><i class="fa-solid fa-rotate"></i> Retry</button>');
    attachRefreshAction();
  } finally {
    refreshInFlight = false;
  }
};

export const renderAdminDashboardPage = async () => {
  stopDashboardTimers();
  bindLiveRefreshHooks();

  const appContent = document.getElementById('app-content');
  if (!appContent) return;

  if (!isAdminUser()) {
    appContent.innerHTML = getPageContentHTML('Admin Dashboard', `
      <div class="card access-denied-card">
        <i class="fa-solid fa-lock access-denied-icon"></i>
        <h2>Access Denied</h2>
        <p>Only administrators can access this dashboard.</p>
      </div>
    `);
    return;
  }

  await refreshAndRender(true);

  adminDashboardPollId = setInterval(async () => {
    if (!isAdminDashboardRoute()) {
      stopDashboardTimers();
      return;
    }
    await refreshAndRender(false);
  }, 15000);
};
