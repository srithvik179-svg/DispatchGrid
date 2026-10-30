import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { OverviewPage } from './OverviewPage';

const mockOverviewData = {
  total_jobs: 108,
  job_counts_by_status: {
    pending: 100,
    completed: 4,
    in_progress: 3,
    cancelled: 1,
  },
  job_counts_by_priority: {
    urgent: 12,
    high: 28,
    medium: 45,
    low: 23,
  },
  total_technicians: 20,
  total_assignments: 7,
  total_zones: 6,
  simulation_clock: '2026-11-02T10:00:00+05:30',
  jobs: [
    {
      id: 'JOB-001',
      title: 'Firewall setup',
      customer_name: 'Pioneer Apartments',
      zone_id: 'Z3',
      priority: 3,
      priority_label: 'medium',
      duration_minutes: 45,
      status: 'pending',
      required_skills: ['networking'],
      time_window_start: '2026-11-02T13:45:00+05:30',
      time_window_end: '2026-11-02T18:15:00+05:30',
      sla_deadline: '2026-11-02T18:15:00+05:30',
      assigned_technician_id: null,
    },
    {
      id: 'JOB-101',
      title: 'Water filter maintenance',
      customer_name: 'Apex Residency',
      zone_id: 'Z2',
      priority: 2,
      priority_label: 'high',
      duration_minutes: 75,
      status: 'completed',
      required_skills: ['plumbing'],
      time_window_start: '2026-11-02T08:00:00+05:30',
      time_window_end: '2026-11-02T10:00:00+05:30',
      sla_deadline: '2026-11-02T10:00:00+05:30',
      assigned_technician_id: 'T03',
    },
  ],
  technicians: [
    {
      id: 'T01',
      name: 'Arjun Rao',
      home_zone_id: 'Z1',
      skills: ['electrical', 'solar'],
      equipment: ['ladder', 'multimeter'],
      eligible_zones: ['Z1', 'Z2'],
      shifts_count: 2,
      overtime_allowed: true,
    },
    {
      id: 'T02',
      name: 'Deepa Nair',
      home_zone_id: 'Z2',
      skills: ['cctv', 'networking'],
      equipment: ['appliance_toolkit'],
      eligible_zones: ['Z2', 'Z4'],
      shifts_count: 2,
      overtime_allowed: false,
    },
  ],
};

describe('OverviewPage Component', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => mockOverviewData,
      })
    );
  });

  it('renders overview KPI cards with genuine database values', async () => {
    render(<OverviewPage />);

    await waitFor(() => {
      expect(screen.getByText('108')).toBeInTheDocument();
      expect(screen.getByText('20')).toBeInTheDocument();
      expect(screen.getByText('7')).toBeInTheDocument();
      expect(screen.getByText('100 Pending')).toBeInTheDocument();
    });
  });

  it('renders jobs list and switches to technicians list tab', async () => {
    render(<OverviewPage />);

    await waitFor(() => {
      expect(screen.getByText('JOB-001')).toBeInTheDocument();
      expect(screen.getByText('Firewall setup')).toBeInTheDocument();
      expect(screen.getByText('Pioneer Apartments')).toBeInTheDocument();
    });

    // Switch to Technicians fleet tab
    const techTab = screen.getByRole('button', { name: /Technicians Fleet/i });
    fireEvent.click(techTab);

    await waitFor(() => {
      expect(screen.getByText('Arjun Rao')).toBeInTheDocument();
      expect(screen.getByText('Deepa Nair')).toBeInTheDocument();
      expect(screen.getByText('T01')).toBeInTheDocument();
    });
  });

  it('triggers data refresh on refresh button click', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockOverviewData,
    });
    vi.stubGlobal('fetch', fetchMock);

    render(<OverviewPage />);

    await waitFor(() => {
      expect(screen.getByText('108')).toBeInTheDocument();
    });

    const refreshButton = screen.getByRole('button', { name: /Refresh Data/i });
    fireEvent.click(refreshButton);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(2);
    });
  });

  it('renders error state when API request fails', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockRejectedValue(new Error('Network error: connection refused'))
    );

    render(<OverviewPage />);

    await waitFor(() => {
      expect(screen.getByText(/Failed to load overview data/i)).toBeInTheDocument();
      expect(screen.getByText(/Network error: connection refused/i)).toBeInTheDocument();
    });
  });
});
