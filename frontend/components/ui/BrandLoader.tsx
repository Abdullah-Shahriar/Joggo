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
        <svg
          aria-hidden="true"
          className="absolute inset-0 m-auto h-7 w-7 text-accent"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.75"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M12 3L4.5 6.2V11.8c0 4.8 3.2 8.2 7.5 9.2 4.3-1 7.5-4.4 7.5-9.2V6.2L12 3Z" />
          <path className="cs-brand-cross" d="M12 8.5v7M8.5 12h7" />
        </svg>
      </div>
      <p className="text-sm text-text-muted">{label}</p>
    </div>
  );
}
