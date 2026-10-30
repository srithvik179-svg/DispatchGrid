import React, { useEffect, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { NAV_ITEMS } from './navConfig';
import { Menu, Clock, Server, CheckCircle2, AlertCircle } from 'lucide-react';

interface HeaderProps {
  onOpenMobile: () => void;
}

export const Header: React.FC<HeaderProps> = ({ onOpenMobile }) => {
  const location = useLocation();
  const [online, setOnline] = useState<boolean | null>(null);

  const currentNav =
    NAV_ITEMS.find((item) =>
      item.path === '/'
        ? location.pathname === '/'
        : location.pathname.startsWith(item.path)
    ) || { name: 'DispatchGrid', description: '' };

  useEffect(() => {
    const checkHealth = async () => {
      try {
        const apiUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
        const res = await fetch(`${apiUrl}/health`);
        setOnline(res.ok);
      } catch {
        setOnline(false);
      }
    };
    checkHealth();
    const interval = setInterval(checkHealth, 20000);
    return () => clearInterval(interval);
  }, []);

  return (
    <header className="h-16 bg-slate-900/80 backdrop-blur-md border-b border-slate-800 sticky top-0 z-30 px-4 sm:px-6 lg:px-8 flex items-center justify-between">
      {/* Left: Mobile trigger & Current Section */}
      <div className="flex items-center space-x-3">
        <button
          onClick={onOpenMobile}
          className="lg:hidden p-2 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition"
          aria-label="Open sidebar"
        >
          <Menu className="w-5 h-5" />
        </button>

        <div>
          <div className="text-sm font-semibold text-white tracking-tight flex items-center space-x-2">
            <span>{currentNav.name}</span>
          </div>
        </div>
      </div>

      {/* Right: Simulation Clock & Health Badge */}
      <div className="flex items-center space-x-3">
        {/* Simulation Clock Indicator */}
        <div className="hidden sm:flex items-center space-x-2 px-3 py-1.5 rounded-lg bg-slate-800/80 border border-slate-700/80 text-xs">
          <Clock className="w-3.5 h-3.5 text-indigo-400" />
          <span className="text-slate-400">Clock:</span>
          <span className="text-slate-200 font-mono font-medium">
            2026-11-02 10:00 IST
          </span>
        </div>

        {/* Backend Connectivity Status */}
        <div className="flex items-center space-x-2 px-3 py-1.5 rounded-lg bg-slate-800/80 border border-slate-700/80 text-xs">
          <Server className="w-3.5 h-3.5 text-slate-400" />
          <span className="hidden md:inline text-slate-400">Backend:</span>
          {online === null ? (
            <span className="text-amber-400 font-medium">Checking</span>
          ) : online ? (
            <span className="text-emerald-400 font-medium flex items-center">
              <CheckCircle2 className="w-3.5 h-3.5 mr-1" /> Healthy
            </span>
          ) : (
            <span className="text-rose-400 font-medium flex items-center">
              <AlertCircle className="w-3.5 h-3.5 mr-1" /> Offline
            </span>
          )}
        </div>
      </div>
    </header>
  );
};
