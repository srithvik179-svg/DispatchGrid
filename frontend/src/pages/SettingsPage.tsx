import React from 'react';
import { PlaceholderModulePage } from './PlaceholderModulePage';
import { Settings as SettingsIcon } from 'lucide-react';

export const SettingsPage: React.FC = () => {
  return (
    <PlaceholderModulePage
      title="System Settings"
      description="Simulation clock parameters, hard/soft constraint conventions, and environment variables."
      icon={SettingsIcon}
      badge="System"
      moduleKey="settings"
      features={[
        'Simulation Reference Clock: 2026-11-02T10:00:00+05:30',
        'Planning Horizon Boundaries: 2026-11-02 00:00 to 2026-11-04 00:00 IST',
        'Transit Speed Model: 30 km/h Haversine geodesic distance',
        'Backend API endpoint configuration and connectivity monitoring',
      ]}
      constraints={[
        'Hard constraints: Skills, equipment, zone eligibility, shift boundaries, unavailable periods, time windows, and overlaps',
        'Soft objectives: SLA lateness, transit minutes, unassigned urgent jobs, and overtime penalties',
      ]}
    />
  );
};
