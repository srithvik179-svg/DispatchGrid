import React from 'react';
import { PlaceholderModulePage } from './PlaceholderModulePage';
import { AlertTriangle } from 'lucide-react';

export const DisruptionsPage: React.FC = () => {
  return (
    <PlaceholderModulePage
      title="Disruptions & Recovery"
      description="Live operational recovery when technicians become unavailable or urgent jobs arrive."
      icon={AlertTriangle}
      badge="Module D"
      moduleKey="disruptions"
      features={[
        '12 validated test scenarios (9 disruption and 3 reliability edge cases)',
        'Technician absence management with automated re-assignment',
        'Urgent priority job injection with minimal ripple effect',
        'Early/delayed completion feedback and dynamic schedule adjustment',
      ]}
      constraints={[
        'Immutable protection of completed jobs and active in-progress tasks',
        'Audited delta view showing what changed, what remained unchanged, and why',
      ]}
    />
  );
};
