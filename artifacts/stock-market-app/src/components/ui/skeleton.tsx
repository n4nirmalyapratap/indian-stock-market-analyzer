/**
 * Skeleton.tsx
 * ============
 * Reusable loading skeleton primitives. Use instead of repeating
 * `<div className="h-X bg-gray-100 dark:bg-gray-700 animate-pulse rounded" />`
 * throughout the codebase.
 */

interface SkeletonProps {
  className?: string;
}

export function Skeleton({ className = "" }: SkeletonProps) {
  return (
    <div
      className={`bg-gray-100 dark:bg-gray-700 animate-pulse rounded ${className}`}
    />
  );
}

export function SkeletonText({ lines = 3, className = "" }: { lines?: number; className?: string }) {
  return (
    <div className={`space-y-2 ${className}`}>
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton key={i} className={`h-4 ${i === lines - 1 ? "w-3/4" : "w-full"}`} />
      ))}
    </div>
  );
}

export function SkeletonCard({ className = "" }: SkeletonProps) {
  return (
    <div className={`p-4 rounded-xl border border-gray-100 dark:border-gray-700 space-y-3 ${className}`}>
      <Skeleton className="h-5 w-1/3" />
      <Skeleton className="h-8 w-1/2" />
      <Skeleton className="h-4 w-full" />
    </div>
  );
}

export function SkeletonRow({ cols = 4, className = "" }: { cols?: number; className?: string }) {
  return (
    <div className={`grid gap-3 ${className}`} style={{ gridTemplateColumns: `repeat(${cols}, 1fr)` }}>
      {Array.from({ length: cols }).map((_, i) => (
        <Skeleton key={i} className="h-8" />
      ))}
    </div>
  );
}
