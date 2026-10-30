import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import App from './App.tsx';

describe('DispatchGrid Application Shell & Routing', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          status: 'ok',
          service: 'DispatchGrid Backend Engine',
          version: '0.1.0',
          environment: 'development',
          simulation_clock: '2026-11-02T10:00:00+05:30',
          timestamp: '2026-10-30T10:00:00Z',
        }),
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
