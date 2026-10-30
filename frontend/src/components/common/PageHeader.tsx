import React from 'react';

interface PageHeaderProps {
  title: string;
  description: string;
  badge?: string;
  action?: React.ReactNode;
}

export const PageHeader: React.FC<PageHeaderProps> = ({
  title,
  description,
  badge,
  action,
}) => {
  return (
    <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between pb-6 mb-6 border-b border-slate-800 gap-4">
      <div>
        <div className="flex items-center space-x-3">
          <h1 className="text-2xl font-bold tracking-tight text-white">{title}</h1>
          {badge && (
            <span className="text-xs px-2.5 py-0.5 rounded-full font-medium bg-indigo-950 text-indigo-400 border border-indigo-800/80">
              {badge}
            </span>
          )}
        </div>
        <p className="text-sm text-slate-400 mt-1">{description}</p>
      </div>
      {action && <div className="flex items-center space-x-3">{action}</div>}
    </div>
  );
};
