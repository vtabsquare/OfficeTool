import { state } from '../state.js';
import { getPageContentHTML } from '../utils.js';
import { getInternDetails, updateIntern, getInternProjects } from '../features/internApi.js';
import { updateEmployee } from '../features/employeeApi.js';

const formatDate = (iso) => {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleDateString('en-IN', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  } catch {
    return iso;
  }
};

const PHASE_FIELD_MAP = {
  unpaid: {
    duration: 'unpaid_duration',
    start: 'unpaid_start',
    end: 'unpaid_end',
    salary: null,
  },
  paid: {
    duration: 'paid_duration',
    start: 'paid_start',
    end: 'paid_end',
    salary: 'paid_salary',
  },
  probation: {
    duration: 'probation_duration',
    start: 'probation_start',
    end: 'probation_end',
    salary: 'probation_salary',
  },
  postprob: {
    duration: 'postprob_duration',
    start: 'postprob_start',
    end: 'postprob_end',
    salary: 'postprob_salary',
  },
};

const PHASE_ORDER = ['unpaid', 'paid', 'probation', 'postprob'];

const addMonthsToDate = (dateStr, months) => {
  if (!dateStr || !months) return '';
  const base = new Date(dateStr);
  if (Number.isNaN(base.getTime())) return '';
  const year = base.getFullYear();
  const month = base.getMonth();
  const day = base.getDate();
  const result = new Date(year, month + months, day);
  if (Number.isNaN(result.getTime())) return '';
  return result.toISOString().split('T')[0];
};

const addDaysToDate = (dateStr, days) => {
  if (!dateStr || !days) return '';
  const base = new Date(dateStr);
  if (Number.isNaN(base.getTime())) return '';
  base.setDate(base.getDate() + days);
  return base.toISOString().split('T')[0];
};

const getPhaseProgress = (phase) => {
  const msPerDay = 24 * 60 * 60 * 1000;
  const parseDate = (value) => {
    if (!value) return null;
    const d = new Date(value);
    return Number.isNaN(d.getTime()) ? null : d;
  };

  const start = parseDate(phase?.start);
  const end = parseDate(phase?.end);
  if (!start || !end || end < start) {
    return { completedDays: 0, totalDays: 0, percent: 0 };
  }

  const today = new Date();
  const totalDays = Math.max(1, Math.round((end - start) / msPerDay) + 1);

  let completedDays;
  if (today < start) {
    completedDays = 0;
  } else if (today > end) {
    completedDays = totalDays;
  } else {
    completedDays = Math.min(totalDays, Math.max(0, Math.round((today - start) / msPerDay) + 1));
  }

  const percent = totalDays > 0 ? Math.round((completedDays / totalDays) * 100) : 0;
  return { completedDays, totalDays, percent };
};

const renderProjectRow = (item) => {
  const taskName = item.task_name || item.task_id || 'Task';
  const taskId = item.task_id || '';
  const projectLabel = item.project_name || item.project_id || '';
  const status = (item.task_status || '').toString().trim();
  const due = item.due_date ? formatDate(item.due_date) : null;

  return `
    <div class="intern-project-row">
      <div class="intern-project-main">
        <div class="intern-project-name">${taskName}</div>
        <div class="intern-project-id">${taskId}</div>
        <div class="intern-project-tasks">Project: ${projectLabel || '—'}</div>
      </div>
      <div class="intern-project-meta">
        ${due ? `<div class="intern-project-assigned">Due ${due}</div>` : ''}
        ${status ? `<span class="status-pill">${status}</span>` : ''}
      </div>
    </div>
  `;
};

const renderPhaseCard = (phaseKey, phase) => {
  const duration = phase?.duration || '—';
  const start = phase?.start ? formatDate(phase.start) : '—';
  const end = phase?.end ? formatDate(phase.end) : '—';
  const salary = phase?.salary ? `₹ ${phase.salary}` : '—';

  const { completedDays, totalDays, percent } = getPhaseProgress(phase || {});

  let statusText = 'In Progress';
  if (totalDays > 0 && completedDays >= totalDays) {
    statusText = 'Completed';
  } else if (completedDays === 0) {
    statusText = 'Yet to Start';
  }
  const statusClass = statusText.toLowerCase().replace(/\s+/g, '-');

  return `
    <div class="intern-phase-card" data-phase-key="${phaseKey}">
      <div class="intern-phase-header">
        <h4>${phase?.title || phaseKey}</h4>
        <span class="status-pill status-${statusClass}">${statusText}</span>
      </div>
      <div class="intern-phase-body">
        <div><label>Duration</label><p>${duration}</p></div>
        <div><label>Start Date</label><p>${start}</p></div>
        <div><label>End Date</label><p>${end}</p></div>
        <div><label>Salary</label><p>${salary}</p></div>
        <div class="intern-phase-progress">
          <div class="intern-phase-progress-status status-${statusClass}">${statusText}</div>
          <div class="intern-phase-progress-bar">
            <div class="intern-phase-progress-fill status-${statusClass}" style="width: ${percent}%;"></div>
          </div>
          <div class="intern-phase-progress-scale">
            <span class="intern-phase-progress-scale-start">0</span>
            <span class="intern-phase-progress-scale-end">${totalDays || 0}</span>
          </div>
        </div>
      </div>
    </div>
  `;
};

