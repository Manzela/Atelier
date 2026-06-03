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
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'",
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
            "font-src 'self' https://fonts.gstatic.com",
            "img-src 'self' data: blob:",
            "connect-src 'self' https://*.googleapis.com https://*.firebaseio.com https://*.firebaseapp.com https://*.run.app https://*.autonomous-agent.dev wss://*.firebaseio.com http://localhost:*",
            "frame-src 'self' https://*.firebaseapp.com",
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
