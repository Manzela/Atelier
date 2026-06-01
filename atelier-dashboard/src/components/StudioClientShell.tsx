'use client';

import React, { useState, useRef, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { LazyMotion, domAnimation, m, AnimatePresence } from 'framer-motion';
import {
  ArrowLeft,
  Play,
  Layout,
  Box,
  Terminal,
  ChevronUp,
  ChevronDown,
  SlidersHorizontal,
  MousePointer2,
  ZoomIn,
  ZoomOut,
  Maximize,
  Smartphone,
  Tablet,
  Monitor,
  Loader2,
  AlertTriangle,
  XCircle,
  ZapOff,
  RotateCcw,
} from 'lucide-react';
import {
  runGenerationStream,
  type StreamCallbacks,
  type DoravScores,
  type NielsenHeuristic,
  type CapReachedData,
} from '@/lib/api';

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

type DeviceWidth = 390 | 768 | 1280;

export default function StudioClientShell({ id }: { id: string }) {
  const router = useRouter();
  const [scale, setScale] = useState(1);
  const [deviceWidth, setDeviceWidth] = useState<DeviceWidth>(1280);
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [temperature, setTemperature] = useState(0.4);
  const [topK, setTopK] = useState(40);
  const [maxTokens, setMaxTokens] = useState(4096);
  const { user, initRef } = useClientAuth();

  const [status, setStatus] = useState<
    'idle' | 'generating' | 'converged' | 'degraded' | 'error' | 'cap-reached'
  >('idle');
  const [logs, setLogs] = useState<{ id: number; time: string; level: string; msg: string }[]>([]);
  const [convergedHtml, setConvergedHtml] = useState<string>('');
  const [dorav, setDorav] = useState<DoravScores | null>(null);
  const [nielsen, setNielsen] = useState<NielsenHeuristic[]>([]);
  const [degradationReason, setDegradationReason] = useState<string>('');
  const [capReachedDetail, setCapReachedDetail] = useState<string>('');

  const addLog = (level: string, msg: string) => {
    const time = new Date().toISOString().split('T')[1].slice(0, 8);
    setLogs((prev) => [...prev, { id: Date.now(), time, level, msg }]);
  };

  const handleZoom = (delta: number) => {
    setScale((s) => Math.max(0.2, Math.min(3, s + delta)));
  };

  const startGeneration = () => {
    if (status === 'generating' || status === 'cap-reached' || !user) return;
    setStatus('generating');
    setLogs([]);
    addLog('INFO', 'Initiating Vertex AI Convergence Loop...');

    const brief = new URLSearchParams(window.location.search).get('brief') || 'SaaS landing page';

    const callbacks: StreamCallbacks = {
      onPlan: (data) => {
        addLog('INFO', `Plan received: ${data.surfaces?.join(', ') || 'N/A'}`);
      },
      onScreenStart: (data) => {
        addLog('INFO', `Generating screen: ${data.screen}`);
      },
      onIterationStart: (data) => {
        addLog('INFO', `Iteration #${data.iteration} started`);
      },
      onCandidates: () => {
        addLog('INFO', 'Candidate HTML received');
      },
      onGatesEvaluation: (data) => {
        const level = data.passed ? 'SUCCESS' : 'WARN';
        addLog(level, `Gates: axe=${data.axe_score}, visual=${data.visual_score}`);
      },
      onConsensusEvaluation: (data) => {
        const level = data.passed ? 'SUCCESS' : 'WARN';
        addLog(level, `Consensus: [${data.votes?.join(', ')}]`);
      },
      onFixerDirective: (data) => {
        addLog('WARN', `Fixer: ${data.directive}`);
      },
      onScreenConverged: (data) => {
        addLog('SUCCESS', `Screen converged: ${data.screen}`);
      },
      onComplete: (data) => {
        if (data.best_html) setConvergedHtml(data.best_html);
        if (data.dorav) setDorav(data.dorav);
        if (data.nielsen) setNielsen(data.nielsen);
        if (data.degraded) {
          const reason =
            data.degradation_reason || 'Output quality fell below the convergence threshold.';
          setDegradationReason(reason);
          addLog('WARN', `Generation degraded: ${reason}`);
          setStatus('degraded');
        } else {
          addLog('SUCCESS', 'Generation complete. All screens converged.');
          setStatus('converged');
        }
      },
      onError: (err) => {
        addLog('ERROR', `Pipeline error: ${err}`);
        setStatus('error');
      },
      onCapReached: (data: CapReachedData) => {
        const detail = data.detail || 'Token cap reached. Please wait before running again.';
        setCapReachedDetail(detail);
        addLog('ERROR', `Token cap reached: ${detail}`);
        setStatus('cap-reached');
      },
    };

    runGenerationStream(brief, 50, user.token, callbacks);
  };

  if (!user) return <div ref={initRef} />;

  return (
    <LazyMotion features={domAnimation}>
      <div className="h-screen w-screen bg-[var(--g-bg)] text-[var(--g-text)] overflow-hidden flex flex-col font-sans stitch-grid-bg">
        {/* Top Navbar */}
        <header className="h-14 flex items-center justify-between px-4 border-b border-[var(--g-outline)] bg-[var(--g-surface)]/80 backdrop-blur-md z-40">
          <div className="flex items-center gap-3">
            <button
              onClick={() => router.push('/')}
              className="p-1.5 hover:bg-[var(--g-surface-hover)] rounded-md transition-colors"
              aria-label="Back to dashboard"
            >
              <ArrowLeft size={18} className="text-[var(--g-text-muted)]" />
            </button>
            <div className="flex items-center gap-2">
              <span className="font-semibold text-[13px] text-white tracking-wide">{id}</span>
              <span className="px-1.5 py-0.5 rounded text-[10px] bg-indigo-500/20 text-indigo-300 font-mono border border-indigo-500/30">
                v1.0
              </span>
            </div>
          </div>

          <div className="flex items-center gap-1 bg-black/40 p-1 rounded-md border border-[var(--g-outline)]">
            <button className="px-3 py-1 rounded text-xs font-medium bg-[var(--g-outline)] text-white shadow-sm">
              Home
            </button>
            <button className="px-3 py-1 rounded text-xs font-medium text-gray-400 hover:text-white transition-colors">
              Auth
            </button>
            <button className="px-3 py-1 rounded text-xs font-medium text-gray-400 hover:text-white transition-colors">
              Dashboard
            </button>
          </div>

          <div className="flex items-center gap-3">
            <div className="px-3 py-1.5 text-xs text-gray-400 border border-[var(--g-outline)] rounded-md bg-black/20 flex items-center gap-2">
              Model: <span className="text-white font-medium">Gemini 1.5 Pro</span>
            </div>
            <button
              onClick={startGeneration}
              disabled={status === 'generating' || status === 'cap-reached'}
              className="flex items-center gap-1.5 bg-[var(--g-primary-blue)] hover:bg-[var(--g-primary-blue-hover)] disabled:opacity-50 text-white px-4 py-1.5 rounded-md text-xs font-medium transition-colors shadow-sm"
            >
              {status === 'generating' ? (
                <div className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              ) : (
                <Play size={14} className="ml-0.5 fill-current" />
              )}
              {status === 'generating' ? 'Generating...' : 'Run'}
            </button>
          </div>
        </header>

        <div className="flex-1 flex overflow-hidden relative">
          {/* Left Block Drawer */}
          <aside className="w-56 border-r border-[var(--g-outline)] bg-[var(--g-surface)]/50 backdrop-blur-md flex flex-col z-10">
            <div className="p-3 border-b border-[var(--g-outline)] flex items-center gap-2">
              <Layout size={14} className="text-gray-400" />
              <span className="text-xs font-semibold text-gray-300 uppercase tracking-wider">
                Layers
              </span>
            </div>
            <div className="flex-1 overflow-y-auto p-2 space-y-1">
              {['Hero Section', 'Feature Grid', 'Testimonials', 'Pricing Table', 'Footer'].map(
                (layer, i) => (
                  <div
                    key={i}
                    className="flex items-center gap-2 px-2 py-1.5 rounded-md hover:bg-[var(--g-surface-hover)] text-xs text-gray-400 cursor-pointer group transition-colors"
                  >
                    <Box
                      size={14}
                      className="text-gray-500 group-hover:text-indigo-400 transition-colors"
                    />
                    <span className="truncate">{layer}</span>
                  </div>
                )
              )}
            </div>
          </aside>

          {/* Center Canvas */}
          <main className="flex-1 relative flex items-center justify-center overflow-auto">
            {/* Canvas Toolbar */}
            <div className="absolute top-4 left-1/2 -translate-x-1/2 flex items-center gap-1 bg-[var(--g-surface)]/80 backdrop-blur-md p-1 rounded-lg border border-[var(--g-outline)] shadow-lg z-20">
              <button
                data-testid="device-390"
                aria-label="Mobile 390px"
                className={`p-1.5 rounded transition-colors ${deviceWidth === 390 ? 'bg-indigo-500/30 text-indigo-300' : 'hover:bg-[var(--g-surface-hover)] text-gray-400 hover:text-white'}`}
                onClick={() => setDeviceWidth(390)}
              >
                <Smartphone size={16} />
              </button>
              <button
                data-testid="device-768"
                aria-label="Tablet 768px"
                className={`p-1.5 rounded transition-colors ${deviceWidth === 768 ? 'bg-indigo-500/30 text-indigo-300' : 'hover:bg-[var(--g-surface-hover)] text-gray-400 hover:text-white'}`}
                onClick={() => setDeviceWidth(768)}
              >
                <Tablet size={16} />
              </button>
              <button
                data-testid="device-1280"
                aria-label="Desktop 1280px"
                className={`p-1.5 rounded transition-colors ${deviceWidth === 1280 ? 'bg-indigo-500/30 text-indigo-300' : 'hover:bg-[var(--g-surface-hover)] text-gray-400 hover:text-white'}`}
                onClick={() => setDeviceWidth(1280)}
              >
                <Monitor size={16} />
              </button>
              <div className="w-px h-4 bg-[var(--g-outline)] mx-1" />
              <button
                className="p-1.5 rounded hover:bg-[var(--g-surface-hover)] text-gray-400 hover:text-white transition-colors"
                onClick={() => handleZoom(-0.1)}
                aria-label="Zoom out"
              >
                <ZoomOut size={16} />
              </button>
              <span className="text-xs font-mono w-12 text-center text-gray-300">
                {Math.round(scale * 100)}%
              </span>
              <button
                className="p-1.5 rounded hover:bg-[var(--g-surface-hover)] text-gray-400 hover:text-white transition-colors"
                onClick={() => handleZoom(0.1)}
                aria-label="Zoom in"
              >
                <ZoomIn size={16} />
              </button>
              <div className="w-px h-4 bg-[var(--g-outline)] mx-1" />
              <button
                className="p-1.5 rounded hover:bg-[var(--g-surface-hover)] text-gray-400 hover:text-white transition-colors"
                onClick={() => setScale(1)}
                aria-label="Reset zoom"
              >
                <Maximize size={16} />
              </button>
            </div>

            {/* Draggable/Zoomable Canvas Area */}
            <m.div
              data-testid="studio-canvas"
              drag
              dragMomentum={false}
              animate={{ scale }}
              transition={{ type: 'spring', bounce: 0, duration: 0.4 }}
              style={{ width: deviceWidth }}
              className="shrink-0 h-[768px] bg-white rounded-lg shadow-2xl overflow-hidden border border-gray-200 cursor-grab active:cursor-grabbing origin-center"
            >
              {/* \u2500\u2500 Empty (idle) state \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500 */}
              {status === 'idle' && (
                <div
                  data-testid="state-empty"
                  className="w-full h-full flex flex-col items-center justify-center bg-gray-50 gap-4 px-8"
                >
                  <MousePointer2 size={40} className="text-indigo-300" aria-hidden="true" />
                  <h2 className="text-lg font-semibold text-gray-700 text-center">
                    Ready to generate
                  </h2>
                  <p className="text-sm text-gray-600 text-center max-w-xs">
                    Configure your brief in the URL and click{' '}
                    <strong className="text-gray-800">Run</strong> to start the Vertex AI
                    Convergence Loop.
                  </p>
                </div>
              )}

              {/* \u2500\u2500 Loading (generating) state \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500 */}
              {status === 'generating' && (
                <div
                  data-testid="state-loading"
                  role="status"
                  aria-live="polite"
                  aria-label="Generating design \u2014 please wait"
                  className="w-full h-full flex flex-col items-center justify-center bg-gray-50 gap-4"
                >
                  <Loader2 size={40} className="text-indigo-500 animate-spin" aria-hidden="true" />
                  <h2 className="text-lg font-semibold text-gray-700">Generating\u2026</h2>
                  <p className="text-sm text-gray-600">
                    Vertex AI Convergence Loop is running. This may take a moment.
                  </p>
                </div>
              )}

              {/* \u2500\u2500 Converged state \u2014 render iframe \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500 */}
              {status === 'converged' && convergedHtml && (
                <iframe
                  sandbox="allow-scripts"
                  srcDoc={convergedHtml}
                  title="Converged design output"
                  className="w-full h-full border-0"
                />
              )}

              {/* \u2500\u2500 Degraded state \u2014 show output + degradation banner \u2500\u2500\u2500 */}
              {status === 'degraded' && (
                <div data-testid="state-degraded" className="w-full h-full relative">
                  {/* Still render the best available output behind the banner */}
                  {convergedHtml && (
                    <iframe
                      sandbox="allow-scripts"
                      srcDoc={convergedHtml}
                      title="Degraded design output"
                      className="w-full h-full border-0"
                    />
                  )}
                  {/* Degradation acknowledgment overlay (PRD: agent always acknowledges degradation) */}
                  <div
                    role="status"
                    aria-live="polite"
                    className="absolute top-0 left-0 right-0 flex items-start gap-3 bg-amber-50 border-b-2 border-amber-400 px-4 py-3"
                  >
                    <AlertTriangle
                      size={20}
                      className="text-amber-600 mt-0.5 shrink-0"
                      aria-hidden="true"
                    />
                    <div>
                      <h2 className="text-sm font-semibold text-amber-800">
                        Result is degraded \u2014 showing the best available output
                      </h2>
                      {degradationReason && (
                        <p className="text-xs text-amber-700 mt-0.5">{degradationReason}</p>
                      )}
                    </div>
                  </div>
                </div>
              )}

              {/* \u2500\u2500 Error state \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500 */}
              {status === 'error' && (
                <div
                  data-testid="state-error"
                  role="alert"
                  className="w-full h-full flex flex-col items-center justify-center bg-gray-50 gap-4 px-8"
                >
                  <XCircle size={40} className="text-red-400" aria-hidden="true" />
                  <h2 className="text-lg font-semibold text-red-700">Pipeline error</h2>
                  <p className="text-sm text-gray-500 text-center max-w-xs">
                    The generation pipeline encountered an error. Check the log below for details,
                    then try again.
                  </p>
                  <button
                    onClick={startGeneration}
                    className="mt-2 flex items-center gap-2 bg-red-600 hover:bg-red-700 text-white px-4 py-2 rounded-md text-sm font-medium transition-colors"
                  >
                    <RotateCcw size={14} aria-hidden="true" />
                    Retry generation
                  </button>
                </div>
              )}

              {/* \u2500\u2500 Cap-reached state \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500 */}
              {status === 'cap-reached' && (
                <div
                  data-testid="state-cap-reached"
                  role="alert"
                  className="w-full h-full flex flex-col items-center justify-center bg-gray-50 gap-4 px-8"
                >
                  <ZapOff size={40} className="text-orange-400" aria-hidden="true" />
                  <h2 className="text-lg font-semibold text-orange-700">Token cap reached</h2>
                  <p className="text-sm text-gray-600 text-center max-w-xs">
                    {capReachedDetail ||
                      "You've reached your token cap for this session. Please wait before running another generation."}
                  </p>
                  <p className="text-xs text-gray-600 text-center max-w-xs">
                    Token limits reset periodically. Contact your administrator if you need a higher
                    limit.
                  </p>
                </div>
              )}
            </m.div>
          </main>

          {/* Right Vertex AI Config Panel */}
          <aside className="w-72 border-l border-[var(--g-outline)] bg-[var(--g-surface)]/50 backdrop-blur-md flex flex-col z-10">
            <div className="p-4 border-b border-[var(--g-outline)] flex items-center gap-2">
              <SlidersHorizontal size={16} className="text-indigo-400" />
              <span className="text-sm font-semibold text-white">Vertex AI Settings</span>
            </div>

            <div className="p-5 space-y-6 flex-1 overflow-y-auto">
              <div className="space-y-4">
                <div>
                  <div className="flex justify-between text-xs mb-1.5">
                    <span className="text-gray-400">Temperature</span>
                    <span className="text-white font-mono">{temperature.toFixed(2)}</span>
                  </div>
                  <input
                    type="range"
                    min="0"
                    max="1"
                    step="0.05"
                    value={temperature}
                    onChange={(e) => setTemperature(parseFloat(e.target.value))}
                    className="w-full accent-indigo-500"
                    aria-label="Temperature"
                  />
                </div>
                <div>
                  <div className="flex justify-between text-xs mb-1.5">
                    <span className="text-gray-400">Top-K</span>
                    <span className="text-white font-mono">{topK}</span>
                  </div>
                  <input
                    type="range"
                    min="1"
                    max="40"
                    value={topK}
                    onChange={(e) => setTopK(parseInt(e.target.value))}
                    className="w-full accent-indigo-500"
                    aria-label="Top-K"
                  />
                </div>
                <div>
                  <div className="flex justify-between text-xs mb-1.5">
                    <span className="text-gray-400">Max Tokens</span>
                    <span className="text-white font-mono">{maxTokens}</span>
                  </div>
                  <input
                    type="range"
                    min="1024"
                    max="8192"
                    step="512"
                    value={maxTokens}
                    onChange={(e) => setMaxTokens(parseInt(e.target.value))}
                    className="w-full accent-indigo-500"
                    aria-label="Max Tokens"
                  />
                </div>
              </div>

              <div className="h-px bg-[var(--g-outline)] my-6"></div>

              <div>
                <h4 className="text-[11px] uppercase tracking-wider font-semibold text-gray-500 mb-3">
                  D-O-R-A-V Scorecard
                </h4>
                {/* Composite headline */}
                <div className="bg-black/40 p-3 rounded border border-indigo-500/30 flex justify-between items-center mb-3">
                  <span className="text-xs text-gray-300 font-semibold">Composite</span>
                  <span
                    className={`text-sm font-mono font-bold ${dorav?.composite != null ? 'text-indigo-300' : 'text-gray-600'}`}
                  >
                    {dorav?.composite != null ? Math.round(dorav.composite * 100) : '--'}
                  </span>
                </div>
                <div className="space-y-2">
                  {(
                    [
                      { key: 'brand' as const, label: 'Brand' },
                      { key: 'originality' as const, label: 'Originality' },
                      { key: 'relevance' as const, label: 'Relevance' },
                      { key: 'accessibility' as const, label: 'Accessibility' },
                      { key: 'visual-clarity' as const, label: 'Visual Clarity' },
                    ] as const
                  ).map(({ key, label }) => {
                    const val = dorav?.[key];
                    return (
                      <div
                        key={key}
                        className="bg-black/30 px-3 py-2 rounded border border-[var(--g-outline)] flex justify-between items-center"
                      >
                        <span className="text-xs text-gray-400">{label}</span>
                        <span
                          className={`text-xs font-mono font-bold ${val != null ? 'text-emerald-400' : 'text-gray-600'}`}
                        >
                          {val != null ? Math.round(val * 100) : '—'}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Nielsen Heuristics */}
              {(status === 'converged' || nielsen.length > 0) && (
                <div>
                  <div className="h-px bg-[var(--g-outline)] my-4" />
                  <h4 className="text-[11px] uppercase tracking-wider font-semibold text-gray-500 mb-3">
                    Nielsen Heuristics
                  </h4>
                  {nielsen.length === 0 ? (
                    <p className="text-xs text-gray-600 italic">No heuristic data</p>
                  ) : (
                    <div className="space-y-1.5">
                      {nielsen.map((item) => (
                        <div
                          key={item.heuristic}
                          className="flex items-center gap-2 px-2 py-1.5 rounded bg-black/20 border border-[var(--g-outline)]"
                        >
                          <span
                            className={`shrink-0 w-2 h-2 rounded-full ${item.present ? 'bg-emerald-400' : 'bg-gray-600'}`}
                            aria-label={item.present ? 'present' : 'absent'}
                          />
                          <span className="text-[10px] text-gray-400 flex-1 truncate capitalize">
                            {item.heuristic.replace(/_/g, ' ')}
                          </span>
                          <span className="text-[10px] font-mono text-gray-500 shrink-0">
                            {item.votes}/3
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          </aside>

          {/* Bottom Drawer: Cloud Log Explorer */}
          <AnimatePresence>
            {isDrawerOpen && (
              <m.div
                initial={{ y: '100%' }}
                animate={{ y: 0 }}
                exit={{ y: '100%' }}
                transition={{ type: 'spring', bounce: 0, duration: 0.4 }}
                className="absolute bottom-0 left-56 right-72 h-64 bg-[#1e1f22] border-t border-[var(--g-outline)] shadow-2xl flex flex-col z-30"
              >
                <div className="h-10 bg-[#2d2f31] flex items-center justify-between px-4 border-b border-[var(--g-outline)]">
                  <div className="flex items-center gap-2 text-xs text-gray-300 font-medium">
                    <Terminal size={14} className="text-blue-400" />
                    Cloud Log Explorer
                  </div>
                  <button
                    onClick={() => setIsDrawerOpen(false)}
                    className="p-1 hover:bg-black/20 rounded text-gray-400 hover:text-white transition-colors"
                    aria-label="Close log drawer"
                  >
                    <ChevronDown size={16} />
                  </button>
                </div>
                <div className="flex-1 p-4 overflow-y-auto font-mono text-[11px] space-y-1.5 bg-[#0f1013]">
                  {logs.length === 0 ? (
                    <p className="text-gray-600 italic">
                      No logs available. Start a generation run.
                    </p>
                  ) : (
                    logs.map((log) => (
                      <div key={log.id} className="flex gap-3">
                        <span className="text-gray-500 shrink-0">{log.time}</span>
                        <span
                          className={`shrink-0 w-12 ${log.level === 'SUCCESS' ? 'text-emerald-400' : log.level === 'ERROR' ? 'text-red-400' : log.level === 'WARN' ? 'text-amber-400' : 'text-blue-400'}`}
                        >
                          {log.level}
                        </span>
                        <span className="text-gray-300">{log.msg}</span>
                      </div>
                    ))
                  )}
                </div>
              </m.div>
            )}
          </AnimatePresence>

          {/* Drawer Toggle Handle */}
          <div className="absolute bottom-4 left-1/2 -translate-x-1/2 z-20">
            {!isDrawerOpen && (
              <button
                onClick={() => setIsDrawerOpen(true)}
                className="bg-[var(--g-surface)] border border-[var(--g-outline)] shadow-lg rounded-full px-4 py-1.5 flex items-center gap-2 text-xs font-medium text-gray-400 hover:text-white transition-colors"
              >
                <Terminal size={14} /> View Logs <ChevronUp size={14} className="ml-1" />
              </button>
            )}
          </div>
        </div>
      </div>
    </LazyMotion>
  );
}
