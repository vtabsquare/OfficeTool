import { state } from "../state.js";
import { getPageContentHTML } from "../utils.js";
import { renderModal, closeModal } from "../components/modal.js";
import { notifyAdminCompOffRequest } from "../features/notificationApi.js";
import { API_BASE_URL } from '../config.js';


const API_BASE = API_BASE_URL;

// -------------------------------------------------------------
// 🔹 Fetch Comp Off Data from Backend
// -------------------------------------------------------------
export const fetchCompOffData = async () => {
  try {
    const response = await fetch(`${API_BASE}/api/comp-off`);
    const result = await response.json();

    if (result.status === "success") {
      // ✅ Map backend fields to frontend format
      state.compOffs = result.data.map((item) => ({
        employeeId: item.employee_id,
        employeeName: item.employee_name,
        availableDays: item.available_compoff,
      }));
    } else {
      console.error("Failed to load comp off data:", result.message);
      state.compOffs = [];
    }
  } catch (err) {
    console.error("Error fetching comp off data:", err);
    state.compOffs = [];
  }
};

const getCompOffContentHTML = () => {
  const tableRows = state.compOffs
    .map(
      (co) => `
        <tr>
            <td>${co.employeeName}</td>
            <td>${co.employeeId}</td>
            <td>${co.availableDays}</td>
            <td>
                <button class="btn btn-secondary edit-compoff-balance-btn" data-id="${co.employeeId}" aria-label="Edit balance">
                    <i class="fa-solid fa-pen-to-square"></i>
                </button>
            </td>
        </tr>
    `
    )
    .join("");

  const requestRows = state.compOffRequests
    .filter((req) => req.employeeId === state.user.id)
    .map(
      (req) => `
         <tr>
            <td>${req.dateWorked}</td>
            <td>${req.reason}</td>
            <td><span class="status-badge ${req.status.toLowerCase()}">${req.status
        }</span></td>
            <td>${req.appliedDate}</td>
            <td>
                <button class="btn btn-secondary edit-compoff-btn" data-id="${req.id
        }" aria-label="Edit request">
                    <i class="fa-solid fa-pen-to-square"></i>
                </button>
            </td>
        </tr>
    `
    )
    .join("");

  return `
        <div class="card">
            <h3 style="margin-bottom: 1.5rem;">Compensatory Off Balance</h3>
            <div class="table-container">
                <table class="table">
                    <thead>
                        <tr>
                            <th>Employee Name</th>
                            <th>Employee ID</th>
                            <th>Available Comp Off (Days)</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${tableRows ||
    `<tr><td colspan="3" class="placeholder-text">No comp off data available.</td></tr>`
    }
                    </tbody>
                </table>
            </div>
        </div>
        <div class="card" style="margin-top: 1.5rem;">
            <h3 style="margin-bottom: 1.5rem;">My Comp Off Requests</h3>
            <div class="table-container">
                <table class="table">
                    <thead>
                        <tr>
                            <th>Date Worked</th>
                            <th>Reason</th>
                            <th>Status</th>
                            <th>Applied Date</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${requestRows ||
    `<tr><td colspan="4" class="placeholder-text">No comp off requests found.</td></tr>`
    }
                    </tbody>
                </table>
            </div>
        </div>
    `;
};

export const renderCompOffPage = async () => {
  // 1️⃣ Show loading text
  document.getElementById("app-content").innerHTML = `
    <div class="loading-screen">
      <p>Loading Comp Off data...</p>
    </div>
  `;

  // 2️⃣ Clear old data before reloading
  state.compOffs = [];

  // 3️⃣ Fetch from backend
  await fetchCompOffData();

  // 4️⃣ Render actual content
  const controls = `
    <button id="request-compoff-btn" class="btn btn-primary">
      <i class="fa-solid fa-plus"></i> REQUEST COMP OFF
    </button>
  `;
  const content = getCompOffContentHTML();

  document.getElementById("app-content").innerHTML = getPageContentHTML(
    "Compensatory Off",
    content,
    controls
  );

  // 5️⃣ Attach button events AFTER render
  document
    .getElementById("request-compoff-btn")
    ?.addEventListener("click", showRequestCompOffModal);

  document.querySelectorAll(".edit-compoff-balance-btn").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      const empId = e.currentTarget.dataset.id;
      showEditCompOffBalanceModal(empId);
    });
  });
};


