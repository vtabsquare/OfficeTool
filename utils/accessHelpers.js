export const deriveRoleInfo = (payload = {}) => {
  const normalize = (val = '') => String(val || '').trim().toUpperCase();
  const allowed = new Set(['L1', 'L2', 'L3', 'L4']);

  const normalizeRole = (rawValue = '') => {
    const raw = normalize(rawValue);
    if (!raw) return '';
    if (allowed.has(raw)) return raw;
    const compact = raw.replace(/\s+/g, '');
    if (allowed.has(compact)) return compact;
    const levelMatch = raw.match(/L\s*([1-4])/);
    if (levelMatch) return `L${levelMatch[1]}`;
    const numericMatch = raw.match(/LEVEL\s*([1-4])/);
    if (numericMatch) return `L${numericMatch[1]}`;
    return '';
  };

  let role = normalizeRole(
    payload.access_level ||
    payload.accessLevel ||
    payload.access ||
    payload.role
  );
  if (!allowed.has(role)) {
    if (payload.is_admin) {
      role = 'L3';
    } else if (payload.is_manager) {
      role = 'L2';
    } else {
      const designation = String(payload.designation || '').toLowerCase();
      if (designation.includes('team lead') || designation.includes('lead')) {
        role = 'L4';
      } else if (designation.includes('admin') || designation.includes('hr')) {
        role = 'L3';
      } else if (designation.includes('manager')) {
        role = 'L2';
      } else {
        role = 'L1';
      }
    }
  }

  const isAdmin = Boolean(payload.is_admin || role === 'L3');
  const isManager = Boolean(payload.is_manager || role === 'L2' || role === 'L3');

  return { role, isAdmin, isManager };
};
