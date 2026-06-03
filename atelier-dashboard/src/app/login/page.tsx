'use client';

import React, { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { auth, googleProvider, isFirebaseConfigured } from '@/lib/firebase';
import { signInWithPopup } from 'firebase/auth';
import { m, LazyMotion, domAnimation } from 'framer-motion';

export default function LoginPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // The local dev-mode auth bypass mints a mock user so the dashboard is usable
  // without Firebase configured. It must NEVER reach a production build — gating
  // it on NODE_ENV (statically eliminated by the bundler in prod) guarantees the
  // mock credential and the "Dev Mode" affordance cannot appear in production,
  // even if the Firebase env vars are somehow missing at build time. A
  // misconfigured prod build then surfaces a real error, not a fake session.
  const devBypassAllowed = !isFirebaseConfigured && process.env.NODE_ENV !== 'production';

  // If already logged in, redirect to home
  useEffect(() => {
    const userStr = localStorage.getItem('user');
    if (userStr) {
      router.push('/');
    }
  }, [router]);

  const handleGoogleSignIn = async () => {
    setLoading(true);
    setError(null);

    if (devBypassAllowed) {
      // Dev Mode Authentication Bypass (local development only — never prod)
      const mockUser = {
        uid: 'dev-user-local',
        email: 'developer@atelier.dev',
        displayName: 'Local Developer',
        token: 'dev-bypass-token',
        tenant_id: 't1',
      };
      localStorage.setItem('user', JSON.stringify(mockUser));
      setLoading(false);
      setTimeout(() => {
        router.push('/');
      }, 500);
      return;
    }

    try {
      if (!auth || !googleProvider) {
        setError('Firebase Authentication is not initialized.');
        setLoading(false);
        return;
      }
      const result = await signInWithPopup(auth, googleProvider);
      const token = await result.user.getIdToken();
      const userPayload = {
        uid: result.user.uid,
        email: result.user.email,
        displayName: result.user.displayName,
        token: token,
        tenant_id: 't1',
      };
      localStorage.setItem('user', JSON.stringify(userPayload));
      router.push('/');
    } catch (err: unknown) {
      console.error('Sign-in failed:', err);
      const message =
        err instanceof Error ? err.message : 'An error occurred during authentication.';
      setError(message);
      setLoading(false);
    }
  };

  return (
    <LazyMotion features={domAnimation}>
      <main
        id="login-page"
        className="flex-grow flex items-center justify-center p-6 bg-[var(--g-bg)] stitch-grid-bg relative overflow-hidden"
      >
        {/* Subtle glowing ambient background orbs */}
        <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-[var(--g-primary-blue)]/10 rounded-full blur-[100px] pointer-events-none" />
        <div className="absolute bottom-1/4 right-1/4 w-[500px] h-[500px] bg-[var(--g-info)]/10 rounded-full blur-[120px] pointer-events-none" />

        <m.div
          initial={{ opacity: 0, scale: 0.95, y: 20 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
          className="w-full max-w-md g-card p-10 relative z-10 shadow-2xl backdrop-blur-xl bg-[var(--g-surface)]/80"
        >
          <div className="flex flex-col items-center mb-10">
            <m.div
              initial={{ scale: 0.5, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              transition={{ delay: 0.2, type: 'spring', bounce: 0.5 }}
              className="w-14 h-14 rounded-2xl bg-[var(--g-primary-blue)] flex items-center justify-center mb-6 shadow-[0_0_24px_rgba(26,115,232,0.4)]"
            >
              <span className="text-2xl font-bold text-white">A</span>
            </m.div>
            <h1 id="login-title" className="text-3xl font-medium tracking-tight text-white mb-3">
              Welcome to Atelier
            </h1>
            <p className="text-[15px] text-[var(--g-text-muted)] text-center">
              Design rapidly with Autonomous AI
            </p>
          </div>

          {error && (
            <m.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              className="mb-6 p-4 rounded-lg bg-red-900/20 border border-red-500/30 text-xs text-red-400"
            >
              {error}
            </m.div>
          )}

          <div className="space-y-5">
            <button
              id="google-signin-btn"
              onClick={handleGoogleSignIn}
              disabled={loading}
              className="w-full py-3.5 px-4 rounded-xl bg-white hover:bg-gray-100 text-gray-900 font-medium text-[15px] transition-all flex items-center justify-center gap-3 cursor-pointer shadow-md disabled:opacity-50 hover:shadow-lg hover:-translate-y-0.5 active:translate-y-0"
            >
              <svg className="w-5 h-5" viewBox="0 0 24 24" width="24" height="24">
                <path
                  fill="#4285F4"
                  d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
                />
                <path
                  fill="#34A853"
                  d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                />
                <path
                  fill="#FBBC05"
                  d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"
                />
                <path
                  fill="#EA4335"
                  d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"
                />
              </svg>
              {loading
                ? 'Authenticating...'
                : devBypassAllowed
                  ? 'Dev Mode Sign In (Bypass)'
                  : 'Continue with Google'}
            </button>

            {devBypassAllowed && (
              <p className="text-[11px] text-[var(--g-text-muted)] text-center mt-4 leading-relaxed">
                Running in Developer Mode. The dashboard will mock client authentication and pass a
                developer credential to local API server.
              </p>
            )}
          </div>
        </m.div>
      </main>
    </LazyMotion>
  );
}