const renderSummaryCard = (intern) => {
  return `
    <div class="intern-summary-card">
      <div class="intern-badge">${(intern.intern_id || '?').slice(0, 2)}</div>
      <div class="intern-summary-meta">
        <div class="intern-chip">Intern</div>
        <h2>${intern.intern_id || 'Intern'}</h2>
        <p class="intern-sub-meta">Employee ID: <strong>${intern.employee_id || '—'}</strong></p>
        <p class="intern-sub-meta">Created on: ${formatDate(intern.created_on)}</p>
      </div>
    </div>
  `;
};

const renderInfoList = (intern) => {
  const emp = intern.employee || {};
  const infoItems = [
    { label: 'Date Of Joining', value: emp.doj ? formatDate(emp.doj) : null },
    { label: 'Designation', value: emp.designation },
    { label: 'Department', value: emp.department },
    { label: 'Email', value: emp.email },
    { label: 'Contact Info', value: emp.contact_number },
  ];
  return infoItems
    .map((item) => {
      const value = item.value || '—';
      return `
        <div class="intern-info-row">
          <span>${item.label}</span>
          <strong>${value}</strong>
        </div>
      `;
    })
    .join('');
};

export const renderInternDetailPage = async (internId) => {
  const targetId = internId || state.selectedInternId;
  if (!targetId) {
    window.location.hash = '#/interns';
    return;
  }
  state.selectedInternId = targetId;

  const skeleton = `
    <div class="intern-detail-layout">
      <div class="intern-summary-card skeleton-card"></div>
      <div class="intern-phase-grid">
        ${Array.from({ length: 4 })
          .map(() => '<div class="intern-phase-card skeleton-card"></div>')
          .join('')}
      </div>
    </div>
  `;
  document.getElementById('app-content').innerHTML = getPageContentHTML('', skeleton, '');

  try {
    const intern = await getInternDetails(targetId);
    if (!intern) {
      document.getElementById('app-content').innerHTML = getPageContentHTML(
        '',
        `<div class="card error-card">Intern ${targetId} not found.</div>`,
        ''
      );
      return;
    }

    state.selectedIntern = intern;

    const phasesByKey = intern.phases || {};
    const phasesMarkup = PHASE_ORDER
      .map((key) => [key, phasesByKey[key]])
      .filter(([, phase]) => phase)
      .map(([key, phase]) => renderPhaseCard(key, phase))
      .join('');

    const infoList = renderInfoList(intern);

    const detailContent = `
      <div class="intern-detail-layout">
        <aside class="intern-detail-sidebar">
          ${renderSummaryCard(intern)}
          <div class="intern-info-header">
            <span class="intern-info-title">Details</span>
            <div class="intern-info-actions">
              <button id="intern-info-edit-btn" class="icon-btn icon-btn-sm" title="Edit intern info">
                <i class="fa-solid fa-pen"></i>
              </button>
              <button id="intern-info-save-btn" class="icon-btn icon-btn-sm" title="Save" style="display:none;">
                <i class="fa-solid fa-check"></i>
              </button>
              <button id="intern-info-cancel-btn" class="icon-btn icon-btn-sm" title="Cancel" style="display:none;">
                <i class="fa-solid fa-xmark"></i>
              </button>
            </div>
          </div>
          <div class="intern-info-list">
            ${infoList}
          </div>
        </aside>
        <section class="intern-detail-main">
          <div class="intern-detail-main-header">
            <div class="intern-detail-main-left">
              <button id="intern-detail-back" class="btn btn-ghost btn-sm">← Back to Interns</button>
              <div class="intern-breadcrumbs">
                <a href="#/interns" class="link-muted">Home</a>
                <span>›</span>
                <a href="#/interns" class="link-muted">Interns</a>
                <span>›</span>
                <span class="current">${intern.intern_id || 'Detail'}</span>
              </div>
            </div>
            <div class="intern-detail-actions">
              <button id="intern-edit-btn" class="btn btn-secondary btn-sm">Edit Phases</button>
              <button id="intern-save-btn" class="btn btn-primary btn-sm" style="display:none;">Save</button>
              <button id="intern-cancel-btn" class="btn btn-ghost btn-sm" style="display:none;">Cancel</button>
            </div>
          </div>
          <div class="intern-phase-grid">
            ${phasesMarkup}
          </div>
          <div class="intern-projects-card card">
            <div class="intern-projects-header">
              <h3>Tasks</h3>
            </div>
            <div class="intern-projects-body" id="intern-projects-body">
              <div class="placeholder-text">Loading tasks...</div>
            </div>
          </div>
        </section>
      </div>
    `;

    document.getElementById('app-content').innerHTML = getPageContentHTML('', detailContent, '');

    const loadInternTasks = async () => {
      const container = document.getElementById('intern-projects-body');
      if (!container) return;

      const empId = (intern.employee && (intern.employee.employee_id || intern.employee.employeeId)) || intern.employee_id;
      if (!empId) {
        container.innerHTML = '<div class="placeholder-text">No employee ID available.</div>';
        return;
      }

      try {
        const projects = await getInternProjects(empId);
        const allTasks = [];
        (projects || []).forEach((proj) => {
          (proj.tasks || []).forEach((t) => {
            allTasks.push({
              ...t,
              project_id: proj.project_id,
              project_name: proj.project_name,
            });
          });
        });

        if (!allTasks.length) {
          container.innerHTML = '<div class="placeholder-text">No tasks assigned.</div>';
          return;
        }

        const fullName = (intern.employee && intern.employee.full_name) || '';
        const empIdUpper = String(empId || '').toUpperCase();
        const fullNameLower = fullName.toLowerCase().trim();

        const matching = allTasks.filter((t) => {
          const asg = String(t.assigned_to || '');
          const asgUpper = asg.toUpperCase();
          const asgLower = asg.toLowerCase();
          if (empIdUpper && asgUpper.includes(empIdUpper)) return true;
          if (fullNameLower && asgLower.includes(fullNameLower)) return true;
          return false;
        });

        const tasksToShow = matching.length ? matching : allTasks;
        container.innerHTML = tasksToShow.map((t) => renderProjectRow(t)).join('');
      } catch (err) {
        console.error('Failed to load intern tasks', err);
        container.innerHTML = '<div class="placeholder-text">Unable to load tasks.</div>';
      }
    };

    loadInternTasks();

    const backBtn = document.getElementById('intern-detail-back');
    if (backBtn) {
      backBtn.addEventListener('click', (e) => {
        e.preventDefault();
        window.location.hash = '#/interns';
      });
    }

    const infoEditBtn = document.getElementById('intern-info-edit-btn');
    const infoSaveBtn = document.getElementById('intern-info-save-btn');
    const infoCancelBtn = document.getElementById('intern-info-cancel-btn');
    const infoListEl = document.querySelector('.intern-info-list');

    const enterInfoEditMode = () => {
      if (!infoListEl || !state.selectedIntern || !state.selectedIntern.employee) return;
      const emp = state.selectedIntern.employee || {};
      const dojIso = emp.doj ? String(emp.doj).split('T')[0] : '';

      infoListEl.innerHTML = `
        <div class="intern-info-row">
          <span>Date Of Joining</span>
          <input class="input-control" type="date" data-field="doj" value="${dojIso || ''}">
        </div>
        <div class="intern-info-row">
          <span>Designation</span>
          <input class="input-control" type="text" data-field="designation" value="${emp.designation || ''}">
        </div>
        <div class="intern-info-row">
          <span>Department</span>
          <input class="input-control" type="text" data-field="department" value="${emp.department || ''}">
        </div>
        <div class="intern-info-row">
          <span>Email</span>
          <input class="input-control" type="email" data-field="email" value="${emp.email || ''}">
        </div>
        <div class="intern-info-row">
          <span>Contact Info</span>
          <input class="input-control" type="text" data-field="contact_number" value="${emp.contact_number || ''}">
        </div>
      `;

      if (infoEditBtn && infoSaveBtn && infoCancelBtn) {
        infoEditBtn.style.display = 'none';
        infoSaveBtn.style.display = 'inline-flex';
        infoCancelBtn.style.display = 'inline-flex';
      }
    };

    const exitInfoEditMode = (updatedEmp) => {
      if (!infoListEl) return;
      if (updatedEmp) {
        state.selectedIntern = state.selectedIntern || {};
        state.selectedIntern.employee = {
          ...(state.selectedIntern.employee || {}),
          ...updatedEmp,
        };
      }
      const html = renderInfoList(state.selectedIntern);
      infoListEl.innerHTML = html;
      if (infoEditBtn && infoSaveBtn && infoCancelBtn) {
        infoEditBtn.style.display = 'inline-flex';
        infoSaveBtn.style.display = 'none';
        infoCancelBtn.style.display = 'none';
      }
    };

    if (infoEditBtn) {
      infoEditBtn.addEventListener('click', (e) => {
        e.preventDefault();
        enterInfoEditMode();
      });
    }

    if (infoCancelBtn) {
      infoCancelBtn.addEventListener('click', (e) => {
        e.preventDefault();
        exitInfoEditMode();
      });
    }

    if (infoSaveBtn) {
      infoSaveBtn.addEventListener('click', async (e) => {
        e.preventDefault();
        if (!state.selectedIntern || !state.selectedIntern.employee) {
          exitInfoEditMode();
          return;
        }
        const emp = state.selectedIntern.employee;
        const empId = emp.employee_id || state.selectedIntern.employee_id;
        if (!empId) {
          alert('Missing employee ID; cannot update.');
          return;
        }

        const getVal = (field) => {
          const el = infoListEl && infoListEl.querySelector(`input[data-field="${field}"]`);
          return el && el.value != null ? el.value.trim() : '';
        };

        const dojVal = getVal('doj');
        const payload = {
          designation: getVal('designation') || emp.designation || '',
          department: getVal('department') || emp.department || '',
          email: getVal('email') || emp.email || '',
          contact_number: getVal('contact_number') || emp.contact_number || '',
        };
        if (dojVal) {
          payload.doj = dojVal;
        }

        try {
          await updateEmployee(empId, payload);
          const updatedEmp = {
            ...emp,
            designation: payload.designation,
            department: payload.department,
            email: payload.email,
            contact_number: payload.contact_number,
            doj: dojVal || emp.doj,
          };
          exitInfoEditMode(updatedEmp);
        } catch (err) {
          console.error('Failed to update intern employee info', err);
          alert(err.message || 'Failed to update intern employee info');
        }
      });
    }

    const editBtn = document.getElementById('intern-edit-btn');
    const saveBtn = document.getElementById('intern-save-btn');
    const cancelBtn = document.getElementById('intern-cancel-btn');
    const phaseGrid = document.querySelector('.intern-phase-grid');

    const enterEditMode = () => {
      if (!phaseGrid || !state.selectedIntern) return;
      const phases = state.selectedIntern.phases || {};
      Object.entries(phases).forEach(([key, phase]) => {
        const card = phaseGrid.querySelector(`.intern-phase-card[data-phase-key="${key}"]`);
        if (!card) return;
        const body = card.querySelector('.intern-phase-body');
        if (!body) return;

        const durationVal = phase?.duration ?? '';
        const startVal = phase?.start ? String(phase.start).split('T')[0] : '';
        const endVal = phase?.end ? String(phase.end).split('T')[0] : '';
        const salaryVal = phase?.salary ?? '';

        const salaryInput = PHASE_FIELD_MAP[key]?.salary
          ? `<div><label>Salary</label><input class="input-control" type="number" data-phase="${key}" data-field="salary" value="${salaryVal || ''}"></div>`
          : '<div><label>Salary</label><p>—</p></div>';

        body.innerHTML = `
          <div><label>Duration</label><input class="input-control" type="text" data-phase="${key}" data-field="duration" value="${durationVal || ''}"></div>
          <div><label>Start Date</label><input class="input-control" type="date" data-phase="${key}" data-field="start" value="${startVal || ''}"></div>
          <div><label>End Date</label><input class="input-control" type="date" data-phase="${key}" data-field="end" value="${endVal || ''}"></div>
          ${salaryInput}
        `;

        // Auto-calculate end date when duration (months) and start date are provided
        const durationInput = body.querySelector(`input[data-phase="${key}"][data-field="duration"]`);
        const startInput = body.querySelector(`input[data-phase="${key}"][data-field="start"]`);
        const endInput = body.querySelector(`input[data-phase="${key}"][data-field="end"]`);

        const updateEndFromDuration = () => {
          if (!durationInput || !startInput || !endInput) return;
          const months = parseInt(durationInput.value, 10);
          const startDate = startInput.value && startInput.value.trim();
          if (!startDate || Number.isNaN(months) || months <= 0) return;
          const computed = addMonthsToDate(startDate, months);
          if (computed) {
            endInput.value = computed;
          }
        };

        if (durationInput) {
          durationInput.addEventListener('change', updateEndFromDuration);
          durationInput.addEventListener('blur', updateEndFromDuration);
        }
        if (startInput) {
          startInput.addEventListener('change', updateEndFromDuration);
          startInput.addEventListener('blur', updateEndFromDuration);
        }
      });

      // Ensure each phase's start date follows the previous phase's end date
      const linkPhaseDates = () => {
        for (let i = 1; i < PHASE_ORDER.length; i += 1) {
          const prevKey = PHASE_ORDER[i - 1];
          const curKey = PHASE_ORDER[i];
          const prevEnd = document.querySelector(`input[data-phase="${prevKey}"][data-field="end"]`);
          const curStart = document.querySelector(`input[data-phase="${curKey}"][data-field="start"]`);
          if (!prevEnd || !curStart) continue;

          const syncStart = () => {
            const endVal = prevEnd.value && prevEnd.value.trim();
            if (!endVal) return;
            const nextDay = addDaysToDate(endVal, 1);
            if (nextDay) {
              curStart.value = nextDay;
            }
          };

          // Initial sync when entering edit mode
          syncStart();

          // Keep in sync when previous end date changes
          prevEnd.addEventListener('change', syncStart);
          prevEnd.addEventListener('blur', syncStart);
        }
      };

      linkPhaseDates();

      if (editBtn && saveBtn && cancelBtn) {
        editBtn.style.display = 'none';
        saveBtn.style.display = 'inline-flex';
        cancelBtn.style.display = 'inline-flex';
      }
    };

    const exitEditMode = (updatedIntern) => {
      const current = updatedIntern || state.selectedIntern;
      if (!current || !phaseGrid) return;
      const phasesByKey = current.phases || {};
      const markup = PHASE_ORDER
        .map((key) => [key, phasesByKey[key]])
        .filter(([, phase]) => phase)
        .map(([key, phase]) => renderPhaseCard(key, phase))
        .join('');
      phaseGrid.innerHTML = markup;
      if (editBtn && saveBtn && cancelBtn) {
        editBtn.style.display = 'inline-flex';
        saveBtn.style.display = 'none';
        cancelBtn.style.display = 'none';
      }
    };

    if (editBtn) {
      editBtn.addEventListener('click', (e) => {
        e.preventDefault();
        enterEditMode();
      });
    }

    if (cancelBtn) {
      cancelBtn.addEventListener('click', (e) => {
        e.preventDefault();
        exitEditMode();
      });
    }

    if (saveBtn) {
      saveBtn.addEventListener('click', async (e) => {
        e.preventDefault();
        if (!state.selectedIntern) return;

        const payload = {};
        Object.entries(PHASE_FIELD_MAP).forEach(([phaseKey, fieldCfg]) => {
          Object.entries(fieldCfg).forEach(([fieldName, friendly]) => {
            if (!friendly) return;
            const input = document.querySelector(`input[data-phase="${phaseKey}"][data-field="${fieldName}"]`);
            if (!input) return;
            const raw = input.value && input.value.trim();
            if (raw) {
              payload[friendly] = raw;
            }
          });
        });

        if (!Object.keys(payload).length) {
          alert('Please enter at least one value to update.');
          return;
        }

        try {
          const updated = await updateIntern(state.selectedIntern.intern_id, payload);
          state.selectedIntern = updated;

          // Check if post probation phase is completed
          const postProb = updated.phases?.postprob;
          if (postProb) {
            const { completedDays, totalDays } = getPhaseProgress(postProb);
            if (totalDays > 0 && completedDays >= totalDays) {
              // Post probation completed - update employee flag
              const empId = updated.employee_id;
              if (empId) {
                await updateEmployee(empId, { employee_flag: 'Employee' });
              }
            }
          }

          exitEditMode(updated);
        } catch (err) {
          console.error('Failed to update intern phases', err);
          alert(err.message || 'Failed to update intern phases');
        }
      });
    }
  } catch (err) {
    console.error('Failed to load intern detail', err);
    document.getElementById('app-content').innerHTML = getPageContentHTML(
      '',
      `<div class="card error-card">${err.message || 'Unable to load intern details.'}</div>`,
      ''
    );
  }
};
