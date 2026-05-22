import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import './globals.css'

const inter = Inter({
  subsets: ['latin'],
  variable: '--font-inter',
  display: 'swap',
})

export const metadata: Metadata = {
  title: {
    template: '%s — NEXUS - Distributed AI Agent Orchestration Platform',
    default: 'NEXUS - Distributed AI Agent Orchestration Platform',
  },
  description: 'Distributed AI agent orchestration platform',
  // Inline SVG favicon as a data URL (avoids a separate file in /public)
  icons: {
    icon: "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 14 14' fill='none'><rect width='14' height='14' rx='2' fill='%23534AB7'/><rect x='1' y='1' width='5' height='5' rx='1' fill='white'/><rect x='8' y='1' width='5' height='5' rx='1' fill='white' opacity='0.6'/><rect x='1' y='8' width='5' height='5' rx='1' fill='white' opacity='0.6'/><rect x='8' y='8' width='5' height='5' rx='1' fill='white' opacity='0.3'/></svg>"
  },
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={inter.variable}>
      <body className="bg-nexus-bg font-sans antialiased">
        {children}
      </body>
    </html>
  )
}