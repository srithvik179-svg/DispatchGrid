import React, { useEffect, useState } from 'react';
import { Activity, ShieldCheck, Cpu, ArrowRight, Layers, CheckCircle2, AlertCircle } from 'lucide-react';

interface HealthData {
  status: string;
  service: string;
  version: string;
  environment: string;
  simulation_clock: string;
  timestamp: string;
}

export const App: React.FC = () => {
  const [health, setHealth] = useState<HealthData | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchHealth = async () => {
      try {
        setLoading(true);
        // Supports Vite proxy or direct localhost
        const apiUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
        const res = await fetch(`${apiUrl}/health`);
        if (!res.ok) {
          throw new Error(`HTTP error ${res.status}`);
        }
        const data = await res.json();
        setHealth(data);
        setError(null);
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : 'Failed to connect to backend');
      } finally {
        setLoading(false);
      }
    };

    fetchHealth();
    const interval = setInterval(fetchHealth, 15000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans selection:bg-indigo-500 selection:text-white">
      {/* Top Navigation */}
      <header className="border-b border-slate-800 bg-slate-900/60 backdrop-blur-md sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="w-9 h-9 rounded-lg bg-indigo-600 flex items-center justify-center text-white font-bold shadow-lg shadow-indigo-600/30">
              <Cpu className="w-5 h-5" />
            </div>
            <div>
              <span className="text-xl font-bold tracking-tight text-white">DispatchGrid</span>
              <span className="hidden sm:inline-block ml-2 text-xs px-2 py-0.5 rounded-full bg-indigo-900/60 text-indigo-300 border border-indigo-700/50">
                v0.1.0
              </span>
            </div>
          </div>

          <div className="flex items-center space-x-4">
            <div className="flex items-center space-x-2 text-xs px-3 py-1.5 rounded-full bg-slate-800/80 border border-slate-700">
              <span className="relative flex h-2 w-2">
                {loading ? (
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75"></span>
                ) : error ? (
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-rose-500"></span>
                ) : (
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-400"></span>
                )}
              </span>
              <span className="text-slate-300 font-medium">
                Backend: {loading ? 'Checking...' : error ? 'Offline' : 'Healthy'}
              </span>
            </div>
          </div>
        </div>
      </header>

      {/* Hero Section */}
      <main className="flex-1 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16 flex flex-col justify-center">
        <div className="text-center max-w-3xl mx-auto mb-16">
          <div className="inline-flex items-center space-x-2 px-3 py-1 rounded-full bg-indigo-950/80 border border-indigo-800 text-indigo-300 text-xs font-semibold uppercase tracking-wider mb-6">
            <Activity className="w-3.5 h-3.5" />
            <span>Next-Gen Field Operations Engine</span>
          </div>

          <h1 className="text-4xl sm:text-6xl font-extrabold tracking-tight text-white mb-6 leading-tight">
            DispatchGrid
          </h1>

          <p className="text-lg sm:text-xl text-slate-300 leading-relaxed font-normal mb-8">
            Intelligent Workforce Scheduling &amp; Recovery Engine. Engineered for deterministic assignment,
            strict constraint validation, and automated disruption recovery.
          </p>

          {/* System Health Status Card */}
          <div className="p-6 rounded-2xl bg-slate-900/90 border border-slate-800 text-left shadow-2xl backdrop-blur">
            <div className="flex items-center justify-between pb-4 mb-4 border-b border-slate-800">
              <div className="flex items-center space-x-3">
                {error ? (
                  <AlertCircle className="w-5 h-5 text-rose-400" />
                ) : (
                  <CheckCircle2 className="w-5 h-5 text-emerald-400" />
                )}
                <div>
                  <h3 className="text-sm font-semibold text-white">Application Health Status</h3>
                  <p className="text-xs text-slate-400">GET /health verification endpoint</p>
                </div>
              </div>
              <span
                className={`text-xs px-2.5 py-1 rounded font-mono uppercase tracking-wider font-semibold ${
                  error
                    ? 'bg-rose-950/70 text-rose-400 border border-rose-800'
                    : 'bg-emerald-950/70 text-emerald-300 border border-emerald-800'
                }`}
              >
                {loading ? 'CHECKING' : error ? 'DISCONNECTED' : 'SYSTEM ONLINE'}
              </span>
            </div>

            {error ? (
              <div className="text-xs text-rose-300 bg-rose-950/40 p-3 rounded-lg border border-rose-900/50">
                Backend connection failed: {error}. Ensure FastAPI is running on port 8000.
              </div>
            ) : health ? (
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-xs">
                <div className="bg-slate-950/60 p-3 rounded-lg border border-slate-800/80">
                  <span className="text-slate-500 block mb-1">Service</span>
                  <span className="text-slate-200 font-medium font-mono">{health.service}</span>
                </div>
                <div className="bg-slate-950/60 p-3 rounded-lg border border-slate-800/80">
                  <span className="text-slate-500 block mb-1">Status</span>
                  <span className="text-emerald-400 font-medium font-mono capitalize">{health.status}</span>
                </div>
                <div className="bg-slate-950/60 p-3 rounded-lg border border-slate-800/80">
                  <span className="text-slate-500 block mb-1">Simulation Clock</span>
                  <span className="text-slate-200 font-medium font-mono">{health.simulation_clock}</span>
                </div>
                <div className="bg-slate-950/60 p-3 rounded-lg border border-slate-800/80">
                  <span className="text-slate-500 block mb-1">Environment</span>
                  <span className="text-indigo-400 font-medium font-mono uppercase">{health.environment}</span>
                </div>
              </div>
            ) : null}
          </div>
        </div>

        {/* Architectural Pillars Preview */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 max-w-5xl mx-auto w-full">
          <div className="p-6 rounded-xl bg-slate-900/40 border border-slate-800/80 hover:border-slate-700 transition">
            <div className="w-10 h-10 rounded-lg bg-indigo-950/80 border border-indigo-800/60 flex items-center justify-center text-indigo-400 mb-4">
              <Layers className="w-5 h-5" />
            </div>
            <h3 className="text-base font-semibold text-white mb-2">Deterministic Scheduling</h3>
            <p className="text-xs text-slate-400 leading-relaxed">
              Enforces hard operational constraints: multi-skill matching, equipment, shifts, unavailable periods, and Haversine transit time.
            </p>
          </div>

          <div className="p-6 rounded-xl bg-slate-900/40 border border-slate-800/80 hover:border-slate-700 transition">
            <div className="w-10 h-10 rounded-lg bg-emerald-950/80 border border-emerald-800/60 flex items-center justify-center text-emerald-400 mb-4">
              <ShieldCheck className="w-5 h-5" />
            </div>
            <h3 className="text-base font-semibold text-white mb-2">Dynamic Disruption Recovery</h3>
            <p className="text-xs text-slate-400 leading-relaxed">
              Recovers gracefully from technician absences, urgent priority injections, and duration overruns while protecting in-progress work.
            </p>
          </div>

          <div className="p-6 rounded-xl bg-slate-900/40 border border-slate-800/80 hover:border-slate-700 transition">
            <div className="w-10 h-10 rounded-lg bg-blue-950/80 border border-blue-800/60 flex items-center justify-center text-blue-400 mb-4">
              <ArrowRight className="w-5 h-5" />
            </div>
            <h3 className="text-base font-semibold text-white mb-2">Transparent Audit &amp; Trace</h3>
            <p className="text-xs text-slate-400 leading-relaxed">
              Provides granular diagnostic reasons for every scheduling assignment and unassigned job decision with complete execution logs.
            </p>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-800/80 py-6 text-center text-xs text-slate-500 bg-slate-950">
        DispatchGrid Engine &copy; 2026 &bull; Phase 01: Project Initialisation
      </footer>
    </div>
  );
};

export default App;
