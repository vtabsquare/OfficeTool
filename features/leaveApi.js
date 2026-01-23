// features/leaveApi.js
import { API_BASE_URL } from '../config.js';
import { state } from '../state.js';
import { timedFetch } from './timedFetch.js';

const BASE_URL = API_BASE_URL.replace(/\/$/, '');
const CACHE_TTL_MS = 2 * 60 * 1000; // 2 minutes
const toKey = (id) => String(id || '').toUpperCase();

export async function fetchEmployeeLeaves(employeeId, forceRefresh = false) {
  try {
    const key = toKey(employeeId);
    const now = Date.now();
    const cached = state?.cache?.leaves?.[key];
    
    // Bypass cache if forceRefresh is true
    if (!forceRefresh && cached && now - cached.fetchedAt < CACHE_TTL_MS) {
      return cached.data;
    }

    const res = await timedFetch(`${BASE_URL}/api/leaves/${key}`, {
      cache: 'no-store'
    }, 'fetchEmployeeLeaves');
    if (!res.ok) {
      console.error(`❌ HTTP Error: ${res.status} ${res.statusText}`);
      throw new Error(`Failed to fetch leaves: ${res.status} ${res.statusText}`);
    }
    const data = await res.json();
    if (!data.success) {
      console.error('❌ API returned error:', data.error);
      throw new Error(data.error || 'Failed to fetch leaves');
    }
    const leaves = data.leaves || [];
    try {
      if (state?.cache?.leaves) {
        state.cache.leaves[key] = { data: leaves, fetchedAt: now };
      }
    } catch { /* ignore cache errors */ }
    console.log(`✅ Successfully fetched ${leaves.length} leave records`);
    return leaves;
  } catch (error) {
    console.error('❌ Error in fetchEmployeeLeaves:', error);
    throw error;
  }
}

export async function applyLeave(leaveData) {
  const res = await fetch(`${BASE_URL}/api/apply-leave`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(leaveData)
  });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.error || 'Failed to apply leave');
  }
  try {
    const key = toKey(leaveData?.employee_id || leaveData?.employeeId || leaveData?.employeeID);
    if (key && state?.cache?.leaves) {
      delete state.cache.leaves[key];
    }
  } catch { /* ignore cache errors */ }
  return data;
}

// Aggregated team leaves endpoint
export async function fetchTeamLeavesBatch(employeeIds = []) {
  const ids = employeeIds.filter(Boolean).map(toKey);
  if (!ids.length) return [];
  const qs = new URLSearchParams();
  qs.set('employee_ids', ids.join(','));
  const res = await timedFetch(`${BASE_URL}/api/leaves/team?${qs.toString()}`, {}, 'fetchTeamLeavesBatch');
  const data = await res.json();
  if (!res.ok || !data.success) {
    throw new Error(data.error || 'Failed to fetch team leaves');
  }
  return data.leaves || [];
}

export async function fetchOnLeaveToday(employeeIds = []) {
  const ids = employeeIds.filter(Boolean).map(toKey);
  const qs = new URLSearchParams();
  if (ids.length) qs.set('employee_ids', ids.join(','));
  const res = await timedFetch(`${BASE_URL}/api/leaves/on-leave-today?${qs.toString()}`, {}, 'fetchOnLeaveToday');
  const data = await res.json();
  if (!res.ok || !data.success) {
    throw new Error(data.error || 'Failed to fetch on-leave-today');
  }
  return data.leaves || [];
}

export async function fetchLeaveBalance(employeeId, leaveType) {
  // Try path style first, then query fallback
  let res = await fetch(`${BASE_URL}/api/leave-balance/${encodeURIComponent(employeeId)}/${encodeURIComponent(leaveType)}`);
  if (!res.ok) {
    res = await fetch(`${BASE_URL}/api/leave-balance?employee_id=${encodeURIComponent(employeeId)}&leave_type=${encodeURIComponent(leaveType)}`);
  }
  if (!res.ok) {
    throw new Error(`Failed to fetch leave balance: ${res.status}`);
  }
  const data = await res.json();
  if (!data.success) {
    throw new Error(data.error || 'Failed to fetch leave balance');
  }
  return data.available || 0;
}

