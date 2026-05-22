import Link from 'next/link'

export default function NotFound() {
  return (
    <div className="min-h-screen bg-nexus-bg flex items-center justify-center px-6">
      <div className="text-center max-w-md">
        {/* 404 display */}
        <div className="text-[80px] font-bold text-nexus-accent/20 leading-none mb-2 select-none">
          404
        </div>

        {/* Wordmark */}
        <div className="flex items-center justify-center gap-2 mb-4">
          <div className="w-6 h-6 bg-nexus-accent rounded-[5px] flex items-center justify-center">
            <svg viewBox="0 0 14 14" fill="none" className="w-[14px] h-[14px]">
              <rect x="1" y="1" width="5" height="5" rx="1" fill="white"/>
              <rect x="8" y="1" width="5" height="5" rx="1" fill="white" opacity="0.6"/>
              <rect x="1" y="8" width="5" height="5" rx="1" fill="white" opacity="0.6"/>
              <rect x="8" y="8" width="5" height="5" rx="1" fill="white" opacity="0.3"/>
            </svg>
          </div>
          <span className="text-[14px] font-bold text-nexus-dark tracking-[0.06em]">NEXUS</span>
        </div>

        <h1 className="text-[22px] font-semibold text-nexus-dark mb-2">Page not found</h1>
        <p className="text-[13.5px] text-nexus-muted mb-6 leading-[1.6]">
          The page you&apos;re looking for doesn&apos;t exist or has been moved.
        </p>

        <Link
          href="/dashboard"
          className="inline-flex items-center gap-2 bg-nexus-accent hover:bg-nexus-accent-hover text-white px-5 py-2.5 rounded-[7px] text-[13.5px] font-medium no-underline transition-colors"
        >
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
            <rect x="1" y="1" width="6" height="6" rx="1.5" fill="white"/>
            <rect x="8" y="1" width="5" height="5" rx="1" fill="white" opacity="0.6"/>
            <rect x="1" y="8" width="5" height="5" rx="1" fill="white" opacity="0.6"/>
            <rect x="8" y="8" width="5" height="5" rx="1" fill="white" opacity="0.3"/>
          </svg>
          Go to Dashboard
        </Link>
      </div>
    </div>
  )
}