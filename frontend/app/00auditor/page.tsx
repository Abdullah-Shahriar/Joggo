import { RoleLoginForm } from "@/components/auth/RoleLoginForm";

export default function SecretAuditorLoginPage() {
  return (
    <RoleLoginForm
      portal="auditor"
      badge="Compliance portal"
      title="Auditor sign in"
      subtitle="Authorized compliance auditors only. Read-only audit log access."
    />
  );
}
