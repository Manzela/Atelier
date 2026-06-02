'use client';

import React, { useState, useRef, useCallback } from 'react';
import { LazyMotion, domAnimation, m, AnimatePresence } from 'framer-motion';
import {
  Menu,
  Plus,
  Smartphone,
  Monitor,
  Mic,
  Send,
  Cloud,
  CreditCard,
  LayoutTemplate,
  History,
  Palette,
  ChevronDown,
} from 'lucide-react';
import { useRouter } from 'next/navigation';

type SidebarMode = 'stitch' | 'gcp';

interface UserSession {
  uid: string;
  email: string;
  displayName: string;
  token: string;
  tenant_id: string;
}

function useClientAuth() {
  const router = useRouter();
  const initialized = useRef(false);
  const [user, setUser] = useState<UserSession | null>(null);

  const initRef = useCallback(
    (node: HTMLDivElement | null) => {
      if (initialized.current || !node) return;
      initialized.current = true;
      const userStr = localStorage.getItem('user');
      if (!userStr) {
        router.push('/login');
        return;
      }
      try {
        setUser(JSON.parse(userStr) as UserSession);
      } catch {
        localStorage.removeItem('user');
        router.push('/login');
      }
    },
    [router]
  );

  return { user, initRef };
}

export default function StitchClientShell() {
  const [sidebarMode, setSidebarMode] = useState<SidebarMode>('stitch');
  const [prompt, setPrompt] = useState('');
  const [deviceType, setDeviceType] = useState<'app' | 'web'>('app');
  const [isFocused, setIsFocused] = useState(false);
  const { user, initRef } = useClientAuth();
  const router = useRouter();

  const handleGenerate = () => {
    if (!prompt.trim()) return;
    const briefId = encodeURIComponent(
      prompt.substring(0, 20).replace(/\s+/g, '-').toLowerCase() + '-' + Date.now()
    );
    router.push(`/studio/${briefId}?brief=${encodeURIComponent(prompt)}`);
  };

  const getUserInitials = (): string => {
    if (!user?.displayName) return '?';
    return user.displayName
      .split(' ')
      .map((n) => n[0])
      .join('')
      .substring(0, 2)
      .toUpperCase();
  };

  if (!user) return <div ref={initRef} />;

  return (
    <LazyMotion features={domAnimation}>
      <div className="flex h-screen w-screen overflow-hidden bg-[var(--g-bg)] text-[var(--g-text)] stitch-grid-bg">
        {/* Sidebar */}
        <m.aside
          className="w-64 border-r border-[var(--g-outline)] bg-transparent flex flex-col"
          initial={{ x: -20, opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
        >
          <div className="h-16 flex items-center px-4 border-b border-[var(--g-outline)]">
            <button
              onClick={() => setSidebarMode((prev) => (prev === 'stitch' ? 'gcp' : 'stitch'))}
              className="p-2 rounded-full hover:bg-[var(--g-surface-hover)] transition-colors"
              aria-label="Toggle sidebar mode"
            >
              <Menu size={20} className="text-[var(--g-text-muted)]" />
            </button>
            <span className="ml-3 font-medium text-[15px] tracking-wide text-white">
              {sidebarMode === 'stitch' ? 'Stitch BETA' : 'GCP Console'}
            </span>
          </div>

          <div className="flex-1 overflow-y-auto overflow-x-hidden p-3 relative">
            <AnimatePresence mode="wait">
              {sidebarMode === 'stitch' ? (
                <m.div
                  key="stitch-nav"
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: 10 }}
                  transition={{ duration: 0.2 }}
                  className="flex flex-col gap-6"
                >
                  <div className="flex bg-[var(--g-surface)] rounded-full p-1 border border-[var(--g-outline)]">
                    <button className="flex-1 text-sm py-1.5 px-3 rounded-full bg-[var(--g-outline)] text-white font-medium shadow-sm">
                      My projects
                    </button>
                    <button className="flex-1 text-sm py-1.5 px-3 rounded-full text-[var(--g-text-muted)] hover:text-white transition-colors">
                      Shared
                    </button>
                  </div>

                  <div>
                    <h3 className="text-[11px] font-semibold text-[var(--g-text-muted)] uppercase tracking-wider mb-2 px-2">
                      Last 30 days
                    </h3>
                    <div className="flex flex-col gap-0.5">
                      <button className="text-left text-sm py-2 px-3 rounded-md hover:bg-[var(--g-surface-hover)] text-gray-300 truncate transition-colors">
                        E-commerce Checkout
                      </button>
                      <button className="text-left text-sm py-2 px-3 rounded-md hover:bg-[var(--g-surface-hover)] text-gray-300 truncate transition-colors">
                        Analytics Dashboard
                      </button>
                    </div>
                  </div>
                  <div>
                    <h3 className="text-[11px] font-semibold text-[var(--g-text-muted)] uppercase tracking-wider mb-2 px-2">
                      Examples
                    </h3>
                    <div className="flex flex-col gap-0.5">
                      <button className="text-left text-sm py-2 px-3 rounded-md hover:bg-[var(--g-surface-hover)] text-gray-300 truncate transition-colors">
                        Social App Feed
                      </button>
                      <button className="text-left text-sm py-2 px-3 rounded-md hover:bg-[var(--g-surface-hover)] text-gray-300 truncate transition-colors">
                        Music Player UI
                      </button>
                    </div>
                  </div>
                </m.div>
              ) : (
                <m.div
                  key="gcp-nav"
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: 10 }}
                  transition={{ duration: 0.2 }}
                  className="flex flex-col gap-1"
                >
                  <button className="flex items-center gap-3 text-sm py-2 px-3 rounded-md hover:bg-[var(--g-surface-hover)] text-gray-300 transition-colors">
                    <LayoutTemplate size={16} className="text-blue-400" /> Atelier Studio
                  </button>
                  <div className="h-px bg-[var(--g-outline)] my-2" />
                  <button className="flex items-center gap-3 text-sm py-2 px-3 rounded-md hover:bg-[var(--g-surface-hover)] text-gray-300 transition-colors">
                    <Cloud size={16} /> IAM & Admin
                  </button>
                  <button className="flex items-center gap-3 text-sm py-2 px-3 rounded-md hover:bg-[var(--g-surface-hover)] text-gray-300 transition-colors">
                    <CreditCard size={16} /> Quotas & Billing
                  </button>
                  <button className="flex items-center gap-3 text-sm py-2 px-3 rounded-md hover:bg-[var(--g-surface-hover)] text-gray-300 transition-colors">
                    <History size={16} /> Model Registry
                  </button>
                </m.div>
              )}
            </AnimatePresence>
          </div>
        </m.aside>

        {/* Main Content Area */}
        <main className="flex-1 flex flex-col relative h-full">
          {/* Top Header */}
          <header className="h-16 flex items-center justify-end px-6 border-b border-[var(--g-outline)] bg-transparent">
            <div
              className="w-8 h-8 rounded-full bg-[var(--g-primary-blue)] flex items-center justify-center text-xs font-bold text-white cursor-pointer hover:bg-[var(--g-primary-blue-hover)] transition-colors shadow-sm"
              title={user.email}
            >
              {getUserInitials()}
            </div>
          </header>

          {/* Center Stage */}
          <div className="flex-1 flex flex-col items-center justify-center p-8 overflow-y-auto">
            <m.h1
              initial={{ y: 20, opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              transition={{ delay: 0.1, duration: 0.6, ease: 'easeOut' }}
              className="text-[44px] sm:text-[56px] font-medium mb-10 text-center text-white"
            >
              Welcome to Stitch.
            </m.h1>

            <m.div
              initial={{ y: 30, opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              transition={{ delay: 0.2, duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
              className={`w-full max-w-3xl g-card flex flex-col transition-all duration-300 ease-in-out ${isFocused ? 'ring-1 ring-[var(--g-primary-blue)] shadow-[0_0_24px_rgba(26,115,232,0.15)] !bg-[var(--g-surface-hover)]' : ''}`}
            >
              <div className="p-5">
                <textarea
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  onFocus={() => setIsFocused(true)}
                  onBlur={() => setIsFocused(false)}
                  placeholder="What native mobile app shall we design?"
                  className="w-full bg-transparent text-[17px] text-white placeholder-[var(--g-text-muted)] outline-none resize-none overflow-hidden min-h-[60px]"
                  style={{ height: Math.max(60, prompt.split('\n').length * 24 + 12) + 'px' }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault();
                      handleGenerate();
                    }
                  }}
                />
              </div>

              {/* Bottom Control Bar */}
              <div className="flex items-center justify-between px-4 py-3 border-t border-[var(--g-outline)] bg-transparent">
                <div className="flex items-center gap-2">
                  <button
                    className="w-8 h-8 rounded-full flex items-center justify-center bg-[var(--g-outline)] hover:bg-[#3d3f44] transition-colors text-white"
                    aria-label="Add attachment"
                  >
                    <Plus size={18} />
                  </button>

                  {/* App/Web Toggle */}
                  <div className="flex items-center bg-[var(--g-bg)] rounded-full border border-[var(--g-outline)] overflow-hidden">
                    <button
                      onClick={() => setDeviceType('app')}
                      className={`flex items-center gap-1.5 px-3 py-1.5 text-sm transition-colors ${deviceType === 'app' ? 'bg-[var(--g-outline)] text-white' : 'text-gray-400 hover:text-white'}`}
                    >
                      <Smartphone size={14} /> App
                    </button>
                    <button
                      onClick={() => setDeviceType('web')}
                      className={`flex items-center gap-1.5 px-3 py-1.5 text-sm transition-colors ${deviceType === 'web' ? 'bg-[var(--g-outline)] text-white' : 'text-gray-400 hover:text-white'}`}
                    >
                      <Monitor size={14} /> Web
                    </button>
                  </div>

                  <button className="h-8 px-3 rounded-full border border-[var(--g-outline)] flex items-center gap-1.5 text-sm text-gray-300 hover:bg-[var(--g-surface-hover)] transition-colors">
                    <Palette size={14} /> Style
                  </button>
                </div>

                <div className="flex items-center gap-2">
                  <button className="h-8 px-3 rounded-full border border-[var(--g-outline)] flex items-center gap-1.5 text-sm text-gray-300 hover:bg-[var(--g-surface-hover)] transition-colors">
                    Gemini 2.5 Pro <ChevronDown size={14} className="text-gray-500" />
                  </button>
                  <button
                    className="w-8 h-8 rounded-full flex items-center justify-center text-gray-400 hover:text-white hover:bg-[var(--g-surface-hover)] transition-colors"
                    aria-label="Voice input"
                  >
                    <Mic size={18} />
                  </button>
                  <button
                    onClick={handleGenerate}
                    disabled={!prompt.trim()}
                    className="w-8 h-8 rounded-full flex items-center justify-center bg-[var(--g-primary-blue)] text-white hover:bg-[var(--g-primary-blue-hover)] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    aria-label="Generate"
                  >
                    <Send size={16} className="ml-0.5" />
                  </button>
                </div>
              </div>
            </m.div>
          </div>
        </main>
      </div>
    </LazyMotion>
  );
}
