import React, { ReactNode } from "react";
import Link from "next/link";

interface EmptyStateProps {
  /** SVG icon element to display above the heading. */
  icon?: ReactNode;
  /** Primary heading text. */
  heading: string;
  /** Supporting description below the heading. */
  description?: string;
  /** Label for the CTA button/link. */
  ctaLabel?: string;
  /** href for the CTA link. If omitted, no CTA is rendered. */
  ctaHref?: string;
}

/**
 * Presentational empty-state component for NEXUS list pages.
 *
 * Renders when an API call succeeds but returns zero items.
 * Provides heading, optional description, and an optional CTA link.
 */
export function EmptyState({
  icon,
  heading,
  description,
  ctaLabel,
  ctaHref,
}: EmptyStateProps): React.ReactElement {
  return (
    <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-gray-300 bg-white px-6 py-16 text-center dark:border-gray-600 dark:bg-gray-800">
      {icon && (
        <div className="mb-4 text-gray-400 dark:text-gray-500">{icon}</div>
      )}
      <h3 className="text-lg font-semibold text-gray-800 dark:text-gray-100">
        {heading}
      </h3>
      {description && (
        <p className="mt-2 max-w-sm text-sm text-gray-500 dark:text-gray-400">
          {description}
        </p>
      )}
      {ctaHref && ctaLabel && (
        <Link
          href={ctaHref}
          className="mt-6 inline-flex items-center rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2"
        >
          {ctaLabel}
        </Link>
      )}
    </div>
  );
}