import type { Profile } from '../types';

const tenantAdministrators = new Set(['admin', 'ceo']);
const departmentOperators = new Set(['admin', 'ceo', 'manager', 'dept_head', 'division_head', 'c_suite']);

export interface Capabilities {
  configureTenant: boolean;
  manageUsers: boolean;
  operateDepartment: boolean;
  approveExecutiveWork: boolean;
  resetDemo: boolean;
}

export function capabilitiesFor(profile: Profile): Capabilities {
  const role = profile.role ?? 'employee';
  const tenantAdmin = tenantAdministrators.has(role);
  return {
    configureTenant: tenantAdmin,
    manageUsers: tenantAdmin,
    operateDepartment: departmentOperators.has(role),
    approveExecutiveWork: tenantAdmin,
    resetDemo: tenantAdmin,
  };
}

export function permittedDepartments(profile: Profile, available: string[]): string[] {
  if (tenantAdministrators.has(profile.role ?? 'employee')) return available;
  const allowed = new Set(profile.permitted_departments ?? []);
  return available.filter((department) => allowed.has(department));
}

