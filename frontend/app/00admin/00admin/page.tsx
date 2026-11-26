import { RoleLoginForm } from "@/components/auth/RoleLoginForm";

export default function SecretAdminLoginPage() {
  return (
    <RoleLoginForm
      portal="admin"
      badge="Restricted portal"
      title="Administrator sign in"
      subtitle="Authorized administrators only. Doctor and auditor accounts cannot sign in here."
    />
  );
}
