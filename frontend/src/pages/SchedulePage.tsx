import React from 'react';
import { PlaceholderModulePage } from './PlaceholderModulePage';
import { Calendar } from 'lucide-react';

export const SchedulePage: React.FC = () => {
  return (
    <PlaceholderModulePage
      title="Workforce Schedule"
      description="Visual assignment timeline, technician routes, and dispatch board."
      icon={Calendar}
      badge="Module B"
      moduleKey="schedule"
      features={[
        'Interactive dispatch timeline organized by technician and operational hours',
        'Visual indicators for transit times, service durations, and job status',
        'Preservation of 7 existing completed and in-progress assignments',
        'Feasibility diagnostics distinguishing feasible, infeasible, and unassignable jobs',
      ]}
      constraints={[
        'Zero technician assignment overlap guarantee',
        'Haversine transit time factored between consecutive locations at 30 km/h',
        'Technician initial trip originates from home location',
      ]}
    />
  );
};
