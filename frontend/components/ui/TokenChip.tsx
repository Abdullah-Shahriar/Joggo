import type { ReactNode } from "react";

export function TokenChip({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={`inline-block whitespace-nowrap rounded-l-none rounded-r-[4px] border-l-[3px] border-l-accent bg-accent-tint px-[6px] py-[1px] align-baseline font-mono text-[12px] font-medium leading-[1.4] text-accent ${className}`}
    >
      {children}
    </span>
  );
}
