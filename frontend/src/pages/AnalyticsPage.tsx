import React from 'react';
import { PlaceholderModulePage } from './PlaceholderModulePage';
import { BarChart3 } from 'lucide-react';

export const AnalyticsPage: React.FC = () => {
  return (
    <PlaceholderModulePage
      title="Analytics Dashboard"
      description="Workforce utilization, SLA compliance, zone load balance, and travel analytics."
      icon={BarChart3}
      badge="Module F"
      moduleKey="analytics"
      features={[
        'Fleet utilization and technician workload distribution',
        'SLA risk assessment and deadline compliance breakdown',
        'Zone coverage and unassigned jobs categorical analysis',
        'Re-optimisation impact and disruption recovery comparisons',
      ]}
      constraints={[
        'All statistics derived strictly from authoritative operational records (zero fabricated metrics)',
      ]}
    />
  );
};
