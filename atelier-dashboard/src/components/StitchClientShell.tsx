'use client';
/* eslint-disable @typescript-eslint/no-explicit-any */

import React, { useState, useRef, useCallback, useEffect } from 'react';
import { LazyMotion, domAnimation, m, AnimatePresence } from 'framer-motion';
import {
  Smartphone,
  Monitor,
  Mic,
  Send,
  ChevronDown,
  Settings,
  BookOpen,
  FileText,
  Shield,
  LifeBuoy,
  LogOut,
  X,
  Check,
  Copy,
  Menu,
  LayoutTemplate,
  Hammer,
  Server,
  ShieldCheck,
  LineChart,
  ChevronRight,
  KanbanSquare,
  Bot,
} from 'lucide-react';
import { useRouter } from 'next/navigation';
import { onIdTokenChanged } from 'firebase/auth';
import { auth } from '@/lib/firebase';
import { prettifyProjectName } from '@/lib/project-utils';
import PillarBuild from '@/components/platform/PillarBuild';
import PillarScale from '@/components/platform/PillarScale';
import PillarGovern from '@/components/platform/PillarGovern';
import PillarOptimize from '@/components/platform/PillarOptimize';
import { getAgents } from '@/lib/api';
import type { AgentSummary } from '@/lib/api';

type SidebarMode = 'stitch' | 'platform';
type DashboardView = 'generate' | 'build' | 'scale' | 'govern' | 'optimize';

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

  useEffect(() => {
    if (!auth) return;
    const unsubscribe = onIdTokenChanged(auth, async (firebaseUser) => {
      if (firebaseUser) {
        try {
          const token = await firebaseUser.getIdToken();
          const userStr = localStorage.getItem('user');
          if (userStr) {
            const userObj = JSON.parse(userStr) as UserSession;
            if (userObj.token !== token) {
              userObj.token = token;
              localStorage.setItem('user', JSON.stringify(userObj));
              setUser(userObj);
            }
          }
        } catch (err) {
          console.error('Failed to sync Firebase token:', err);
        }
      }
    });
    return () => unsubscribe();
  }, []);

  return { user, initRef };
}

// ---------------------------------------------------------------------------
// Pillar metadata (drives sidebar nav and header label)
// ---------------------------------------------------------------------------

const PILLARS: {
  id: DashboardView & ('build' | 'scale' | 'govern' | 'optimize');
  label: string;
  icon: React.ReactNode;
}[] = [
  { id: 'build', label: 'Build', icon: <Hammer size={15} /> },
  { id: 'scale', label: 'Scale', icon: <Server size={15} /> },
  { id: 'govern', label: 'Govern', icon: <ShieldCheck size={15} /> },
  { id: 'optimize', label: 'Optimize', icon: <LineChart size={15} /> },
];

// ---------------------------------------------------------------------------
// Platform sidebar nav
// ---------------------------------------------------------------------------