// export const renderCompOffPage = () => {
//      fetchCompOffData();
//   const controls = `<button id="request-compoff-btn" class="btn btn-primary"><i class="fa-solid fa-plus"></i> REQUEST COMP OFF</button>`;
//   const content = getCompOffContentHTML();
//   document.getElementById("app-content").innerHTML = getPageContentHTML(
//     "Compensatory Off",
//     content,
//     controls
//   );
// };

export const showRequestCompOffModal = () => {
  const formHTML = `
        <div class="modal-form modern-form compoff-form">
            <div class="form-section">
                <div class="form-section-header">
                    <div>
                        <p class="form-eyebrow">COMP OFF</p>
                        <h3>Request compensatory off</h3>
                    </div>
                </div>
                <div class="form-grid two-col">
                    <div class="form-group">
                        <i class="fa-solid fa-calendar-check"></i>
                        <input type="date" id="dateWorked" placeholder=" " required>
                        <label for="dateWorked">Date Worked</label>
                    </div>
                    <div class="form-group" style="grid-column: 1 / -1;">
                        <i class="fa-solid fa-comment"></i>
                        <textarea id="reason" rows="3" placeholder=" " required></textarea>
                        <label for="reason">Reason</label>
                    </div>
                </div>
            </div>
        </div>
    `;
  renderModal("Request Compensatory Off", formHTML, "submit-compoff-btn");
};

export const handleRequestCompOff = (e) => {
  e.preventDefault();

  const newRequest = {
    id: state.compOffRequests.length + 1,
    employeeId: state.user.id,
    employeeName: state.user.name,
    dateWorked: document.getElementById("dateWorked").value,
    reason: document.getElementById("reason").value,
    status: "Pending",
    appliedDate: new Date().toISOString().split("T")[0],
  };

  state.compOffRequests.unshift(newRequest);
  try { notifyAdminCompOffRequest(newRequest); } catch { }
  closeModal();
  renderCompOffPage();
};

export const showEditCompOffBalanceModal = (employeeId) => {
  const compOff = state.compOffs.find((co) => co.employeeId === employeeId);
  if (!compOff) return;

  const formHTML = `
        <div class="modal-form modern-form compoff-form">
            <div class="form-section">
                <div class="form-section-header">
                    <div>
                        <p class="form-eyebrow">COMP OFF</p>
                        <h3>Edit comp off balance</h3>
                    </div>
                </div>
                <input type="hidden" id="editCompOffEmployeeId" value="${employeeId}">
                <div class="form-grid two-col">
                    <div class="form-group">
                        <i class="fa-solid fa-user"></i>
                        <input type="text" id="employeeName" value="${compOff.employeeName}" placeholder=" " readonly>
                        <label for="employeeName">Employee Name</label>
                    </div>
                    <div class="form-group">
                        <i class="fa-solid fa-calendar-days"></i>
                        <input type="number" step="0.5" id="availableDays" value="${compOff.availableDays}" placeholder=" " required>
                        <label for="availableDays">Available Comp Off Days</label>
                    </div>
                </div>
            </div>
        </div>
    `;
  renderModal(`Edit Comp Off Balance`, formHTML, "update-compoff-balance-btn");
};

export const handleUpdateCompOffBalance = async (e) => {
  e.preventDefault();

  const employeeId = document.getElementById("editCompOffEmployeeId").value;
  const newBalance = parseFloat(document.getElementById("availableDays").value);

  if (isNaN(newBalance) || newBalance < 0) {
    alert("Please enter a valid non-negative number.");
    return;
  }

  try {
    // 🔹 Send update request to backend
    const response = await fetch(`${API_BASE}/api/comp-off/${employeeId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ available_compoff: newBalance }),
    });

    const result = await response.json();

    if (result.status === "success") {
      alert("✅ Comp Off balance updated successfully!");
      closeModal();
      await renderCompOffPage(); // reload latest data
    } else {
      alert("❌ Failed: " + result.message);
    }
  } catch (err) {
    console.error("Error updating comp off:", err);
    alert("Error connecting to server.");
  }
};


