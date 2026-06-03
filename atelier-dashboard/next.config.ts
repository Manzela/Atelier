import path from 'node:path';

import type { NextConfig } from 'next';

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
          value: [
            "default-src 'self'",
            // apis.google.com + gstatic: Firebase Auth signInWithPopup loads the
            // Google API (gapi) client; without these the Google sign-in script is
            // CSP-blocked and the popup fails with auth/internal-error.
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://apis.google.com https://www.gstatic.com",
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
            "font-src 'self' https://fonts.gstatic.com",
            // googleusercontent: the signed-in user's Google avatar.
            "img-src 'self' data: blob: https://*.googleusercontent.com",
            "connect-src 'self' https://*.googleapis.com https://*.firebaseio.com https://*.firebaseapp.com https://*.run.app https://*.autonomous-agent.dev https://accounts.google.com wss://*.firebaseio.com http://localhost:*",
            // accounts.google.com + apis.google.com: the Google OAuth popup/iframe.
            "frame-src 'self' https://*.firebaseapp.com https://apis.google.com https://accounts.google.com",
          ].join('; '),
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