function PlatformNav({
  view,
  onNavigate,
  onClose,
}: {
  view: DashboardView;
  onNavigate: (v: DashboardView) => void;
  onClose?: () => void;
}) {
  // `userExpanded` is the user's explicit toggle; the effective expansion also
  // honors the active pillar. Deriving it during render (rather than committing
  // it in an effect) keeps this pure and avoids a setState-in-effect.
  const [userExpanded, setUserExpanded] = useState(false);
  const buildExpanded = userExpanded || view === 'build';
  const setBuildExpanded = setUserExpanded;
  const [agents, setAgents] = useState<AgentSummary[]>([]);
  const [agentsLoaded, setAgentsLoaded] = useState(false);

  // Load agent roster once when Build expands. All state transitions run inside
  // the async closure (never synchronously in the effect body).
  useEffect(() => {
    if (!buildExpanded || agentsLoaded) return;

    const run = async () => {
      let token: string | null = null;
      try {
        const raw = typeof window !== 'undefined' ? localStorage.getItem('user') : null;
        token = raw ? (JSON.parse(raw) as { token: string }).token : null;
      } catch {
        token = null;
      }
      if (!token) {
        setAgentsLoaded(true);
        return;
      }
      try {
        const res = await getAgents(token);
        // /agents returns an envelope { available, agents } — guard before use.
        setAgents(res.available ? res.agents : []);
      } catch {
        // Swallow — the roster is a non-critical sidebar affordance.
      } finally {
        setAgentsLoaded(true);
      }
    };

    void run();
  }, [buildExpanded, agentsLoaded]);

  const nav = (v: DashboardView) => {
    onNavigate(v);
    onClose?.();
  };

  return (
    <div className="flex flex-col gap-0.5">
      {/* Atelier Studio link */}
      <button
        onClick={() => nav('generate')}
        className={`flex items-center gap-2.5 text-sm py-2 px-3 rounded-md transition-colors w-full text-left ${
          view === 'generate'
            ? 'bg-[var(--g-info)]/10 text-[var(--g-info)]'
            : 'text-[var(--g-text)] hover:bg-[var(--g-surface-hover)]'
        }`}
      >
        <LayoutTemplate
          size={15}
          className={view === 'generate' ? 'text-[var(--g-info)]' : 'text-[var(--g-text-muted)]'}
        />
        Atelier Studio
      </button>

      {/* Pipeline Board link */}
      <a
        href="/board"
        onClick={() => onClose?.()}
        className="flex items-center gap-2.5 text-sm py-2 px-3 rounded-md transition-colors w-full text-left text-[var(--g-text)] hover:bg-[var(--g-surface-hover)]"
      >
        <KanbanSquare size={15} className="text-[var(--g-text-muted)]" />
        Pipeline Board
      </a>

      {/* Divider + Platform label */}
      <div className="h-px bg-[var(--g-outline)] my-2" />
      <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--g-text-muted)] px-3 mb-1">
        Platform
      </p>

      {/* Four pillars */}
      {PILLARS.map((p) => (
        <React.Fragment key={p.id}>
          <button
            onClick={() => {
              if (p.id === 'build') {
                setBuildExpanded((e) => !e);
              }
              nav(p.id);
            }}
            className={`flex items-center justify-between gap-2.5 text-sm py-2 px-3 rounded-md transition-colors w-full text-left ${
              view === p.id
                ? 'bg-[var(--g-info)]/10 text-[var(--g-info)]'
                : 'text-[var(--g-text)] hover:bg-[var(--g-surface-hover)]'
            }`}
          >
            <span className="flex items-center gap-2.5">
              <span
                className={view === p.id ? 'text-[var(--g-info)]' : 'text-[var(--g-text-muted)]'}
              >
                {p.icon}
              </span>
              {p.label}
            </span>
            {p.id === 'build' && (
              <ChevronRight
                size={12}
                className={`transition-transform ${buildExpanded ? 'rotate-90' : ''} ${view === p.id ? 'text-[var(--g-info)]' : 'text-[var(--g-text-muted)]'}`}
              />
            )}
          </button>

          {/* Build > nested Agents */}
          {p.id === 'build' && buildExpanded && agents.length > 0 && (
            <div className="ml-6 flex flex-col gap-0.5">
              {agents.map((agent) => (
                <button
                  key={agent.id}
                  onClick={() => nav('build')}
                  className="flex items-center gap-2 text-xs py-1.5 px-3 rounded-md transition-colors w-full text-left text-[var(--g-text-muted)] hover:text-[var(--g-text)] hover:bg-[var(--g-surface-hover)]"
                  title={`${agent.task_type ?? agent.kind} — ${agent.model_id}`}
                >
                  <Bot size={11} className="shrink-0" />
                  <span className="truncate">{agent.name}</span>
                </button>
              ))}
            </div>
          )}
        </React.Fragment>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Pillar label for the header breadcrumb
// ---------------------------------------------------------------------------

function getPillarLabel(view: DashboardView): string {
  switch (view) {
    case 'build':
      return 'Platform > Build';
    case 'scale':
      return 'Platform > Scale';
    case 'govern':
      return 'Platform > Govern';
    case 'optimize':
      return 'Platform > Optimize';
    default:
      return 'Atelier Studio';
  }
}

export default function StitchClientShell() {
  const [sidebarMode, setSidebarMode] = useState<SidebarMode>('stitch');
  const [view, setView] = useState<DashboardView>('generate');
  const [prompt, setPrompt] = useState('');
  const [deviceType, setDeviceType] = useState<'app' | 'web'>('app');
  const [isFocused, setIsFocused] = useState(false);
  const { user, initRef } = useClientAuth();
  const router = useRouter();

  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [copiedField, setCopiedField] = useState<string | null>(null);
  const [tokenUsage, setTokenUsage] = useState<{
    input?: number;
    output?: number;
    thinking?: number;
    cumulative_user_tokens?: number;
  } | null>(null);
  const [isMobileSidebarOpen, setIsMobileSidebarOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (user?.uid) {
      try {
        const storedUsage = localStorage.getItem(`atelier_last_token_usage_${user.uid}`);
        if (storedUsage) {
          // eslint-disable-next-line react-hooks/set-state-in-effect
          setTokenUsage(JSON.parse(storedUsage));
        }
      } catch (e) {
        console.error('Failed to load token usage from localStorage:', e);
      }
    }
  }, [isSettingsOpen, user?.uid]);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setIsMenuOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleLogout = () => {
    localStorage.removeItem('user');
    router.push('/login');
  };

  const handleCopy = (text: string, field: string) => {
    navigator.clipboard.writeText(text);
    setCopiedField(field);
    setTimeout(() => setCopiedField(null), 2000);
  };

  const [selectedModel, setSelectedModel] = useState('gemini-2.5-pro');
  const [projects, setProjects] = useState<Project[]>([]);
  const [isRecording, setIsRecording] = useState(false);
  const [voiceUnsupported, setVoiceUnsupported] = useState(false);
  const recognitionRef = useRef<any>(null);

  useEffect(() => {
    try {
      const stored = localStorage.getItem('atelier_projects');
      if (stored) {
        // eslint-disable-next-line react-hooks/set-state-in-effect
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
      setVoiceUnsupported(true);
      setTimeout(() => setVoiceUnsupported(false), 3000);
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
    router.push(
      `/studio/${briefId}?brief=${encodeURIComponent(prompt)}&model=${selectedModel}&device=${deviceType}`
    );
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
        {/* Desktop Sidebar */}
        <m.aside
          className="hidden lg:flex w-64 border-r border-[var(--g-outline)] bg-transparent flex-col"
          initial={{ x: -20, opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
        >
          <div className="h-16 flex items-center px-4 border-b border-[var(--g-outline)]">
            <button
              onClick={() => setSidebarMode((prev) => (prev === 'stitch' ? 'platform' : 'stitch'))}
              className="p-2 rounded-full hover:bg-[var(--g-surface-hover)] transition-colors"
              aria-label="Toggle sidebar mode"
            >
              <Menu size={20} className="text-[var(--g-text-muted)]" />
            </button>
            <span className="ml-3 font-medium text-[15px] tracking-wide text-white flex items-center gap-2">
              {sidebarMode === 'stitch' && (
                <span className="w-2.5 h-2.5 rounded-full bg-[var(--g-primary-blue)]" />
              )}
              {sidebarMode === 'stitch' ? 'Atelier Studio' : 'Agent Platform'}
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
                              `/studio/${proj.id}?brief=${encodeURIComponent(proj.brief)}&model=${selectedModel}&device=${deviceType}`
                            )
                          }
                          className="text-left text-sm py-2 px-3 rounded-md hover:bg-[var(--g-surface-hover)] text-[var(--g-text)] truncate transition-colors w-full block text-left"
                          title={proj.brief}
                        >
                          {prettifyProjectName(proj.brief, proj.id)}
                        </button>
                      ))}
                      {projects.length === 0 && (
                        <div className="text-left text-xs py-2 px-3 text-[var(--g-text-muted)] italic">
                          No projects built yet
                        </div>
                      )}
                    </div>
                  </div>
                </m.div>
              ) : (
                <m.div
                  key="platform-nav"
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: 10 }}
                  transition={{ duration: 0.2 }}
                >
                  <PlatformNav
                    view={view}
                    onNavigate={(v) => {
                      setView(v);
                      if (v === 'generate') setSidebarMode('stitch');
                    }}
                  />
                </m.div>
              )}
            </AnimatePresence>
          </div>
        </m.aside>

        {/* Mobile Sidebar Overlay */}
        <AnimatePresence>
          {isMobileSidebarOpen && (
            <div className="fixed inset-0 z-40 lg:hidden flex">
              {/* Backdrop */}
              <m.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                onClick={() => setIsMobileSidebarOpen(false)}
                className="fixed inset-0 bg-black/60 backdrop-blur-sm"
              />

              {/* Sidebar Content */}
              <m.aside
                initial={{ x: -260 }}
                animate={{ x: 0 }}
                exit={{ x: -260 }}
                transition={{ type: 'spring', damping: 25, stiffness: 200 }}
                className="relative w-64 max-w-xs bg-[var(--g-bg)] border-r border-[var(--g-outline)] h-full flex flex-col z-50 p-3"
              >
                {/* Header with close button */}
                <div className="h-12 flex items-center justify-between px-3 mb-4 border-b border-[var(--g-outline)]">
                  <div className="flex items-center">
                    <button
                      onClick={() =>
                        setSidebarMode((prev) => (prev === 'stitch' ? 'platform' : 'stitch'))
                      }
                      className="mr-2 p-1.5 rounded-md hover:bg-[var(--g-surface-hover)] transition-colors text-[var(--g-text-muted)] hover:text-white"
                      aria-label="Toggle sidebar mode"
                    >
                      <Menu size={18} />
                    </button>
                    <span className="font-medium text-sm text-white flex items-center gap-2">
                      {sidebarMode === 'stitch' && (
                        <span className="w-2.5 h-2.5 rounded-full bg-[var(--g-primary-blue)]" />
                      )}
                      {sidebarMode === 'stitch' ? 'Atelier Studio' : 'Agent Platform'}
                    </span>
                  </div>
                  <button
                    onClick={() => setIsMobileSidebarOpen(false)}
                    className="p-1 text-[var(--g-text-muted)] hover:text-white rounded-md"
                    aria-label="Close sidebar"
                  >
                    <X size={18} />
                  </button>
                </div>

                <div className="flex-1 overflow-y-auto">
                  <AnimatePresence mode="wait">
                    {sidebarMode === 'stitch' ? (
                      <m.div
                        key="stitch-nav-mobile"
                        initial={{ opacity: 0, x: -10 }}
                        animate={{ opacity: 1, x: 0 }}
                        exit={{ opacity: 0, x: 10 }}
                        transition={{ duration: 0.2 }}
                        className="flex flex-col gap-4"
                      >
                        <div className="flex bg-[var(--g-surface)] rounded-full p-1 border border-[var(--g-outline)]">
                          <button
                            onClick={() => {
                              setView('generate');
                              setSidebarMode('stitch');
                              setIsMobileSidebarOpen(false);
                            }}
                            className={`flex-1 text-xs py-1.5 px-3 rounded-full transition-colors ${view === 'generate' ? 'bg-[var(--g-outline)] text-white font-medium shadow-sm' : 'text-[var(--g-text-muted)] hover:text-white'}`}
                          >
                            My projects
                          </button>
                        </div>

                        <div>
                          <h3 className="text-[10px] font-semibold text-[var(--g-text-muted)] uppercase tracking-wider mb-2 px-2">
                            Last 30 days
                          </h3>
                          <div className="flex flex-col gap-0.5">
                            {projects.map((proj) => (
                              <button
                                key={proj.id}
                                onClick={() => {
                                  setIsMobileSidebarOpen(false);
                                  router.push(
                                    `/studio/${proj.id}?brief=${encodeURIComponent(proj.brief)}&model=${selectedModel}&device=${deviceType}`
                                  );
                                }}
                                className="text-left text-sm py-2 px-3 rounded-md hover:bg-[var(--g-surface-hover)] text-[var(--g-text)] truncate transition-colors w-full block text-left"
                                title={proj.brief}
                              >
                                {prettifyProjectName(proj.brief, proj.id)}
                              </button>
                            ))}
                            {projects.length === 0 && (
                              <div className="text-left text-xs py-2 px-3 text-[var(--g-text-muted)] italic">
                                No projects built yet
                              </div>
                            )}
                          </div>
                        </div>
                      </m.div>
                    ) : (
                      <m.div
                        key="platform-nav-mobile"
                        initial={{ opacity: 0, x: -10 }}
                        animate={{ opacity: 1, x: 0 }}
                        exit={{ opacity: 0, x: 10 }}
                        transition={{ duration: 0.2 }}
                      >
                        <PlatformNav
                          view={view}
                          onNavigate={(v) => {
                            setView(v);
                            if (v === 'generate') setSidebarMode('stitch');
                          }}
                          onClose={() => setIsMobileSidebarOpen(false)}
                        />
                      </m.div>
                    )}
                  </AnimatePresence>
                </div>
              </m.aside>
            </div>
          )}
        </AnimatePresence>

        {/* Main Content Area */}
        <main className="flex-1 flex flex-col relative h-full">
          {/* Top Header */}
          <header className="h-16 flex items-center justify-between lg:justify-end px-6 border-b border-[var(--g-outline)] bg-transparent">
            <button
              onClick={() => setIsMobileSidebarOpen(true)}
              className="lg:hidden p-2 text-[var(--g-text-muted)] hover:text-white hover:bg-[var(--g-surface-hover)] rounded-md focus:outline-none focus:ring-1 focus:ring-[var(--g-primary-blue)] transition-colors"
              aria-label="Open sidebar"
            >
              <Menu size={20} />
            </button>
            <div className="relative" ref={menuRef}>
              <button
                onClick={() => setIsMenuOpen(!isMenuOpen)}
                className="w-8 h-8 rounded-full bg-[var(--g-primary-blue)] flex items-center justify-center text-xs font-bold text-white cursor-pointer hover:bg-[var(--g-primary-blue-hover)] transition-colors shadow-sm focus:outline-none focus:ring-1 focus:ring-[var(--g-primary-blue)]"
                title={user.email}
                aria-haspopup="true"
                aria-expanded={isMenuOpen}
              >
                {getUserInitials()}
              </button>

              {isMenuOpen && (
                <div className="absolute right-0 mt-2 w-60 bg-[var(--g-surface)]/95 border border-[var(--g-outline)] rounded-lg shadow-2xl backdrop-blur-md p-2 z-50 animate-in fade-in slide-in-from-top-1 duration-200">
                  <div className="px-3 py-1.5 border-b border-[var(--g-outline)] mb-1">
                    <p className="text-xs font-medium text-white truncate">{user.displayName}</p>
                    <p className="text-[10px] text-[var(--g-text-muted)] truncate">{user.email}</p>
                  </div>

                  <div className="space-y-0.5">
                    <button
                      onClick={() => {
                        setIsSettingsOpen(true);
                        setIsMenuOpen(false);
                      }}
                      className="w-full flex items-center gap-2 px-3 py-1.5 rounded text-left text-xs text-[var(--g-text)] hover:bg-[var(--g-surface-hover)] hover:text-white transition-colors cursor-pointer"
                    >
                      <Settings size={12} className="text-[var(--g-text-muted)]" />
                      Account Settings
                    </button>
                    <a
                      href="https://atelier.autonomous-agent.dev/docs"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="w-full flex items-center gap-2 px-3 py-1.5 rounded text-left text-xs text-[var(--g-text)] hover:bg-[var(--g-surface-hover)] hover:text-white transition-colors cursor-pointer"
                    >
                      <BookOpen size={12} className="text-[var(--g-text-muted)]" />
                      Documentation
                    </a>
                    <a
                      href="/terms"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="w-full flex items-center gap-2 px-3 py-1.5 rounded text-left text-xs text-[var(--g-text)] hover:bg-[var(--g-surface-hover)] hover:text-white transition-colors cursor-pointer"
                    >
                      <FileText size={12} className="text-[var(--g-text-muted)]" />
                      Terms of Service
                    </a>
                    <a
                      href="/privacy"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="w-full flex items-center gap-2 px-3 py-1.5 rounded text-left text-xs text-[var(--g-text)] hover:bg-[var(--g-surface-hover)] hover:text-white transition-colors cursor-pointer"
                    >
                      <Shield size={12} className="text-[var(--g-text-muted)]" />
                      Privacy Policy
                    </a>
                    <a
                      href="mailto:support@atelier.autonomous-agent.dev"
                      className="w-full flex items-center gap-2 px-3 py-1.5 rounded text-left text-xs text-[var(--g-text)] hover:bg-[var(--g-surface-hover)] hover:text-white transition-colors cursor-pointer"
                    >
                      <LifeBuoy size={12} className="text-[var(--g-text-muted)]" />
                      Help &amp; Support
                    </a>
                  </div>

                  <div className="h-px bg-[var(--g-outline)] my-1" />

                  <button
                    onClick={handleLogout}
                    className="w-full flex items-center gap-2 px-3 py-1.5 rounded text-left text-xs text-[var(--g-error)] hover:bg-[var(--g-error)]/10 hover:text-red-300 transition-colors cursor-pointer"
                  >
                    <LogOut size={12} />
                    Logout
                  </button>
                </div>
              )}
            </div>
          </header>

          {/* Center Stage */}
          <div className="flex-1 flex flex-col overflow-y-auto">
            {/* Platform pillars — full-width scrollable panel */}
            {(view === 'build' || view === 'scale' || view === 'govern' || view === 'optimize') && (
              <div className="flex-1 p-6">
                <h2 className="text-xs font-semibold uppercase tracking-widest text-[var(--g-text-muted)] mb-5">
                  {getPillarLabel(view)}
                </h2>
                {view === 'build' && <PillarBuild />}
                {view === 'scale' && <PillarScale />}
                {view === 'govern' && <PillarGovern />}
                {view === 'optimize' && <PillarOptimize />}
              </div>
            )}

            {/* Atelier Studio — centered generate form */}
            {view === 'generate' && (
              <div className="flex-1 flex flex-col items-center justify-center p-4 sm:p-8">
                <>
                  <m.h1
                    initial={{ y: 20, opacity: 0 }}
                    animate={{ y: 0, opacity: 1 }}
                    transition={{ delay: 0.1, duration: 0.6, ease: 'easeOut' }}
                    className="text-[32px] sm:text-[44px] md:text-[56px] font-medium mb-10 text-center text-white"
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
                    <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 border-t border-[var(--g-outline)] bg-transparent">
                      <div className="flex items-center gap-2">
                        {/* App/Web Toggle */}
                        <div className="flex items-center bg-[var(--g-bg)] rounded-full border border-[var(--g-outline)] overflow-hidden">
                          <button
                            onClick={() => setDeviceType('app')}
                            className={`flex items-center gap-1.5 px-3 py-1.5 text-xs sm:text-sm transition-colors ${deviceType === 'app' ? 'bg-[var(--g-outline)] text-white' : 'text-[var(--g-text-muted)] hover:text-white'}`}
                          >
                            <Smartphone size={14} /> App
                          </button>
                          <button
                            onClick={() => setDeviceType('web')}
                            className={`flex items-center gap-1.5 px-3 py-1.5 text-xs sm:text-sm transition-colors ${deviceType === 'web' ? 'bg-[var(--g-outline)] text-white' : 'text-[var(--g-text-muted)] hover:text-white'}`}
                          >
                            <Monitor size={14} /> Web
                          </button>
                        </div>
                      </div>

                      <div className="flex items-center gap-2">
                        <div className="relative">
                          <select
                            value={selectedModel}
                            onChange={(e) => setSelectedModel(e.target.value)}
                            className="appearance-none h-8 px-3 pr-8 rounded-full border border-[var(--g-outline)] bg-transparent text-xs sm:text-sm text-[var(--g-text)] hover:bg-[var(--g-surface-hover)] focus:outline-none focus:ring-1 focus:ring-[var(--g-primary-blue)] cursor-pointer transition-colors"
                            aria-label="Select Model"
                          >
                            <option
                              value="gemini-2.5-pro"
                              className="bg-[var(--g-surface)] text-white"
                            >
                              Gemini 2.5 Pro
                            </option>
                            <option
                              value="gemini-2.5-flash"
                              className="bg-[var(--g-surface)] text-white"
                            >
                              Gemini 2.5 Flash
                            </option>
                          </select>
                          <ChevronDown
                            size={14}
                            className="absolute right-3 top-1/2 -translate-y-1/2 text-[var(--g-text-muted)] pointer-events-none"
                          />
                        </div>
                        <div className="relative">
                          <button
                            onClick={toggleVoiceInput}
                            className={`w-8 h-8 rounded-full flex items-center justify-center transition-all ${isRecording ? 'text-red-500 bg-[var(--g-error)]/10 animate-pulse border border-red-500/40 shadow-[0_0_12px_rgba(239,68,68,0.2)]' : 'text-[var(--g-text-muted)] hover:text-white hover:bg-[var(--g-surface-hover)]'}`}
                            aria-label={isRecording ? 'Stop voice input' : 'Start voice input'}
                          >
                            <Mic size={18} />
                          </button>
                          {voiceUnsupported && (
                            <div className="absolute bottom-10 right-0 whitespace-nowrap text-[10px] text-[var(--g-warning)] bg-[var(--g-surface)] border border-[var(--g-outline)] rounded px-2 py-1 shadow-lg pointer-events-none">
                              Voice input requires Chrome
                            </div>
                          )}
                        </div>
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
              </div>
            )}
          </div>
        </main>
      </div>

      {/* Account Settings Modal */}
      <AnimatePresence>
        {isSettingsOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            {/* Backdrop */}
            <m.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setIsSettingsOpen(false)}
              className="absolute inset-0 bg-black/60 backdrop-blur-md"
            />

            {/* Modal Content */}
            <m.div
              initial={{ scale: 0.95, opacity: 0, y: 10 }}
              animate={{ scale: 1, opacity: 1, y: 0 }}
              exit={{ scale: 0.95, opacity: 0, y: 10 }}
              transition={{ type: 'spring', duration: 0.4 }}
              className="relative w-full max-w-2xl bg-[var(--g-bg)]/95 border border-[var(--g-outline)] rounded-lg shadow-2xl overflow-hidden flex flex-col max-h-[85vh]"
            >
              {/* Header */}
              <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--g-outline)] bg-black/20">
                <div className="flex items-center gap-2">
                  <Settings size={16} className="text-[var(--g-primary-blue)]" />
                  <h2 className="text-sm font-semibold text-white">Account Settings</h2>
                </div>
                <button
                  onClick={() => setIsSettingsOpen(false)}
                  className="text-[var(--g-text-muted)] hover:text-white p-1 rounded-md hover:bg-[var(--g-surface-hover)]/10 transition-colors cursor-pointer"
                  aria-label="Close settings"
                >
                  <X size={16} />
                </button>
              </div>

              {/* Body */}
              <div className="flex-1 overflow-y-auto p-6 space-y-6">
                {/* User Profile Info */}
                <div className="bg-black/20 rounded-lg border border-[var(--g-outline)] p-4 space-y-3 text-left">
                  <h3 className="text-xs font-semibold text-[var(--g-text-muted)] uppercase tracking-wider">
                    User Profile
                  </h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
                    <div>
                      <label className="text-[var(--g-text-muted)] block mb-0.5">
                        Display Name
                      </label>
                      <div className="font-medium text-white">{user?.displayName || '—'}</div>
                    </div>
                    <div>
                      <label className="text-[var(--g-text-muted)] block mb-0.5">
                        Email Address
                      </label>
                      <div className="font-medium text-white">{user?.email || '—'}</div>
                    </div>
                  </div>

                  <div className="pt-2 border-t border-[var(--g-outline)]/50 space-y-2 text-xs">
                    <div className="flex justify-between items-center">
                      <div>
                        <label className="text-[var(--g-text-muted)] block mb-0.5">
                          User ID (UID)
                        </label>
                        <div className="font-mono text-[var(--g-text)] select-all truncate max-w-[280px] md:max-w-[400px]">
                          {user?.uid || '—'}
                        </div>
                      </div>
                      {user?.uid && (
                        <button
                          onClick={() => handleCopy(user.uid, 'uid')}
                          className="shrink-0 p-1.5 rounded hover:bg-[var(--g-surface-hover)]/10 text-[var(--g-text-muted)] hover:text-white transition-colors cursor-pointer"
                          title="Copy UID"
                        >
                          {copiedField === 'uid' ? (
                            <Check size={14} className="text-[var(--g-success)]" />
                          ) : (
                            <Copy size={14} />
                          )}
                        </button>
                      )}
                    </div>

                    <div className="flex justify-between items-center pt-2 border-t border-[var(--g-outline)]/50">
                      <div>
                        <label className="text-[var(--g-text-muted)] block mb-0.5">Tenant ID</label>
                        <div className="font-mono text-[var(--g-text)] select-all truncate max-w-[280px] md:max-w-[400px]">
                          {user?.tenant_id || '—'}
                        </div>
                      </div>
                      {user?.tenant_id && (
                        <button
                          onClick={() => handleCopy(user.tenant_id, 'tenant')}
                          className="shrink-0 p-1.5 rounded hover:bg-[var(--g-surface-hover)]/10 text-[var(--g-text-muted)] hover:text-white transition-colors cursor-pointer"
                          title="Copy Tenant ID"
                        >
                          {copiedField === 'tenant' ? (
                            <Check size={14} className="text-[var(--g-success)]" />
                          ) : (
                            <Copy size={14} />
                          )}
                        </button>
                      )}
                    </div>
                  </div>
                </div>

                {/* GCP & Platform Config */}
                <div className="bg-black/20 rounded-lg border border-[var(--g-outline)] p-4 space-y-3 text-left">
                  <h3 className="text-xs font-semibold text-[var(--g-text-muted)] uppercase tracking-wider">
                    Workspace &amp; GCP Environment
                  </h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
                    <div className="flex items-center justify-between pr-2">
                      <div>
                        <label className="text-[var(--g-text-muted)] block mb-0.5">
                          GCP Project
                        </label>
                        <span className="font-mono text-[var(--g-text)]">atelier-build-2026</span>
                      </div>
                      <span className="px-2 py-0.5 rounded-full text-[10px] bg-[var(--g-success)]/10 text-[var(--g-success)] border border-[var(--g-success)]/20 font-medium flex items-center gap-1">
                        <span className="w-1.5 h-1.5 rounded-full bg-[var(--g-success)] animate-pulse" />
                        Connected
                      </span>
                    </div>
                    <div>
                      <label className="text-[var(--g-text-muted)] block mb-0.5">
                        Active Billing Tier
                      </label>
                      <div className="font-medium text-white flex items-center gap-1.5">
                        <span>Enterprise AI Developer (Self-Serve)</span>
                      </div>
                    </div>
                    <div>
                      <label className="text-[var(--g-text-muted)] block mb-0.5">
                        Base API URL
                      </label>
                      <span className="font-mono text-[var(--g-text)] truncate block max-w-[280px]">
                        https://atelier-dashboard-537337457799.us-central1.run.app/
                      </span>
                    </div>
                    <div>
                      <label className="text-[var(--g-text-muted)] block mb-0.5">
                        Platform Status
                      </label>
                      <span className="text-[var(--g-success)] font-medium">
                        All Services Operational
                      </span>
                    </div>
                  </div>
                </div>

                {/* Token Allocation & Usage */}
                <div className="bg-black/20 rounded-lg border border-[var(--g-outline)] p-4 space-y-4 text-left">
                  <div className="flex justify-between items-center">
                    <h3 className="text-xs font-semibold text-[var(--g-text-muted)] uppercase tracking-wider">
                      Token Allocation &amp; Usage
                    </h3>
                    <span className="px-2 py-0.5 rounded text-[10px] bg-[var(--g-primary-blue)]/20 text-[var(--g-primary-blue)] border border-[var(--g-primary-blue)]/30 font-mono">
                      Limit: 5,000,000
                    </span>
                  </div>

                  {(() => {
                    const TOKEN_CAP = 5_000_000;
                    const cumulative = tokenUsage?.cumulative_user_tokens ?? 0;
                    const pct = Math.min(100, (cumulative / TOKEN_CAP) * 100);
                    const remaining = TOKEN_CAP - cumulative;
                    const barColor =
                      pct >= 90
                        ? 'bg-[var(--g-error)]'
                        : pct >= 70
                          ? 'bg-[var(--g-warning)]'
                          : 'bg-[var(--g-success)]';

                    return (
                      <div className="space-y-4">
                        <div>
                          <div className="flex justify-between items-baseline mb-1.5 text-xs">
                            <span className="text-[var(--g-text-muted)]">Cumulative Usage</span>
                            <span className="font-mono text-white">
                              {cumulative.toLocaleString()} / {TOKEN_CAP.toLocaleString()} (
                              {pct.toFixed(1)}%)
                            </span>
                          </div>

                          {/* Progress bar */}
                          <div className="w-full h-2 rounded-full bg-[var(--g-outline)]/20 overflow-hidden mb-2">
                            <div
                              className={`h-full rounded-full transition-all duration-500 ${barColor}`}
                              style={{ width: `${pct}%` }}
                            />
                          </div>

                          <div className="flex justify-between items-baseline text-xs">
                            <span className="text-[var(--g-text-muted)]">Available Headroom</span>
                            <span
                              className={`font-mono font-bold ${pct >= 90 ? 'text-[var(--g-error)]' : pct >= 70 ? 'text-[var(--g-warning)]' : 'text-[var(--g-success)]'}`}
                            >
                              {remaining.toLocaleString()} tokens
                            </span>
                          </div>
                        </div>

                        {/* Breakdown */}
                        <div className="grid grid-cols-3 gap-2 pt-2 border-t border-[var(--g-outline)]/50">
                          {[
                            { label: 'Input Tokens', val: tokenUsage?.input },
                            { label: 'Output Tokens', val: tokenUsage?.output },
                            { label: 'Thinking Tokens', val: tokenUsage?.thinking },
                          ].map(({ label, val }) => (
                            <div
                              key={label}
                              className="bg-black/30 border border-[var(--g-outline)] rounded p-2 text-center"
                            >
                              <div className="text-[10px] text-[var(--g-text-muted)] block mb-0.5">
                                {label}
                              </div>
                              <div className="text-xs font-mono font-semibold text-[var(--g-text)]">
                                {val != null ? val.toLocaleString() : '0'}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    );
                  })()}
                </div>
              </div>

              {/* Footer */}
              <div className="px-6 py-4 border-t border-[var(--g-outline)] bg-black/20 flex justify-end gap-3">
                <button
                  onClick={() => setIsSettingsOpen(false)}
                  className="px-4 py-1.5 rounded-md border border-[var(--g-outline)] text-xs font-medium text-[var(--g-text)] hover:text-white hover:bg-[var(--g-surface-hover)]/10 transition-colors cursor-pointer"
                >
                  Close
                </button>
              </div>
            </m.div>
          </div>
        )}
      </AnimatePresence>
    </LazyMotion>
  );
}
