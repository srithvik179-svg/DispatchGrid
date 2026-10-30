import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import App from './App.tsx';

describe('App Landing Page', () => {
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

  it('renders landing page titled DispatchGrid', async () => {
    render(<App />);
    const titleElements = screen.getAllByText(/DispatchGrid/i);
    expect(titleElements.length).toBeGreaterThan(0);
    expect(
      screen.getByText(/Intelligent Workforce Scheduling & Recovery Engine/i)
    ).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText(/SYSTEM ONLINE/i)).toBeInTheDocument();
    });
  });

  it('renders application health card', async () => {
    render(<App />);
    expect(screen.getByText(/Application Health Status/i)).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText(/SYSTEM ONLINE/i)).toBeInTheDocument();
    });
  });
});
