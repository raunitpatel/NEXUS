"use client";

import React, { Component, ReactNode } from "react";

interface Props {
  /** Content to render when no error has occurred. */
  children: ReactNode;
  /** Optional custom fallback. Defaults to the built-in fallback card. */
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  errorMessage: string;
}

/**
 * Class-based React error boundary for NEXUS page sections.
 *
 * Wraps any subtree that performs data-fetching or complex rendering.
 * On error, replaces the subtree with a static fallback UI so the rest
 * of the page remains interactive.
 */
export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, errorMessage: "" };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, errorMessage: error.message };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo): void {
    console.error("[ErrorBoundary] Caught error:", error, info.componentStack);
  }

  render(): ReactNode {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }
      return (
        <div className="rounded-lg border border-red-200 bg-red-50 p-6 text-center">
          <h2 className="text-lg font-semibold text-red-700">
            Something went wrong
          </h2>
          <p className="mt-2 text-sm text-red-500">
            This section failed to load. Try refreshing the page.
          </p>
          {process.env.NEXT_PUBLIC_APP_ENV === "development" && (
            <pre className="mt-4 max-h-32 overflow-auto rounded bg-red-100 p-2 text-left text-xs text-red-800">
              {this.state.errorMessage}
            </pre>
          )}
        </div>
      );
    }

    return this.props.children;
  }
}