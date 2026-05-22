/**
 * NEXUS root layout — wraps all authenticated pages with Sidebar + TopBar.
 *
 * This is a React Server Component. Sidebar and TopBar are Client Components
 * rendered inside this server boundary. Inter font is loaded via next/font
 * to eliminate the runtime Google Fonts request.
 */

import type { Metadata } from 'next'
import { Inter} from 'next/font/google'
import { Sidebar } from '@/components/ui/Sidebar'
import './globals.css'

const inter = Inter({
  subsets: ['latin'],
  variable: '--font-inter',
  display: 'swap',
})

export const metadata: Metadata = {
  title: {
    template: '%s — NEXUS',
    default: 'NEXUS',
  },
  description: 'AI agent orchestration platform',
}

/**
 * Props for the root layout.
 */
interface RootLayoutProps {
  children: React.ReactNode
}

/**
 * Root layout shared by all NEXUS pages.
 *
 * Renders the shell: sidebar (220px) + main content area (flex-1).
 * The TopBar is rendered per-page since each page has a different title.
 */
export default function RootLayout({ children }: RootLayoutProps) {
  return (
    <html lang="en" className={inter.variable}>
      <body className="bg-nexus-bg font-sans antialiased">
        <div className="flex h-screen overflow-hidden">
          <Sidebar />
          <main className="flex-1 flex flex-col min-w-0 overflow-hidden">
            {children}
          </main>
        </div>
      </body>
    </html>
  )
}