import { RoleLoginForm } from "@/components/auth/RoleLoginForm";

export default function LoginPage() {
  return (
    <RoleLoginForm
      portal="doctor"
      title="Sign in"
      subtitle="Access your clinical workspace with your doctor account or Gmail."
      showGoogle
      showSignupLink
    />
  );
}
