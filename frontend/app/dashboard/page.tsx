/**
 * Dashboard page — stub for AGNT-021.
 *
 * Renders TopBar with title "Dashboard". Full implementation
 * (metric cards, active runs, recent runs table) comes in AGNT-021.
 */

import { TopBar } from '@/components/ui/TopBar'

export const metadata = { title: 'Dashboard' }

export default function DashboardPage() {
  return (
    <>
      <TopBar title="Dashboard" initials="AK" />
      <div className="flex-1 bg-nexus-bg overflow-y-auto p-6">
        <p className="text-nexus-muted text-sm">
          Dashboard coming in AGNT-021.
        </p>
      </div>
    </>
  )
}