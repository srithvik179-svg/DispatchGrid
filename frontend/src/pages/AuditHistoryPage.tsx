import React from 'react';
import { PlaceholderModulePage } from './PlaceholderModulePage';
import { History } from 'lucide-react';

export const AuditHistoryPage: React.FC = () => {
  return (
    <PlaceholderModulePage
      title="Audit History & Explainability"
      description="Traceable run records, granular unassigned diagnostic reasons, and schedule revisions."
      icon={History}
      badge="Module E"
      moduleKey="audit-history"
      features={[
        'Full execution history with Run IDs, timestamps, and objective scores',
        'Transparent decision logs for all jobs considered and assigned',
        'Actionable diagnostic explanations for unassigned jobs (e.g., missing skills, no eligible technician in zone, time window infeasible)',
        'Schedule change comparison against prior baseline runs',
      ]}
      constraints={[
        'No generic "No technician available" messages when root cause constraint is identifiable',
        'Complete chronological audit trail',
      ]}
    />
  );
};
