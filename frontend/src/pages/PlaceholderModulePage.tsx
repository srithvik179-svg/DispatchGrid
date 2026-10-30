import React from 'react';
import { PageHeader } from '../components/common/PageHeader';
import { LucideIcon, Layers, ShieldCheck, Clock } from 'lucide-react';

interface PlaceholderModulePageProps {
  title: string;
  description: string;
  icon: LucideIcon;
  badge?: string;
  moduleKey: string;
  features: string[];
  constraints?: string[];
}

export const PlaceholderModulePage: React.FC<PlaceholderModulePageProps> = ({
  title,
  description,
  icon: Icon,
  badge = 'Planned Module',
  features,
  constraints,
}) => {
  return (
    <div className="space-y-6">
      <PageHeader
        title={title}
        description={description}
        badge={badge}
      />

      {/* Module Overview Card */}
      <div className="p-8 rounded-2xl bg-slate-900/60 border border-slate-800 text-left">
        <div className="flex items-start space-x-4">
          <div className="w-12 h-12 rounded-xl bg-indigo-950 border border-indigo-800/80 flex items-center justify-center text-indigo-400 shrink-0">
            <Icon className="w-6 h-6" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-white">{title} Engine Interface</h2>
            <p className="text-sm text-slate-400 mt-1 max-w-2xl">{description}</p>
          </div>
        </div>

        <div className="mt-8 grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="p-5 rounded-xl bg-slate-950/60 border border-slate-800">
            <div className="flex items-center space-x-2 text-xs font-semibold uppercase tracking-wider text-indigo-400 mb-3">
              <Layers className="w-4 h-4" />
              <span>Core Functional Scope</span>
            </div>
            <ul className="space-y-2 text-xs text-slate-300">
              {features.map((feat, idx) => (
                <li key={idx} className="flex items-start">
                  <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 mt-1.5 mr-2 shrink-0" />
                  <span>{feat}</span>
                </li>
              ))}
            </ul>
          </div>

          {constraints && (
            <div className="p-5 rounded-xl bg-slate-950/60 border border-slate-800">
              <div className="flex items-center space-x-2 text-xs font-semibold uppercase tracking-wider text-emerald-400 mb-3">
                <ShieldCheck className="w-4 h-4" />
                <span>Deterministic Rules & Constraints</span>
              </div>
              <ul className="space-y-2 text-xs text-slate-300">
                {constraints.map((c, idx) => (
                  <li key={idx} className="flex items-start">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 mt-1.5 mr-2 shrink-0" />
                    <span>{c}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>

        <div className="mt-6 pt-4 border-t border-slate-800/80 flex items-center justify-between text-xs text-slate-500">
          <div className="flex items-center space-x-2">
            <Clock className="w-3.5 h-3.5" />
            <span>Simulation Reference: 2026-11-02 10:00 IST</span>
          </div>
          <span className="font-mono text-slate-400">Ready for domain implementation</span>
        </div>
      </div>
    </div>
  );
};
