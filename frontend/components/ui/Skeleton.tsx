export function TableSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div aria-busy="true" aria-label="Loading content" className="divide-y divide-border border-y border-border">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex items-center gap-4 py-3.5">
          <div className="h-4 w-1/3 animate-pulse rounded bg-bg-subtle" />
          <div className="h-4 w-1/5 animate-pulse rounded bg-bg-subtle" />
          <div className="h-4 w-1/6 animate-pulse rounded bg-bg-subtle" />
          <div className="ml-auto h-4 w-20 animate-pulse rounded bg-bg-subtle" />
        </div>
      ))}
    </div>
  );
}

export function PaneSkeleton() {
  return (
    <div aria-busy="true" aria-label="Loading pane" className="space-y-3 p-4">
      <div className="h-4 w-3/4 animate-pulse rounded bg-bg-subtle" />
      <div className="h-4 w-full animate-pulse rounded bg-bg-subtle" />
      <div className="h-4 w-5/6 animate-pulse rounded bg-bg-subtle" />
      <div className="h-4 w-2/3 animate-pulse rounded bg-bg-subtle" />
      <div className="h-4 w-11/12 animate-pulse rounded bg-bg-subtle" />
    </div>
  );
}
