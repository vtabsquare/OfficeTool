import { API_BASE_URL } from '../config.js';

const BASE_URL = API_BASE_URL.replace(/\/$/, '');

const withQuery = (path, params = {}) => {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') return;
    qs.set(key, String(value));
  });
  const query = qs.toString();
  return `${BASE_URL}${path}${query ? `?${query}` : ''}`;
};

const normalizeRequest = (item = {}) => ({
  id: item.id || item.request_id || item.requestId || '',
  employeeId: item.employeeId || item.employee_id || '',
  employeeName: item.employeeName || item.employee_name || '',
  dateWorked: item.dateWorked || item.date_worked || '',
  reason: item.reason || '',
  status: item.status || 'Pending',
  appliedDate: item.appliedDate || item.applied_date || '',
  rejectionReason: item.rejectionReason || item.rejection_reason || '',
  totalDays: Number(item.totalDays ?? item.total_days ?? 1) || 1,
});

export const fetchCompOffRequests = async (filters = {}) => {
  const url = withQuery('/api/comp-off/requests', {
    status: filters.status,
    employee_id: filters.employeeId,
  });
  const response = await fetch(url, { cache: 'no-store' });
  const data = await response.json().catch(() => ({}));
  if (!response.ok || !data.success) {
    throw new Error(data.error || data.message || 'Failed to fetch comp off requests');
  }
  return (data.requests || []).map(normalizeRequest);
};

export const createCompOffRequest = async (requestData = {}) => {
  const response = await fetch(`${BASE_URL}/api/comp-off/requests`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(requestData),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok || !data.success) {
    throw new Error(data.error || data.message || 'Failed to create comp off request');
  }
  return normalizeRequest(data.request || requestData);
};

export const approveCompOffRequest = async (requestId, approvedBy) => {
  const response = await fetch(`${BASE_URL}/api/comp-off/requests/${encodeURIComponent(requestId)}/approve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ approved_by: approvedBy }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok || !data.success) {
    throw new Error(data.error || data.message || 'Failed to approve comp off request');
  }
  return data;
};

export const rejectCompOffRequest = async (requestId, rejectedBy, reason = '') => {
  const response = await fetch(`${BASE_URL}/api/comp-off/requests/${encodeURIComponent(requestId)}/reject`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ rejected_by: rejectedBy, reason }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok || !data.success) {
    throw new Error(data.error || data.message || 'Failed to reject comp off request');
  }
  return data;
};
