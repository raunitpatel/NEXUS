import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Terms of Service — NEXUS',
}

export default function TermsPage() {
  return (
    <main className="min-h-screen bg-nexus-bg px-6 py-10">
      <div className="mx-auto max-w-4xl bg-white rounded-[18px] border border-black/[0.08] p-8 shadow-[0_8px_32px_rgba(0,0,0,0.08)]">
        <h1 className="text-3xl font-semibold text-nexus-dark mb-4">Terms of Service</h1>
        <p className="text-base text-nexus-text mb-6">
          Welcome to NEXUS. These Terms of Service govern your use of our platform.
          By accessing or using NEXUS, you agree to abide by these terms.
        </p>

        <section className="space-y-4">
          <div>
            <h2 className="text-xl font-semibold text-nexus-dark mb-2">1. Your Account</h2>
            <p className="text-base text-nexus-text">
              You are responsible for maintaining the confidentiality of your account credentials.
              You may not share your account or access with others.
            </p>
          </div>

          <div>
            <h2 className="text-xl font-semibold text-nexus-dark mb-2">2. Acceptable Use</h2>
            <p className="text-base text-nexus-text">
              You agree not to misuse the service or engage in unlawful activities.
              This includes avoiding content or requests that violate applicable laws or third-party rights.
            </p>
          </div>

          <div>
            <h2 className="text-xl font-semibold text-nexus-dark mb-2">3. Intellectual Property</h2>
            <p className="text-base text-nexus-text">
              NEXUS and its content are protected by intellectual property laws.
              You may not reproduce, modify, or distribute our content without permission.
            </p>
          </div>

          <div>
            <h2 className="text-xl font-semibold text-nexus-dark mb-2">4. Disclaimer</h2>
            <p className="text-base text-nexus-text">
              The service is provided "as is" without warranties of any kind.
              We are not responsible for the outcomes of your use of generated content.
            </p>
          </div>

          <div>
            <h2 className="text-xl font-semibold text-nexus-dark mb-2">5. Changes</h2>
            <p className="text-base text-nexus-text">
              We may update these Terms at any time. Continued use of NEXUS after changes means you accept the revised terms.
            </p>
          </div>
        </section>
      </div>
    </main>
  )
}
