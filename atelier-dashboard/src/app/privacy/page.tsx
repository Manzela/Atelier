import React from 'react';
import Link from 'next/link';

export const metadata = {
  title: 'Atelier — Privacy Policy',
  description: 'Privacy Policy for the Atelier autonomous design agent platform.',
};

export default function PrivacyPage() {
  return (
    <main className="min-h-screen bg-[var(--g-bg)] stitch-grid-bg py-16 px-6 flex justify-center">
      <div className="w-full max-w-3xl g-card p-10 bg-[var(--g-surface)]/80 backdrop-blur-xl shadow-2xl relative">
        <header className="mb-10 border-b border-[var(--g-outline)] pb-6 flex flex-col gap-4">
          <div className="w-12 h-12 rounded-xl bg-black flex items-center justify-center border border-neutral-800 shadow-[0_0_16px_rgba(255,255,255,0.05)]">
            <svg
              className="w-5 h-5"
              viewBox="0 0 1155 1000"
              fill="none"
              role="img"
              aria-label="Atelier Logo"
            >
              <path d="m577.3 0 577.4 1000H0z" fill="#fff" />
            </svg>
          </div>
          <div>
            <h1 className="text-3xl font-medium tracking-tight text-white">
              Atelier Privacy Policy
            </h1>
            <p className="text-xs text-[var(--g-text-muted)] font-mono mt-1">
              Effective Date: June 5, 2026
            </p>
          </div>
        </header>

        <div className="space-y-8 text-sm text-[var(--g-text-muted)] leading-relaxed">
          <section>
            <p>
              At <strong>Atelier</strong>, we respect your privacy and are committed to protecting
              the personal data we process about you. This Privacy Policy describes how we collect,
              use, secure, and share your information when you use our autonomous design agent
              Services.
            </p>
          </section>

          <section className="space-y-3">
            <h2 className="text-lg font-medium text-white">1. Information We Collect</h2>
            <p>
              We collect information to provide and improve our Services, authenticate your
              identity, and ensure a secure experience:
            </p>
            <ul className="list-disc pl-5 space-y-2">
              <li>
                <strong>Authentication Information:</strong> When you sign in via Google OAuth, we
                receive your Google user profile information, including your email address, display
                name, profile photo, and unique identifier (UID). We do not receive or store your
                Google password.
              </li>
              <li>
                <strong>User Workspaces and Settings:</strong> We store your custom design briefs,
                projects, design tokens, layout configurations, and generated code components to
                allow you to persist and continue your work.
              </li>
              <li>
                <strong>System Interaction Logs:</strong> We collect standard technical and
                telemetry data, including IP addresses, browser types, page load performance
                metrics, and usage statistics to monitor platform health. These logs are scrubbed of
                any Personally Identifiable Information (PII) before storage.
              </li>
            </ul>
          </section>

          <section className="space-y-3">
            <h2 className="text-lg font-medium text-white">2. How We Use Your Information</h2>
            <p>We process your data for the following purposes:</p>
            <ul className="list-disc pl-5 space-y-2">
              <li>To authenticate your identity and grant access to your private workspaces.</li>
              <li>
                To save, retrieve, and export the design assets and codebase configurations you
                build.
              </li>
              <li>
                To detect, prevent, and debug performance bottlenecks, security exploits, or policy
                violations.
              </li>
              <li>
                To refine, calibrate, and tune the response qualities of our multi-agent AI system.
              </li>
            </ul>
          </section>

          <section className="space-y-3">
            <h2 className="text-lg font-medium text-white">
              3. Data Sharing and Third-Party Disclosures
            </h2>
            <p>
              We do not sell, rent, or distribute your personal data or generated design assets to
              third parties. We only share information in the following circumstances:
            </p>
            <ul className="list-disc pl-5 space-y-2">
              <li>
                <strong>Cloud Infrastructure Providers:</strong> We use Google Cloud Platform (GCP)
                and Firebase to host our APIs, frontend, databases, and authentication endpoints.
                Your data is stored securely in GCP datacenters.
              </li>
              <li>
                <strong>Legal Requirements:</strong> We may disclose data if required to do so by
                law or in good faith belief that such action is necessary to comply with legal
                obligations.
              </li>
            </ul>
          </section>

          <section className="space-y-3">
            <h2 className="text-lg font-medium text-white">4. Data Security</h2>
            <p>
              We implement industry-standard administrative, technical, and physical security
              measures to protect your data. All communication is encrypted in transit using
              Transport Layer Security (TLS 1.3), and all data at rest is encrypted using standard
              GCP cryptographic keys. To protect against open redirect attacks, we implement
              server-side and client-side hostname validation on all redirect payloads.
            </p>
          </section>

          <section className="space-y-3">
            <h2 className="text-lg font-medium text-white">5. Your Rights and Controls</h2>
            <p>You have full control over your personal data and projects. You may request to:</p>
            <ul className="list-disc pl-5 space-y-2">
              <li>Access, update, or correct your profile information.</li>
              <li>
                Delete your account and clear all stored project codebases and designs from our
                servers.
              </li>
              <li>
                Revoke the Google OAuth application permission directly from your Google Account
                settings page.
              </li>
              <li>Request deletion of your data by contacting our support team.</li>
            </ul>
          </section>

          <section className="space-y-3">
            <h2 className="text-lg font-medium text-white">6. Cookies and Storage</h2>
            <p>
              We only use essential local storage keys and session cookies to persist your
              authenticated session. We do not use third-party advertising cookies or trackers.
            </p>
          </section>

          <section className="space-y-3">
            <h2 className="text-lg font-medium text-white">7. Contact Information</h2>
            <p>
              If you have any questions or concerns regarding this Privacy Policy or our data
              practices, you can contact us at{' '}
              <a
                href="mailto:support@atelier.autonomous-agent.dev"
                className="text-[var(--g-info)] hover:underline"
              >
                support@atelier.autonomous-agent.dev
              </a>
              .
            </p>
          </section>
        </div>

        <footer className="mt-12 border-t border-[var(--g-outline)] pt-6 flex justify-between items-center text-xs text-[var(--g-text-muted)]">
          <span>&copy; 2026 Atelier. All rights reserved.</span>
          <Link href="/terms" className="text-[var(--g-info)] hover:underline">
            Terms of Service
          </Link>
        </footer>
      </div>
    </main>
  );
}
