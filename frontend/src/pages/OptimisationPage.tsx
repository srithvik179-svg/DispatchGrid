import React from 'react';
import { PlaceholderModulePage } from './PlaceholderModulePage';
import { Zap } from 'lucide-react';

export const OptimisationPage: React.FC = () => {
  return (
    <PlaceholderModulePage
      title="Optimisation Engine"
      description="Deterministic scoring and heuristic solver for global workforce assignment."
      icon={Zap}
      badge="Module C"
      moduleKey="optimisation"
      features={[
        'Deterministic multi-objective penalty minimization',
        'SLA breach minimization and urgent job prioritization',
        'Route compaction to minimize total transit hours',
        'Assignment stability scoring to prevent unnecessary reallocations',
      ]}
      constraints={[
        'Strict hard constraint satisfaction prerequisite',
        'Explainable scoring weights and reproducible deterministic outcomes',
        'Idempotent execution with run tracking',
      ]}
    />
  );
};
