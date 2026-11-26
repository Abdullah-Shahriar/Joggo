export const APP_NAME = "JOGGO";

export type UserRole = "doctor" | "admin" | "auditor";
export type UserStatus = "active" | "restricted";

export function getRoleHome(role: UserRole): string {
  if (role === "admin") return "/admin";
  if (role === "auditor") return "/admin/audit";
  return "/dashboard";
}
