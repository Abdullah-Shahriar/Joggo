export function BrandLoader({
  label = "Loading…",
  fullScreen = false,
}: {
  label?: string;
  fullScreen?: boolean;
}) {
  return (
    <div
      role="status"
      aria-live="polite"
      className={
        fullScreen
          ? "flex min-h-[60vh] flex-col items-center justify-center gap-3 px-4"
          : "flex flex-col items-center justify-center gap-3 py-12"
      }
    >
      <div className="relative h-14 w-14">
        <svg
          aria-hidden="true"
          className="cs-brand-ring absolute inset-0 h-14 w-14 text-accent"
          viewBox="0 0 56 56"
          fill="none"
        >
          <circle
            cx="28"
            cy="28"
            r="25"
            stroke="#E5E7EB"
            strokeWidth="2"
          />
          <circle
            cx="28"
            cy="28"
            r="25"
            stroke="currentColor"
            strokeWidth="2"
            strokeDasharray="48 110"
            strokeLinecap="round"
          />
        </svg>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src="/logo.png"
          alt=""
          aria-hidden="true"
          className="cs-brand-cross absolute inset-0 m-auto h-7 w-auto object-contain"
        />
      </div>
      <p className="text-sm text-text-muted">{label}</p>
    </div>
  );
}
