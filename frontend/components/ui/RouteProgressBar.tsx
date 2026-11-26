"use client";

import { useIsFetching } from "@tanstack/react-query";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

export function RouteProgressBar() {
  const pathname = usePathname();
  const fetching = useIsFetching();
  const [navigating, setNavigating] = useState(false);

  useEffect(() => {
    setNavigating(true);
    const t = setTimeout(() => setNavigating(false), 180);
    return () => clearTimeout(t);
  }, [pathname]);

  const active = navigating || fetching > 0;
  if (!active) return null;

  return (
    <div
      aria-hidden="true"
      className="fixed left-0 top-0 z-50 h-0.5 w-full overflow-hidden bg-accent-tint"
    >
      <div className="h-full w-2/3 bg-accent transition-all duration-150" />
    </div>
  );
}
