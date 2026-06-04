'use client';

import React, { useState, useRef, useCallback, useEffect } from 'react';
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
type DashboardView = 'generate' | 'iam' | 'billing' | 'models';

interface Project {
  id: string;
  brief: string;
  timestamp: number;
}

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

  const [selectedModel, setSelectedModel] = useState('gemini-2.5-pro');
  const [view, setView] = useState<DashboardView>('generate');
  const [projects, setProjects] = useState<Project[]>([]);
  const [isRecording, setIsRecording] = useState(false);
  const recognitionRef = useRef<any>(null);

  useEffect(() => {
    try {
      const stored = localStorage.getItem('atelier_projects');
      if (stored) {
        setProjects(JSON.parse(stored) as Project[]);
      }
    } catch (e) {
      console.error('Failed to load projects from localStorage:', e);
    }
  }, []);

  const toggleVoiceInput = () => {
    if (typeof window === 'undefined') return;
    const SpeechRecognition =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRecognition) {
      alert('Browser Speech Recognition is not supported in this browser. Please use Chrome.');
      return;
    }

    if (isRecording) {
      recognitionRef.current?.stop();
      setIsRecording(false);
    } else {
      const recognition = new SpeechRecognition();
      recognition.continuous = false;
      recognition.interimResults = false;
      recognition.lang = 'en-US';

      recognition.onstart = () => {
        setIsRecording(true);
      };

      recognition.onresult = (event: any) => {
        const transcript = event.results[0][0].transcript;
        setPrompt((prev) => (prev ? prev + ' ' + transcript : transcript));
      };

      recognition.onerror = (e: any) => {
        console.error('Speech recognition error:', e);
        setIsRecording(false);
      };

      recognition.onend = () => {
        setIsRecording(false);
      };

      recognitionRef.current = recognition;
      recognition.start();
    }
  };

  const handleGenerate = () => {
    if (!prompt.trim()) return;
    const briefId = encodeURIComponent(
      prompt.substring(0, 20).replace(/\s+/g, '-').toLowerCase() + '-' + Date.now()
    );
    const newProj = { id: briefId, brief: prompt, timestamp: Date.now() };
    try {
      const stored = localStorage.getItem('atelier_projects') || '[]';
      const parsed = JSON.parse(stored) as Project[];
      const updated = [newProj, ...parsed.filter((p) => p.id !== briefId)].slice(0, 30);
      localStorage.setItem('atelier_projects', JSON.stringify(updated));
    } catch (e) {
      console.error('Failed to save project to localStorage:', e);
    }
    router.push(`/studio/${briefId}?brief=${encodeURIComponent(prompt)}&model=${selectedModel}`);
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
              {sidebarMode === 'stitch' ? 'Atelier Studio' : 'GCP Console'}
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
                    <button
                      onClick={() => {
                        setView('generate');
                        setSidebarMode('stitch');
                      }}
                      className={`flex-1 text-sm py-1.5 px-3 rounded-full transition-colors ${view === 'generate' ? 'bg-[var(--g-outline)] text-white font-medium shadow-sm' : 'text-[var(--g-text-muted)] hover:text-white'}`}
                    >
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
                      {projects.map((proj) => (
                        <button
                          key={proj.id}
                          onClick={() =>
                            router.push(
                              `/studio/${proj.id}?brief=${encodeURIComponent(proj.brief)}&model=${selectedModel}`
                            )
                          }
                          className="text-left text-sm py-2 px-3 rounded-md hover:bg-[var(--g-surface-hover)] text-gray-300 truncate transition-colors w-full block text-left"
                          title={proj.brief}
                        >
                          {proj.brief.length > 25 ? proj.brief.slice(0, 25) + '...' : proj.brief}
                        </button>
                      ))}
                      {projects.length === 0 && (
                        <div className="text-left text-xs py-2 px-3 text-gray-500 italic">
                          No projects built yet
                        </div>
                      )}
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
                  <button
                    onClick={() => {
                      setView('generate');
                      setSidebarMode('stitch');
                    }}
                    className="flex items-center gap-3 text-sm py-2 px-3 rounded-md hover:bg-[var(--g-surface-hover)] text-gray-300 transition-colors w-full text-left"
                  >
                    <LayoutTemplate size={16} className="text-blue-400" /> Atelier Studio
                  </button>
                  <div className="h-px bg-[var(--g-outline)] my-2" />
                  <button
                    onClick={() => setView('iam')}
                    className={`flex items-center gap-3 text-sm py-2 px-3 rounded-md transition-colors w-full text-left ${view === 'iam' ? 'bg-[var(--g-outline)] text-white' : 'text-gray-300 hover:bg-[var(--g-surface-hover)]'}`}
                  >
                    <Cloud size={16} /> IAM &amp; Admin
                  </button>
                  <button
                    onClick={() => setView('billing')}
                    className={`flex items-center gap-3 text-sm py-2 px-3 rounded-md transition-colors w-full text-left ${view === 'billing' ? 'bg-[var(--g-outline)] text-white' : 'text-gray-300 hover:bg-[var(--g-surface-hover)]'}`}
                  >
                    <CreditCard size={16} /> Quotas &amp; Billing
                  </button>
                  <button
                    onClick={() => setView('models')}
                    className={`flex items-center gap-3 text-sm py-2 px-3 rounded-md transition-colors w-full text-left ${view === 'models' ? 'bg-[var(--g-outline)] text-white' : 'text-gray-300 hover:bg-[var(--g-surface-hover)]'}`}
                  >
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
            {view === 'generate' && (
              <>
                <m.h1
                  initial={{ y: 20, opacity: 0 }}
                  animate={{ y: 0, opacity: 1 }}
                  transition={{ delay: 0.1, duration: 0.6, ease: 'easeOut' }}
                  className="text-[44px] sm:text-[56px] font-medium mb-10 text-center text-white"
                >
                  Welcome to Atelier.
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
                      <div className="relative">
                        <select
                          value={selectedModel}
                          onChange={(e) => setSelectedModel(e.target.value)}
                          className="appearance-none h-8 px-3 pr-8 rounded-full border border-[var(--g-outline)] bg-transparent text-sm text-gray-300 hover:bg-[var(--g-surface-hover)] focus:outline-none focus:ring-1 focus:ring-[var(--g-primary-blue)] cursor-pointer transition-colors"
                          aria-label="Select Model"
                        >
                          <option value="gemini-2.5-pro" className="bg-[#1e1f22] text-white">
                            Gemini 2.5 Pro
                          </option>
                          <option value="gemini-2.5-flash" className="bg-[#1e1f22] text-white">
                            Gemini 2.5 Flash
                          </option>
                        </select>
                        <ChevronDown
                          size={14}
                          className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 pointer-events-none"
                        />
                      </div>
                      <button
                        onClick={toggleVoiceInput}
                        className={`w-8 h-8 rounded-full flex items-center justify-center transition-all ${isRecording ? 'text-red-500 bg-red-500/10 animate-pulse border border-red-500/40 shadow-[0_0_12px_rgba(239,68,68,0.2)]' : 'text-gray-400 hover:text-white hover:bg-[var(--g-surface-hover)]'}`}
                        aria-label={isRecording ? 'Stop voice input' : 'Start voice input'}
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
              </>
            )}

            {view === 'iam' && (
              <div className="w-full max-w-4xl p-6 bg-[var(--g-surface)] rounded-xl border border-[var(--g-outline)] shadow-xl text-left">
                <div className="flex justify-between items-center mb-6">
                  <div>
                    <h2 className="text-2xl font-semibold text-white flex items-center gap-2">
                      <Cloud className="text-blue-400" size={24} /> IAM &amp; Admin
                    </h2>
                    <p className="text-sm text-[var(--g-text-muted)] mt-1">
                      Manage organization workspace members, access controls, and developer API
                      credentials.
                    </p>
                  </div>
                  <button
                    onClick={() => setView('generate')}
                    className="px-4 py-2 text-xs font-semibold rounded bg-[var(--g-outline)] hover:bg-[#3d3f44] text-white transition-colors"
                  >
                    Back to Studio
                  </button>
                </div>

                <div className="mb-8">
                  <h3 className="text-sm font-semibold text-white mb-4">Workspace Members</h3>
                  <div className="overflow-hidden rounded-lg border border-[var(--g-outline)] bg-black/20">
                    <table className="w-full border-collapse text-left text-xs">
                      <thead>
                        <tr className="border-b border-[var(--g-outline)] bg-white/5 text-gray-400">
                          <th className="px-4 py-3">Member</th>
                          <th className="px-4 py-3">Role</th>
                          <th className="px-4 py-3">Status</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-[var(--g-outline)] text-gray-300">
                        <tr>
                          <td className="px-4 py-3.5 flex items-center gap-3">
                            <div className="w-7 h-7 rounded-full bg-[var(--g-primary-blue)] flex items-center justify-center text-[10px] font-bold text-white">
                              DM
                            </div>
                            <div>
                              <div className="font-medium text-white">
                                {user.displayName || 'Daniel Manzela'}
                              </div>
                              <div className="text-[10px] text-gray-500">{user.email}</div>
                            </div>
                          </td>
                          <td className="px-4 py-3.5 font-medium text-blue-400">
                            Organization Owner
                          </td>
                          <td className="px-4 py-3.5">
                            <span className="px-2 py-0.5 rounded-full text-[9px] bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                              Active
                            </span>
                          </td>
                        </tr>
                        <tr>
                          <td className="px-4 py-3.5 flex items-center gap-3">
                            <div className="w-7 h-7 rounded-full bg-purple-600 flex items-center justify-center text-[10px] font-bold text-white">
                              AA
                            </div>
                            <div>
                              <div className="font-medium text-white">Atelier Agent</div>
                              <div className="text-[10px] text-gray-500">
                                agent@atelier.autonomous-agent.dev
                              </div>
                            </div>
                          </td>
                          <td className="px-4 py-3.5">Autonomous Specialist</td>
                          <td className="px-4 py-3.5">
                            <span className="px-2 py-0.5 rounded-full text-[9px] bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                              Active
                            </span>
                          </td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </div>

                <div>
                  <h3 className="text-sm font-semibold text-white mb-4">
                    Workspace API Credentials
                  </h3>
                  <div className="p-4 rounded-lg border border-[var(--g-outline)] bg-black/20 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
                    <div className="flex-1">
                      <div className="text-xs font-semibold text-white">
                        Production Agent API Key
                      </div>
                      <div className="text-xs font-mono text-gray-500 mt-1 select-all">
                        at_live_••••••••••••••••••••••••••••••••3a5f9d
                      </div>
                    </div>
                    <button
                      onClick={() => {
                        navigator.clipboard.writeText(`at_live_${user.token.substring(0, 32)}`);
                        alert('API credential copied to clipboard.');
                      }}
                      className="px-3.5 py-1.5 text-xs font-medium rounded border border-[var(--g-outline)] hover:bg-[var(--g-surface-hover)] text-gray-300 transition-colors"
                    >
                      Copy Key
                    </button>
                  </div>
                </div>
              </div>
            )}

            {view === 'billing' && (
              <div className="w-full max-w-4xl p-6 bg-[var(--g-surface)] rounded-xl border border-[var(--g-outline)] shadow-xl text-left">
                <div className="flex justify-between items-center mb-6">
                  <div>
                    <h2 className="text-2xl font-semibold text-white flex items-center gap-2">
                      <CreditCard className="text-blue-400" size={24} /> Quotas &amp; Billing
                    </h2>
                    <p className="text-sm text-[var(--g-text-muted)] mt-1">
                      Monitor your organization token allocation, real-time consumption quotas, and
                      billing status.
                    </p>
                  </div>
                  <button
                    onClick={() => setView('generate')}
                    className="px-4 py-2 text-xs font-semibold rounded bg-[var(--g-outline)] hover:bg-[#3d3f44] text-white transition-colors"
                  >
                    Back to Studio
                  </button>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
                  <div className="p-4 rounded-xl border border-[var(--g-outline)] bg-black/20">
                    <h3 className="text-xs text-gray-400 font-semibold mb-1">Lifetime Token Cap</h3>
                    <div className="text-2xl font-bold text-white font-mono mt-2">5,000,000</div>
                    <div className="w-full h-1.5 rounded-full bg-white/10 overflow-hidden mt-3">
                      <div className="h-full rounded-full bg-emerald-500" style={{ width: '4%' }} />
                    </div>
                    <p className="text-[10px] text-gray-500 mt-2">
                      Approximately 200,000 tokens consumed (4.0%)
                    </p>
                  </div>

                  <div className="p-4 rounded-xl border border-[var(--g-outline)] bg-black/20">
                    <h3 className="text-xs text-gray-400 font-semibold mb-1">
                      Rate Limits (Quota)
                    </h3>
                    <div className="text-lg font-bold text-white font-mono mt-2">1,000 RPM</div>
                    <p className="text-[10px] text-gray-500 mt-1">
                      Gemini 2.5 Pro: 1,000 requests / min
                    </p>
                    <div className="text-lg font-bold text-white font-mono mt-1">2,000 RPM</div>
                    <p className="text-[10px] text-gray-500 mt-1">
                      Gemini 2.5 Flash: 2,000 requests / min
                    </p>
                  </div>

                  <div className="p-4 rounded-xl border border-blue-500/30 bg-blue-500/5 relative overflow-hidden">
                    <div className="absolute right-0 top-0 w-16 h-16 bg-blue-500/10 rounded-full blur-xl pointer-events-none" />
                    <h3 className="text-xs text-blue-400 font-semibold mb-1">Active Plan</h3>
                    <div className="text-xl font-bold text-white mt-2">Enterprise Plus</div>
                    <p className="text-[10px] text-gray-400 mt-1">Tier-1 GenAI Workspace</p>
                    <div className="mt-4 flex items-center gap-1 text-[10px] text-emerald-400 font-semibold">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" /> Account in Good
                      Standing
                    </div>
                  </div>
                </div>

                <div className="p-5 rounded-xl border border-[var(--g-outline)] bg-black/30 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
                  <div>
                    <h4 className="text-sm font-semibold text-white">Payment Method</h4>
                    <p className="text-xs text-[var(--g-text-muted)] mt-1">
                      Default payment card for API overages.
                    </p>
                    <div className="flex items-center gap-2 mt-3 text-xs text-gray-300">
                      <div className="px-2 py-0.5 bg-white/10 rounded text-[10px] font-bold font-mono tracking-widest text-white">
                        VISA
                      </div>
                      <span className="font-mono">•••• •••• •••• 5542</span>
                      <span className="text-gray-500">Exp 08/29</span>
                    </div>
                  </div>
                  <button className="px-4 py-2 text-xs font-semibold rounded border border-[var(--g-outline)] hover:bg-[var(--g-surface-hover)] text-gray-300 transition-colors">
                    Manage Invoices
                  </button>
                </div>
              </div>
            )}

            {view === 'models' && (
              <div className="w-full max-w-4xl p-6 bg-[var(--g-surface)] rounded-xl border border-[var(--g-outline)] shadow-xl text-left">
                <div className="flex justify-between items-center mb-6">
                  <div>
                    <h2 className="text-2xl font-semibold text-white flex items-center gap-2">
                      <History className="text-blue-400" size={24} /> Model Registry
                    </h2>
                    <p className="text-sm text-[var(--g-text-muted)] mt-1">
                      Overview of calibrated Large Language Models deployed across the Atelier
                      specialist pipeline.
                    </p>
                  </div>
                  <button
                    onClick={() => setView('generate')}
                    className="px-4 py-2 text-xs font-semibold rounded bg-[var(--g-outline)] hover:bg-[#3d3f44] text-white transition-colors"
                  >
                    Back to Studio
                  </button>
                </div>

                <div className="space-y-4">
                  <div className="p-4 rounded-xl border border-[var(--g-outline)] bg-black/20 flex justify-between items-start gap-4">
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-semibold text-white">Gemini 2.5 Pro</span>
                        <span className="px-2 py-0.5 rounded-full text-[9px] bg-blue-500/20 text-blue-400 border border-blue-500/30 font-semibold font-mono">
                          Calibrated (Pro)
                        </span>
                      </div>
                      <p className="text-xs text-gray-400 mt-2 leading-relaxed">
                        Optimal model for high-complexity structural reasoning, UX research,
                        consensus gatekeeping, and multi-variable critique audits.
                      </p>
                    </div>
                    <div className="text-right text-xs shrink-0">
                      <div className="text-gray-400">Rate Limit</div>
                      <div className="font-semibold text-white font-mono mt-0.5">1,000 RPM</div>
                    </div>
                  </div>

                  <div className="p-4 rounded-xl border border-[var(--g-outline)] bg-black/20 flex justify-between items-start gap-4">
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-semibold text-white">Gemini 2.5 Flash</span>
                        <span className="px-2 py-0.5 rounded-full text-[9px] bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 font-semibold font-mono">
                          Calibrated (Flash)
                        </span>
                      </div>
                      <p className="text-xs text-gray-400 mt-2 leading-relaxed">
                        Highly responsive and latency-optimized model deployed for HTML canvas
                        candidate design, layout variations, and rapid CSS structure fixes.
                      </p>
                    </div>
                    <div className="text-right text-xs shrink-0">
                      <div className="text-gray-400">Rate Limit</div>
                      <div className="font-semibold text-white font-mono mt-0.5">2,000 RPM</div>
                    </div>
                  </div>

                  <div className="p-4 rounded-xl border border-[var(--g-outline)] bg-black/20 flex justify-between items-start gap-4">
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-semibold text-white">
                          Gemini 2.5 Flash-Lite
                        </span>
                        <span className="px-2 py-0.5 rounded-full text-[9px] bg-purple-500/20 text-purple-400 border border-purple-500/30 font-semibold font-mono">
                          Calibrated (Lite)
                        </span>
                      </div>
                      <p className="text-xs text-gray-400 mt-2 leading-relaxed">
                        Ultra-low latency inference engine configured for cheap style token
                        extraction, semantic parsing, and DOM text alignments.
                      </p>
                    </div>
                    <div className="text-right text-xs shrink-0">
                      <div className="text-gray-400">Rate Limit</div>
                      <div className="font-semibold text-white font-mono mt-0.5">4,000 RPM</div>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        </main>
      </div>
    </LazyMotion>
  );
}
