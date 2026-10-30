import React, { useEffect, useState } from 'react';
import { PageHeader } from '../components/common/PageHeader';
import { NAV_ITEMS } from '../components/layout/navConfig';
import { Link } from 'react-router-dom';
import { CheckCircle2, AlertCircle, ArrowUpRight, Clock, MapPin, Shield } from 'lucide-react';

interface HealthData {
  status: string;
  service: string;
  version: string;
  environment: string;
  simulation_clock: string;
}

export const OverviewPage: React.FC = () => {
  const [health, setHealth] = useState<HealthData | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchHealth = async () => {
      try {
        setLoading(true);
        const apiUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
        const res = await fetch(`${apiUrl}/health`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        setHealth(data);
        setError(null);
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : 'Backend offline');
      } finally {
        setLoading(false);
      }
    };
    fetchHealth();
  }, []);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Overview"
        description="DispatchGrid Intelligent Workforce Scheduling & Recovery Engine"
        badge="Phase 02 Shell"
      />

      {/* System Status Banner */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="p-4 rounded-xl bg-slate-900 border border-slate-800 flex items-start space-x-3">
          <div className="p-2 rounded-lg bg-indigo-950 text-indigo-400 border border-indigo-800/60 mt-0.5">
            <Clock className="w-4 h-4" />
          </div>
          <div>
            <div className="text-xs text-slate-400 font-medium">Simulation Clock</div>
            <div className="text-sm font-semibold text-white mt-0.5">
              {health?.simulation_clock || '2026-11-02T10:00:00+05:30'}
            </div>
            <div className="text-xs text-slate-500 mt-1">Planning Horizon: 2–3 Nov 2026</div>
          </div>
        </div>

        <div className="p-4 rounded-xl bg-slate-900 border border-slate-800 flex items-start space-x-3">
          <div className="p-2 rounded-lg bg-emerald-950 text-emerald-400 border border-emerald-800/60 mt-0.5">
            <MapPin className="w-4 h-4" />
          </div>
          <div>
            <div className="text-xs text-slate-400 font-medium">Transit & Geography</div>
            <div className="text-sm font-semibold text-white mt-0.5">Haversine @ 30 km/h</div>
            <div className="text-xs text-slate-500 mt-1">6 Service Zones (Z1–Z6)</div>
          </div>
        </div>

        <div className="p-4 rounded-xl bg-slate-900 border border-slate-800 flex items-start space-x-3">
          <div className="p-2 rounded-lg bg-blue-950 text-blue-400 border border-blue-800/60 mt-0.5">
            <Shield className="w-4 h-4" />
          </div>
          <div>
            <div className="text-xs text-slate-400 font-medium">API Service Status</div>
            <div className="flex items-center space-x-2 mt-0.5">
              {loading ? (
                <span className="text-xs text-amber-400 font-medium">Connecting...</span>
              ) : error ? (
                <span className="text-xs text-rose-400 font-medium flex items-center">
                  <AlertCircle className="w-3.5 h-3.5 mr-1" /> Disconnected
                </span>
              ) : (
                <span className="text-xs text-emerald-400 font-medium flex items-center">
                  <CheckCircle2 className="w-3.5 h-3.5 mr-1" /> Online ({health?.version})
                </span>
              )}
            </div>
            <div className="text-xs text-slate-500 mt-1">{health?.service || 'FastAPI Service'}</div>
          </div>
        </div>
      </div>

      {/* Navigation Directory Grid */}
      <div className="pt-2">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-400 mb-4">
          Platform Capabilities & Navigation
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {NAV_ITEMS.filter((item) => item.path !== '/').map((item) => {
            const Icon = item.icon;
            return (
              <Link
                key={item.path}
                to={item.path}
                className="p-5 rounded-xl bg-slate-900/60 border border-slate-800 hover:border-indigo-600/60 hover:bg-slate-900 transition flex flex-col justify-between group"
              >
                <div>
                  <div className="w-9 h-9 rounded-lg bg-slate-800 border border-slate-700 flex items-center justify-center text-slate-300 group-hover:bg-indigo-600 group-hover:text-white transition">
                    <Icon className="w-4 h-4" />
                  </div>
                  <h3 className="text-base font-semibold text-white mt-4 group-hover:text-indigo-300 transition">
                    {item.name}
                  </h3>
                  <p className="text-xs text-slate-400 mt-1 leading-relaxed">
                    {item.description}
                  </p>
                </div>
                <div className="flex items-center text-xs text-indigo-400 font-medium mt-4 pt-3 border-t border-slate-800/80 group-hover:text-indigo-300">
                  <span>Open module</span>
                  <ArrowUpRight className="w-3.5 h-3.5 ml-1 transition group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
                </div>
              </Link>
            );
          })}
        </div>
      </div>
    </div>
  );
};
