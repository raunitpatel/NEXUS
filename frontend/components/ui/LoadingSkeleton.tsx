import React from "react";

/** Base shimmer block — all skeletons compose from this. */
function Shimmer({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>): React.ReactElement {
  return (
    <div
      className={`animate-pulse rounded bg-gray-200 dark:bg-gray-700 ${className ?? ""}`}
      {...props}
    />
  );
}

/** Skeleton that matches the visual footprint of a single RunCard. */
export function RunCardSkeleton(): React.ReactElement {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
      <div className="flex items-center justify-between">
        <Shimmer className="h-4 w-32" />
        <Shimmer className="h-5 w-16 rounded-full" />
      </div>
      <Shimmer className="mt-3 h-3 w-48" />
      <div className="mt-4 flex gap-4">
        <Shimmer className="h-3 w-20" />
        <Shimmer className="h-3 w-20" />
      </div>
    </div>
  );
}

interface TableRowSkeletonProps {
  /** Number of skeleton rows to render. Defaults to 5. */
  count?: number;
  /** Number of columns per row. Defaults to 4. */
  cols?: number;
}

/** Skeleton that matches a table body row in the metrics table. */
export function TableRowSkeleton({
  count = 5,
  cols = 4,
}: TableRowSkeletonProps): React.ReactElement {
  return (
    <>
      {Array.from({ length: count }).map((_, rowIdx) => (
        <tr key={rowIdx} className="border-b border-gray-100 dark:border-gray-700">
          {Array.from({ length: cols }).map((_, colIdx) => (
            <td key={colIdx} className="px-4 py-3">
              <Shimmer className="h-3 w-full" />
            </td>
          ))}
        </tr>
      ))}
    </>
  );
}

/** Skeleton that fills the chart container area on the dashboard. */
export function ChartSkeleton(): React.ReactElement {
  return (
    <div className="flex h-64 w-full flex-col justify-end gap-1 rounded-lg border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
      <div className="flex h-full items-end gap-2">
        {[40, 65, 30, 80, 55, 70, 45, 90, 60, 75].map((height, i) => (
          <Shimmer
            key={i}
            className="flex-1 rounded-t"
            style={{ height: `${height}%` }}
          />
        ))}
      </div>
      <Shimmer className="mt-2 h-3 w-full" />
    </div>
  );
}