import React from 'react';
import { PlaceholderModulePage } from './PlaceholderModulePage';
import { Briefcase } from 'lucide-react';

export const JobsPage: React.FC = () => {
  return (
    <PlaceholderModulePage
      title="Jobs Management"
      description="Service job catalog, time window definitions, required skills, and SLA deadlines."
      icon={Briefcase}
      badge="Module A"
      moduleKey="jobs"
      features={[
        'Job creation, status updates, and lifecycle tracking (pending, assigned, in_progress, completed, cancelled, unassigned)',
        'Priority definitions: 1 (urgent), 2 (high), 3 (medium), 4 (low)',
        'Multi-skill and equipment prerequisites validation',
        'Customer details, geo-location, and zone mapping (Z1–Z6)',
      ]}
      constraints={[
        'Hard time windows: Job service must begin >= window_start and finish <= window_end',
        'Soft SLA deadlines: Penalized in the objective if completed past deadline',
        'Invalid state transition rejection (e.g. cancelled -> completed prohibited)',
      ]}
    />
  );
};
