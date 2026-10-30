import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import App from './App.tsx';

const mockOverview = {
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
  ],
};

describe('DispatchGrid Application Shell & Routing', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((url: string) => {
        if (url.includes('/overview')) {
          return Promise.resolve({
            ok: true,
            json: async () => mockOverview,
          });
        }
        return Promise.resolve({
          ok: true,
          json: async () => ({
            status: 'ok',
            service: 'DispatchGrid Backend Engine',
            version: '0.1.0',
            environment: 'development',
            simulation_clock: '2026-11-02T10:00:00+05:30',
            database: {
              status: 'connected',
              database: 'dispatchgrid',
              engine: 'postgresql',
              latency_ms: 1.2,
            },
            timestamp: '2026-10-30T10:00:00Z',
          }),
        });
      })
    );
  });

  it('renders application branding and header elements', async () => {
    render(<App />);
    const branding = screen.getAllByText('DispatchGrid');
    expect(branding.length).toBeGreaterThan(0);
    expect(screen.getByText('2026-11-02 10:00 IST')).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText('Healthy')).toBeInTheDocument();
    });
  });

  it('renders all 9 primary navigation items', async () => {
    render(<App />);
    const navItems = [
      'Overview',
      'Jobs',
      'Technicians',
      'Schedule',
      'Optimisation',
      'Disruptions',
      'Audit History',
      'Analytics',
      'Settings',
    ];

    navItems.forEach((item) => {
      const elements = screen.getAllByText(item);
      expect(elements.length).toBeGreaterThan(0);
    });

    await waitFor(() => {
      expect(screen.getByText('Healthy')).toBeInTheDocument();
    });
  });

  it('toggles sidebar collapse state on desktop', async () => {
    render(<App />);
    const collapseButton = screen.getByLabelText('Collapse sidebar');
    expect(collapseButton).toBeInTheDocument();

    fireEvent.click(collapseButton);
    expect(screen.getByLabelText('Expand sidebar')).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText('Expand sidebar'));
    expect(screen.getByLabelText('Collapse sidebar')).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText('Healthy')).toBeInTheDocument();
    });
  });

  it('navigates to Jobs page without broken routes', async () => {
    render(<App />);
    const jobsLinks = screen.getAllByRole('link', { name: /Jobs/i });
    fireEvent.click(jobsLinks[0]);

    await waitFor(() => {
      expect(screen.getByText('Jobs Management')).toBeInTheDocument();
      expect(screen.getByText('Jobs Management Engine Interface')).toBeInTheDocument();
    });
  });

  it('navigates to Technicians page without broken routes', async () => {
    render(<App />);
    const techLinks = screen.getAllByRole('link', { name: /Technicians/i });
    fireEvent.click(techLinks[0]);

    await waitFor(() => {
      expect(screen.getByText('Technicians Fleet')).toBeInTheDocument();
      expect(screen.getByText('Technicians Fleet Engine Interface')).toBeInTheDocument();
    });
  });

  it('navigates to Disruptions page without broken routes', async () => {
    render(<App />);
    const disrupLinks = screen.getAllByRole('link', { name: /Disruptions/i });
    fireEvent.click(disrupLinks[0]);

    await waitFor(() => {
      expect(screen.getByText('Disruptions & Recovery')).toBeInTheDocument();
      expect(screen.getByText('Disruptions & Recovery Engine Interface')).toBeInTheDocument();
    });
  });

  it('opens and closes mobile sidebar', async () => {
    render(<App />);
    const mobileButton = screen.getByLabelText('Open sidebar');
    fireEvent.click(mobileButton);

    const closeButton = screen.getByLabelText('Close menu');
    expect(closeButton).toBeInTheDocument();

    fireEvent.click(closeButton);
    expect(screen.queryByTestId('mobile-backdrop')).not.toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText('Healthy')).toBeInTheDocument();
    });
  });
});
