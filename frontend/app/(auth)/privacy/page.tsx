import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Privacy Policy — NEXUS',
}

export default function PrivacyPage() {
  return (
    <main className="min-h-screen bg-nexus-bg px-6 py-10">
      <div className="mx-auto max-w-4xl bg-white rounded-[18px] border border-black/[0.08] p-8 shadow-[0_8px_32px_rgba(0,0,0,0.08)]">
        <h1 className="text-3xl font-semibold text-nexus-dark mb-4">Privacy Policy</h1>
        <p className="text-base text-nexus-text mb-6">
          This Privacy Policy explains how we collect, use, and protect your personal data when you use NEXUS.
        </p>

        <section className="space-y-4">
          <div>
            <h2 className="text-xl font-semibold text-nexus-dark mb-2">1. Information We Collect</h2>
            <p className="text-base text-nexus-text">
              We collect the information you provide when registering, such as your name and email address.
              We also store authentication tokens to keep you signed in.
            </p>
          </div>

          <div>
            <h2 className="text-xl font-semibold text-nexus-dark mb-2">2. How We Use Your Data</h2>
            <p className="text-base text-nexus-text">
              Your data is used to provide and improve the NEXUS platform, to authenticate your sessions, and to respond to support requests.
            </p>
          </div>

          <div>
            <h2 className="text-xl font-semibold text-nexus-dark mb-2">3. Cookies and Storage</h2>
            <p className="text-base text-nexus-text">
              We use cookies and browser storage to maintain your authenticated session and to support secure access to protected routes.
            </p>
          </div>

          <div>
            <h2 className="text-xl font-semibold text-nexus-dark mb-2">4. Data Security</h2>
            <p className="text-base text-nexus-text">
              We take reasonable measures to protect your information, but no internet transmission is completely secure.
              Please keep your credentials private.
            </p>
          </div>

          <div>
            <h2 className="text-xl font-semibold text-nexus-dark mb-2">5. Contact</h2>
            <p className="text-base text-nexus-text">
              If you have questions about this policy, contact support at support@nexus.dev.
            </p>
          </div>
        </section>
      </div>
    </main>
  )
}
