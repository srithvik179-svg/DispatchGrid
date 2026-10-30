import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AppLayout } from './components/layout/AppLayout';
import { OverviewPage } from './pages/OverviewPage';
import { JobsPage } from './pages/JobsPage';
import { TechniciansPage } from './pages/TechniciansPage';
import { SchedulePage } from './pages/SchedulePage';
import { OptimisationPage } from './pages/OptimisationPage';
import { DisruptionsPage } from './pages/DisruptionsPage';
import { AuditHistoryPage } from './pages/AuditHistoryPage';
import { AnalyticsPage } from './pages/AnalyticsPage';
import { SettingsPage } from './pages/SettingsPage';

export const App: React.FC = () => {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<AppLayout />}>
          <Route index element={<OverviewPage />} />
          <Route path="overview" element={<Navigate to="/" replace />} />
          <Route path="jobs" element={<JobsPage />} />
          <Route path="technicians" element={<TechniciansPage />} />
          <Route path="schedule" element={<SchedulePage />} />
          <Route path="optimisation" element={<OptimisationPage />} />
          <Route path="disruptions" element={<DisruptionsPage />} />
          <Route path="audit-history" element={<AuditHistoryPage />} />
          <Route path="analytics" element={<AnalyticsPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
};

export default App;
