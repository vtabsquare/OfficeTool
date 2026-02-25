import { state } from '../state.js';

const ADMIN_EMP_IDS = ['EMP001'];
const ADMIN_EMAILS = ['bala.t@vtab.com'];

const normalizeRole = (value) => {
  const val = String(value || '').trim().toUpperCase();
  if (['L1', 'L2', 'L3', 'L4'].includes(val)) {
    return val;
  }
  const compact = val.replace(/\s+/g, '');
  if (['L1', 'L2', 'L3', 'L4'].includes(compact)) {
    return compact;
  }
  const levelMatch = val.match(/L\s*([1-4])/);
  if (levelMatch) {
    return `L${levelMatch[1]}`;
  }
  const numericMatch = val.match(/LEVEL\s*([1-4])/);
  if (numericMatch) {
    return `L${numericMatch[1]}`;
  }
  return '';
};

export const getUserAccessContext = () => {
  let persistedRole = '';
  let persistedAuthUser = null;
  try {
    persistedRole = localStorage.getItem('role') || '';
    const rawAuth = localStorage.getItem('auth');
    if (rawAuth) {
      const parsed = JSON.parse(rawAuth);
      persistedAuthUser = parsed?.user || null;
    }
  } catch {
    persistedRole = '';
    persistedAuthUser = null;
  }

  const role = normalizeRole(
    state.user?.access_level ||
    state.user?.accessLevel ||
    state.user?.access ||
    state.user?.role ||
    persistedAuthUser?.access_level ||
    persistedAuthUser?.accessLevel ||
    persistedAuthUser?.access ||
    persistedAuthUser?.role ||
    persistedRole
  );
  const empId = String(state.user?.id || '').trim().toUpperCase();
  const email = String(state.user?.email || '').trim().toLowerCase();
  const designation = String(state.user?.designation || '').trim().toLowerCase();

  const isAdminFromFallback = ADMIN_EMP_IDS.includes(empId) || ADMIN_EMAILS.includes(email);
  const isAdminByRole = role === 'L3';
  const isManagerByRole = role === 'L2' || role === 'L3';

  const isAdmin = Boolean(state.user?.is_admin || isAdminByRole || isAdminFromFallback);
  const isManager = Boolean(state.user?.is_manager || isManagerByRole);

  let derivedRole = role;
  if (!derivedRole) {
    if (isAdmin) derivedRole = 'L3';
    else if (isManager) derivedRole = 'L2';
    else if (designation.includes('team lead') || designation.includes('lead')) derivedRole = 'L4';
    else derivedRole = 'L1';
  }

  return {
    role: derivedRole,
    empId,
    email,
    isAdmin,
    isManager,
  };
};

export const isAdminUser = () => getUserAccessContext().isAdmin;

export const isL2OrL3User = () => {
  const { role, isAdmin } = getUserAccessContext();
  return isAdmin || role === 'L2' || role === 'L3';
};

export const isManagerOrAdmin = () => {
  const { isAdmin, isManager } = getUserAccessContext();
  return isAdmin || isManager;
};

export const isL3User = () => {
  const { role, isAdmin } = getUserAccessContext();
  if (isAdmin || role === 'L3') return true;
  const designation = String(state.user?.designation || '').trim().toLowerCase();
  if (!designation) return false;
  return designation.includes('hr') || designation.includes('manager');
};

export const isTeamLeadUser = () => getUserAccessContext().role === 'L4';
