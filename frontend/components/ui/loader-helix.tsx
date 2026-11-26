"use client";

import { useMemo, type CSSProperties } from "react";

import { cn } from "@/lib/utils";

type LoaderHelixProps = {
  dots?: number;
  speed?: number;
  variant?: "dna" | "minimal";
  className?: string;
};

export function LoaderHelix({
  dots = 12,
  speed = 1.6,
  variant = "dna",
  className,
}: LoaderHelixProps) {
  const maxDisplacement = 18;
  const dotSize = 7;
  const dotSpacing = 8;
  const containerHeight = dots * dotSpacing;

  const dotPairs = useMemo(() => {
    return Array.from({ length: dots }, (_, i) => ({
      index: i,
      // Negative delays start the full DNA double-helix wave already in motion at t=0
      delayA: -((i / dots) * speed),
      delayB: -((i / dots) * speed + speed / 2),
    }));
  }, [dots, speed]);

  const containerStyle = {
    width: 96,
    height: containerHeight,
    "--helix-disp": `${maxDisplacement}px`,
  } as CSSProperties;

  return (
    <output
      data-slot="loader-helix"
      aria-live="polite"
      aria-label="Loading"
      className={cn("relative inline-flex flex-col items-center justify-center", className)}
      style={containerStyle}
    >
      <span className="sr-only">Loading</span>

      <div className="relative flex h-full w-full flex-col justify-around">
        {dotPairs.map((pair) => (
          <div
            key={pair.index}
            className="relative flex w-full items-center justify-center"
            style={{ height: dotSpacing }}
          >
            {variant === "dna" && (
              <span
                className="absolute h-[1.5px] bg-accent/35 will-change-transform"
                style={{
                  width: maxDisplacement * 2,
                  animation: `helix-rung-fade ${speed}s ease-in-out infinite`,
                  animationDelay: `${pair.delayA}s`,
                }}
              />
            )}

            <div
              className="absolute rounded-full bg-accent will-change-transform"
              style={{
                width: dotSize,
                height: dotSize,
                left: `calc(50% - ${dotSize / 2}px)`,
                animation: `helix-strand-a ${speed}s ease-in-out infinite`,
                animationDelay: `${pair.delayA}s`,
              }}
            />

            <div
              className="absolute rounded-full bg-foreground will-change-transform"
              style={{
                width: dotSize,
                height: dotSize,
                left: `calc(50% - ${dotSize / 2}px)`,
                animation: `helix-strand-a ${speed}s ease-in-out infinite`,
                animationDelay: `${pair.delayB}s`,
              }}
            />
          </div>
        ))}
      </div>
    </output>
  );
}