export async function fetchAllLeaveBalances(employeeId) {
  try {
    console.log(`🔄 Fetching all leave balances for employee: ${employeeId}`);
    const res = await fetch(`${BASE_URL}/api/leave-balance/all/${encodeURIComponent(employeeId)}`, {
      cache: 'no-store'
    });
    
    if (!res.ok) {
      console.error(`❌ HTTP Error: ${res.status} ${res.statusText}`);
      throw new Error(`Failed to fetch leave balances: ${res.status}`);
    }
    
    const data = await res.json();
    if (!data.success) {
      console.error('❌ API returned error:', data.error);
      throw new Error(data.error || 'Failed to fetch leave balances');
    }
    
    console.log(`✅ Successfully fetched leave balances:`, data.balances);
    return data.balances || [];
  } catch (error) {
    console.error('❌ Error in fetchAllLeaveBalances:', error);
    throw error;
  }
}

export async function fetchPendingLeaves() {
  try {
    console.log('🔄 Fetching pending leave requests...');
    const res = await fetch(`${BASE_URL}/api/leaves/pending`, {
      cache: 'no-store'
    });
    
    if (!res.ok) {
      console.error(`❌ HTTP Error: ${res.status} ${res.statusText}`);
      throw new Error(`Failed to fetch pending leaves: ${res.status} ${res.statusText}`);
    }
    
    const data = await res.json();
    if (!data.success) {
      console.error('❌ API returned error:', data.error);
      throw new Error(data.error || 'Failed to fetch pending leaves');
    }
    
    console.log(`✅ Successfully fetched ${data.leaves?.length || 0} pending leave requests`);
    return data.leaves || [];
  } catch (error) {
    console.error('❌ Error in fetchPendingLeaves:', error);
    throw error;
  }
}

export async function approveLeave(leaveId, approvedBy) {
  try {
    console.log(`✅ Approving leave: ${leaveId} by ${approvedBy}`);
    const res = await fetch(`${BASE_URL}/api/leaves/approve/${encodeURIComponent(leaveId)}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ approved_by: approvedBy })
    });
    
    const data = await res.json();
    
    if (!res.ok) {
      console.error(`❌ Failed to approve leave: ${res.status}`, data);
      throw new Error(data.error || 'Failed to approve leave');
    }
    
    if (!data.success) {
      console.error('❌ API returned error:', data.error);
      throw new Error(data.error || 'Failed to approve leave');
    }
    
    console.log(`✅ Leave ${leaveId} approved successfully`);
    return data;
  } catch (error) {
    console.error('❌ Error in approveLeave:', error);
    throw error;
  }
}

export async function rejectLeave(leaveId, rejectedBy, reason = '') {
  try {
    console.log(`❌ Rejecting leave: ${leaveId} by ${rejectedBy}`);
    if (reason) {
      console.log(`💬 Rejection reason: ${reason}`);
    }
    
    const res = await fetch(`${BASE_URL}/api/leaves/reject/${encodeURIComponent(leaveId)}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ 
        rejected_by: rejectedBy,
        reason: reason 
      })
    });
    
    const data = await res.json();
    
    if (!res.ok) {
      console.error(`❌ Failed to reject leave: ${res.status}`, data);
      throw new Error(data.error || 'Failed to reject leave');
    }
    
    if (!data.success) {
      console.error('❌ API returned error:', data.error);
      throw new Error(data.error || 'Failed to reject leave');
    }
    
    console.log(`✅ Leave ${leaveId} rejected successfully`);
    return data;
  } catch (error) {
    console.error('❌ Error in rejectLeave:', error);
    throw error;
  }
}
