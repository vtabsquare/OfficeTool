// faceAuthSettings.js - FaceAuth Settings page for admin to manage face verification requirements

import { state } from '../state.js';
import { getPageContentHTML } from '../utils.js';
import { isAdminUser } from '../utils/accessControl.js';
import { API_BASE_URL } from '../features/accessHelpers.js';

let cachedEmployees = [];
let isLoading = false;

async function fetchFaceAuthSettings() {
    try {
        const base = API_BASE_URL.replace(/\/$/, '');
        const res = await fetch(`${base}/api/faceauth-settings`, {
            method: 'GET',
            headers: { 'Content-Type': 'application/json' }
        });
        
        if (!res.ok) {
            throw new Error(`Failed to fetch: ${res.status}`);
        }
        
        const data = await res.json();
        return data.employees || [];
    } catch (error) {
        console.error('[FACEAUTH-SETTINGS] Error fetching:', error);
        return [];
    }
}

async function updateFaceAuthSetting(employeeId, faceAuthRequired) {
    try {
        const base = API_BASE_URL.replace(/\/$/, '');
        const res = await fetch(`${base}/api/faceauth-settings/${employeeId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ face_auth_required: faceAuthRequired })
        });
        
        if (!res.ok) {
            throw new Error(`Failed to update: ${res.status}`);
        }
        
        const data = await res.json();
        return data.success;
    } catch (error) {
        console.error('[FACEAUTH-SETTINGS] Error updating:', error);
        return false;
    }
}

function renderEmployeeRow(emp) {
    const isEnabled = emp.face_auth_required;
    const statusClass = isEnabled ? 'text-green-600' : 'text-gray-500';
    const statusText = isEnabled ? 'Required' : 'Not Required';
    const toggleClass = isEnabled ? 'bg-green-500' : 'bg-gray-300';
    const togglePosition = isEnabled ? 'translate-x-5' : 'translate-x-0';
    
    return `
        <tr class="border-b border-gray-100 hover:bg-gray-50 transition-colors" data-employee-id="${emp.employee_id}">
            <td class="px-4 py-3">
                <div class="flex items-center gap-3">
                    <div class="w-9 h-9 rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center text-white text-sm font-medium">
                        ${(emp.name || 'U').charAt(0).toUpperCase()}
                    </div>
                    <div>
                        <div class="font-medium text-gray-900">${emp.name || 'Unknown'}</div>
                        <div class="text-xs text-gray-500">${emp.email || ''}</div>
                    </div>
                </div>
            </td>
            <td class="px-4 py-3 text-gray-600">${emp.employee_id || '-'}</td>
            <td class="px-4 py-3">
                <span class="inline-flex items-center gap-1.5 ${statusClass}">
                    <span class="w-2 h-2 rounded-full ${isEnabled ? 'bg-green-500' : 'bg-gray-400'}"></span>
                    ${statusText}
                </span>
            </td>
            <td class="px-4 py-3">
                <button 
                    class="faceauth-toggle relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 ${toggleClass}"
                    data-employee-id="${emp.employee_id}"
                    data-enabled="${isEnabled}"
                    title="${isEnabled ? 'Click to disable face verification' : 'Click to enable face verification'}"
                >
                    <span class="inline-block h-4 w-4 transform rounded-full bg-white shadow-lg transition-transform ${togglePosition}"></span>
                </button>
            </td>
        </tr>
    `;
}

function renderTable(employees) {
    if (!employees || employees.length === 0) {
        return `
            <div class="text-center py-12 text-gray-500">
                <svg class="w-16 h-16 mx-auto mb-4 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z"/>
                </svg>
                <p>No employees found</p>
            </div>
        `;
    }
    
    const rows = employees.map(emp => renderEmployeeRow(emp)).join('');
    
    return `
        <div class="overflow-x-auto">
            <table class="w-full">
                <thead>
                    <tr class="bg-gray-50 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                        <th class="px-4 py-3">Employee</th>
                        <th class="px-4 py-3">ID</th>
                        <th class="px-4 py-3">Face Auth Status</th>
                        <th class="px-4 py-3">Toggle</th>
                    </tr>
                </thead>
                <tbody id="faceauth-employees-tbody">
                    ${rows}
                </tbody>
            </table>
        </div>
    `;
}

async function handleToggleClick(e) {
    const btn = e.target.closest('.faceauth-toggle');
    if (!btn) return;
    
    const employeeId = btn.dataset.employeeId;
    const currentEnabled = btn.dataset.enabled === 'true';
    const newEnabled = !currentEnabled;
    
    // Disable button during update
    btn.disabled = true;
    btn.classList.add('opacity-50', 'cursor-not-allowed');
    
    const success = await updateFaceAuthSetting(employeeId, newEnabled);
    
    if (success) {
        // Update the cached data
        const emp = cachedEmployees.find(e => e.employee_id === employeeId);
        if (emp) {
            emp.face_auth_required = newEnabled;
        }
        
        // Re-render the row
        const row = document.querySelector(`tr[data-employee-id="${employeeId}"]`);
        if (row) {
            row.outerHTML = renderEmployeeRow({ ...emp, face_auth_required: newEnabled });
        }
        
        // Show success toast
        showToast(`Face verification ${newEnabled ? 'enabled' : 'disabled'} for ${emp?.name || employeeId}`, 'success');
    } else {
        // Re-enable button on failure
        btn.disabled = false;
        btn.classList.remove('opacity-50', 'cursor-not-allowed');
        showToast('Failed to update setting', 'error');
    }
}

function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    const bgColor = type === 'success' ? 'bg-green-500' : type === 'error' ? 'bg-red-500' : 'bg-blue-500';
    
    toast.className = `fixed bottom-4 right-4 ${bgColor} text-white px-6 py-3 rounded-lg shadow-lg z-50 transform transition-all duration-300 translate-y-0 opacity-100`;
    toast.textContent = message;
    
    document.body.appendChild(toast);
    
    setTimeout(() => {
        toast.classList.add('translate-y-2', 'opacity-0');
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

export async function renderFaceAuthSettings() {
    const container = document.getElementById('app-content');
    if (!container) return;
    
    // Check admin access
    if (!isAdminUser()) {
        container.innerHTML = getPageContentHTML(`
            <div class="text-center py-12">
                <svg class="w-16 h-16 mx-auto mb-4 text-red-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/>
                </svg>
                <h2 class="text-xl font-semibold text-gray-700 mb-2">Access Denied</h2>
                <p class="text-gray-500">Only administrators can access FaceAuth settings.</p>
            </div>
        `);
        return;
    }
    
    // Show loading state
    container.innerHTML = getPageContentHTML(`
        <div class="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
            <div class="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
                <div>
                    <h1 class="text-xl font-semibold text-gray-900 flex items-center gap-2">
                        <svg class="w-6 h-6 text-indigo-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"/>
                        </svg>
                        FaceAuth Settings
                    </h1>
                    <p class="text-sm text-gray-500 mt-1">Manage face verification requirements for employees</p>
                </div>
            </div>
            <div class="p-6">
                <div class="flex items-center justify-center py-12">
                    <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-500"></div>
                    <span class="ml-3 text-gray-500">Loading employees...</span>
                </div>
            </div>
        </div>
    `);
    
    // Fetch data
    isLoading = true;
    cachedEmployees = await fetchFaceAuthSettings();
    isLoading = false;
    
    // Render full page
    container.innerHTML = getPageContentHTML(`
        <div class="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
            <div class="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
                <div>
                    <h1 class="text-xl font-semibold text-gray-900 flex items-center gap-2">
                        <svg class="w-6 h-6 text-indigo-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"/>
                        </svg>
                        FaceAuth Settings
                    </h1>
                    <p class="text-sm text-gray-500 mt-1">Manage face verification requirements for employees</p>
                </div>
                <div class="flex items-center gap-3">
                    <span class="text-sm text-gray-500">${cachedEmployees.length} employees</span>
                    <button id="refresh-faceauth-btn" class="px-3 py-1.5 text-sm bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors flex items-center gap-1.5">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>
                        </svg>
                        Refresh
                    </button>
                </div>
            </div>
            
            <div class="p-4 bg-amber-50 border-b border-amber-100">
                <div class="flex items-start gap-3">
                    <svg class="w-5 h-5 text-amber-500 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
                    </svg>
                    <div class="text-sm text-amber-800">
                        <p class="font-medium">About Face Verification</p>
                        <p class="mt-1">When enabled, employees must verify their face during login. Disable for employees without camera access.</p>
                    </div>
                </div>
            </div>
            
            <div id="faceauth-table-container">
                ${renderTable(cachedEmployees)}
            </div>
        </div>
    `);
    
    // Add event listeners
    document.addEventListener('click', handleToggleClick);
    
    const refreshBtn = document.getElementById('refresh-faceauth-btn');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', async () => {
            refreshBtn.disabled = true;
            refreshBtn.innerHTML = `
                <svg class="w-4 h-4 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>
                </svg>
                Refreshing...
            `;
            
            cachedEmployees = await fetchFaceAuthSettings();
            
            const tableContainer = document.getElementById('faceauth-table-container');
            if (tableContainer) {
                tableContainer.innerHTML = renderTable(cachedEmployees);
            }
            
            refreshBtn.disabled = false;
            refreshBtn.innerHTML = `
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>
                </svg>
                Refresh
            `;
            
            showToast('Settings refreshed', 'success');
        });
    }
}

export function cleanupFaceAuthSettings() {
    document.removeEventListener('click', handleToggleClick);
}
