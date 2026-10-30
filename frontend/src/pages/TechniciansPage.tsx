import React from 'react';
import { PlaceholderModulePage } from './PlaceholderModulePage';
import { Users } from 'lucide-react';

export const TechniciansPage: React.FC = () => {
  return (
    <PlaceholderModulePage
      title="Technicians Fleet"
      description="Field workforce registry, skill sets, equipment kits, shifts, and unavailable periods."
      icon={Users}
      badge="Module A"
      moduleKey="technicians"
      features={[
        'Technician profiles with 8 certified skills and specialised equipment kits',
        'Eligible geographical service zones per technician',
        'Multi-day shift boundaries and working hours definition',
        'Home location geo-coordinates for daily initial transit calculation',
      ]}
      constraints={[
        'Hard zone eligibility: Technician can only perform jobs within designated zones',
        'Hard unavailable periods: Precludes assignment during pre-scheduled leaves or breaks',
        'Strict shift boundaries: Overtime permitted only if technician policy authorizes',
      ]}
    />
  );
};
