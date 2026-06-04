import path from 'node:path';

import type { NextConfig } from 'next';

// Environment-gated CSP knobs. The standalone production bundle is built with
// NODE_ENV=production; local `next dev` runs with it unset/development.
const isDev = process.env.NODE_ENV !== 'production';

// script-src keeps 'unsafe-inline' because Next.js injects inline hydration
// bootstrap scripts; a nonce-based policy would require request-time middleware
// and is out of scope here. 'unsafe-eval' is DEV-ONLY (React Refresh / dev
// tooling evaluate code); production drops it (S8 hardening).
const scriptSrc = [
  "script-src 'self' 'unsafe-inline'",
  isDev ? "'unsafe-eval'" : '',
  // apis.google.com + gstatic: Firebase Auth signInWithPopup loads the Google
  // API (gapi) client; without these the sign-in script is CSP-blocked and the
  // popup fails with auth/internal-error.
  'https://apis.google.com https://www.gstatic.com',
]
  .filter(Boolean)
  .join(' ');

// connect-src allows http://localhost:* only in dev (the local API). Production
// talks exclusively to the Cloud Run / *.autonomous-agent.dev origins over TLS,
// so the localhost exception is dropped from the shipped policy (S8 hardening).
const connectSrc = [
  "connect-src 'self'",
  'https://*.googleapis.com https://*.firebaseio.com https://*.firebaseapp.com',
  'https://*.run.app https://*.us-central1.run.app https://*.autonomous-agent.dev https://accounts.google.com',
  'wss://*.firebaseio.com',
  isDev ? 'http://localhost:*' : '',
]
  .filter(Boolean)
  .join(' ');

const contentSecurityPolicy = [
  "default-src 'self'",
  scriptSrc,
  "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
  "font-src 'self' https://fonts.gstatic.com",
  // googleusercontent: the signed-in user's Google avatar.
  "img-src 'self' data: blob: https://*.googleusercontent.com",
  connectSrc,
  // accounts.google.com + apis.google.com: the Google OAuth popup/iframe.
  "frame-src 'self' https://*.firebaseapp.com https://apis.google.com https://accounts.google.com",
  // S8 hardening: lock the document base URI and form targets to self, forbid
  // plugin/object embedding, and add the CSP-level clickjacking guard that
  // complements the X-Frame-Options: DENY header below on browsers that honour
  // frame-ancestors.
  "base-uri 'self'",
  "form-action 'self'",
  "object-src 'none'",
  "frame-ancestors 'none'",
].join('; ');

const nextConfig: NextConfig = {
  // Standalone server output for the Cloud Run container (AT-083 dashboard).
  output: 'standalone',
  // Trace from the npm-workspace root so the standalone bundle resolves the
  // hoisted node_modules correctly.
  outputFileTracingRoot: path.join(process.cwd(), '..'),
  headers: async () => [
    {
      source: '/(.*)',
      headers: [
        {
          key: 'Content-Security-Policy',
          value: contentSecurityPolicy,
        },
        {
          // S3 hardening: HTTP Strict Transport Security. One year, applied to
          // subdomains too (the whole atelier.autonomous-agent.dev zone is TLS
          // behind Cloudflare). 'preload' is intentionally omitted — the browser
          // preload-list commitment is hard to reverse and out of scope for this
          // project. Set at the origin as defense-in-depth even though the edge
          // also enforces TLS.
          key: 'Strict-Transport-Security',
          value: 'max-age=31536000; includeSubDomains',
        },
        {
          key: 'X-Content-Type-Options',
          value: 'nosniff',
        },
        {
          key: 'X-Frame-Options',
          value: 'DENY',
        },
        {
          // signInWithPopup opens a cross-origin OAuth popup; same-origin-allow-popups
          // keeps the opener's handle to it (silences the window.closed COOP warning and
          // lets the SDK detect a user-cancelled popup) without weakening isolation.
          key: 'Cross-Origin-Opener-Policy',
          value: 'same-origin-allow-popups',
        },
        {
          key: 'Referrer-Policy',
          value: 'strict-origin-when-cross-origin',
        },
        {
          key: 'Permissions-Policy',
          value: 'camera=(), microphone=(), geolocation=()',
        },
      ],
    },
  ],
};

export default nextConfig;
