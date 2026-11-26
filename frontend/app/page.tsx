import { APP_NAME } from "@/lib/constants";

export default function HomePage() {
  return (
    <div className="flex min-h-screen flex-col bg-bg text-text">
      <header className="h-16 border-b border-border bg-bg">
        <div className="mx-auto flex h-full max-w-app items-center justify-between px-4 sm:px-6">
          <div className="flex items-center gap-2 text-base font-semibold text-text">
            <svg
              aria-hidden="true"
              className="h-6 w-6 text-accent"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.75"
            >
              <path d="M12 3L4 6.5V12c0 5 3.4 8.4 8 9.5 4.6-1.1 8-4.5 8-9.5V6.5L12 3Z" />
              <path d="M12 8v8M8 12h8" />
            </svg>
            <span>{APP_NAME}</span>
          </div>
          <span className="text-xs text-text-muted">Demo environment — synthetic data only</span>
        </div>
      </header>

      <main className="flex-1">
        <section className="mx-auto max-w-prose px-4 py-16 sm:px-6">
          <h1 className="text-[44px] font-semibold leading-tight tracking-tight text-text">
            Use AI on patient records. Without exposing patients.
          </h1>
          <p className="mt-4 text-base text-text-muted">
            We remove identities locally before anything reaches an AI model, then restore them on
            your screen.
          </p>
        </section>
      </main>

      <footer className="border-t border-border bg-bg py-6">
        <div className="mx-auto flex max-w-app flex-col justify-between gap-2 px-4 text-xs text-text-muted sm:flex-row sm:px-6">
          <span>Privacy-first AI for clinical documents.</span>
          <span>Demo environment — use synthetic data only</span>
        </div>
      </footer>
    </div>
  );
}
