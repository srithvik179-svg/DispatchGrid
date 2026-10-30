import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { SchedulePage } from './SchedulePage';

const mockCurrentSchedule = {
  run_id: 'RUN-20261030-TEST',
  as_of: '2026-11-02T10:00:00+05:30',
  total_jobs: 108,
  assigned_count: 7,
  unassigned_count: 100,
  technicians_count: 20,
  technicians_utilized: 6,
  assignments: [
    {
      assignment_id: 1,
      job_id: 'JOB-101',
      technician_id: 'T03',
      technician_name: 'Karthik Gowda',
      job_title: 'Blocked drain clearance',
      customer_name: 'Hillview Mall',
      zone_id: 'Z2',
      priority: 3,
      priority_label: 'medium',
      start_time: '2026-11-02T08:00:00+05:30',
      end_time: '2026-11-02T09:15:00+05:30',
      duration_minutes: 75,
      travel_time_minutes: 4.08,
      distance_km: 2.04,
      status: 'completed',
      is_existing: true,
    },
  ],
  unassigned_jobs: [
    {
      job_id: 'JOB-017',
      title: 'Substation inspection',
      customer_name: 'North Grid Station',
      zone_id: 'Z6',
      priority: 1,
      priority_label: 'urgent',
      duration_minutes: 120,
      classification: 'permanently_impossible',
      primary_category: 'uncovered_zone',
      rejection_summary: "Job is located in Zone 'Z6', but zero technicians in the entire fleet are certified for Zone 'Z6'.",
      actionable_recommendation: "Assign or cross-certify at least one field technician for operational Zone 'Z6'.",
      required_skills: ['electrical'],
      required_equipment: [],
    },
    {
      job_id: 'JOB-014',
      title: 'High-voltage line audit',
      customer_name: 'PowerCorp Industrial',
      zone_id: 'Z1',
      priority: 1,
      priority_label: 'urgent',
      duration_minutes: 90,
      classification: 'permanently_impossible',
      primary_category: 'unsupported_skill',
      rejection_summary: "Job requires unsupported specialized skill(s): high_voltage.",
      actionable_recommendation: "Dispatch an accredited external high-voltage contractor.",
      required_skills: ['high_voltage'],
      required_equipment: [],
    },
  ],
  metrics: {
    locked_existing_assignments: 7,
    scheduled_assignments: 0,
  },
};

const mockGeneratedSchedule = {
  run_id: 'RUN-20261030-GENERATED',
  as_of: '2026-11-02T10:00:00+05:30',
  total_jobs: 108,
  assigned_count: 88,
  unassigned_count: 19,
  technicians_count: 20,
  technicians_utilized: 20,
  assignments: [
    ...mockCurrentSchedule.assignments,
    {
      assignment_id: 8,
      job_id: 'JOB-001',
      technician_id: 'T13',
      technician_name: 'Sanjana Hegde',
      job_title: 'Firewall setup',
      customer_name: 'Pioneer Apartments',
      zone_id: 'Z1',
      priority: 3,
      priority_label: 'medium',
      start_time: '2026-11-02T13:45:00+05:30',
      end_time: '2026-11-02T14:30:00+05:30',
      duration_minutes: 45,
      travel_time_minutes: 11.52,
      distance_km: 5.76,
      status: 'scheduled',
      is_existing: false,
    },
  ],
  unassigned_jobs: mockCurrentSchedule.unassigned_jobs,
  metrics: {
    locked_existing_assignments: 7,
    scheduled_assignments: 81,
  },
};

const mockTechSchedule = {
  technician_id: 'T03',
  technician_name: 'Karthik Gowda',
  home_zone_id: 'Z2',
  home_lat: 12.3114,
  home_lng: 76.6548,
  eligible_zones: ['Z1', 'Z2'],
  skills: ['plumbing'],
  equipment: ['pipe_wrench'],
  total_assigned_jobs: 1,
  total_working_minutes: 75,
  total_travel_minutes: 4.08,
  itinerary: [
    {
      assignment_id: 1,
      job_id: 'JOB-101',
      job_title: 'Blocked drain clearance',
      customer_name: 'Hillview Mall',
      zone_id: 'Z2',
      lat: 12.32,
      lng: 76.66,
      start_time: '2026-11-02T08:00:00+05:30',
      end_time: '2026-11-02T09:15:00+05:30',
      duration_minutes: 75,
      travel_from_previous_minutes: 4.08,
      distance_from_previous_km: 2.04,
      status: 'completed',
      is_existing: true,
    },
  ],
};

describe('SchedulePage Component', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    global.fetch = vi.fn().mockImplementation((url: string, opts?: any) => {
      if (url.includes('/api/v1/schedule/current')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(mockCurrentSchedule),
        });
      }
      if (url.includes('/api/v1/schedule/generate') && opts?.method === 'POST') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(mockGeneratedSchedule),
        });
      }
      if (url.includes('/api/v1/technicians/')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(mockTechSchedule),
        });
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({}),
      });
    });
  });

  it('renders schedule page header, buttons, and KPI counts', async () => {
    render(<SchedulePage />);

    expect(screen.getByText('Workforce Schedule & Dispatch')).toBeInTheDocument();
    expect(screen.getByTestId('generate-schedule-btn')).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByTestId('assigned-count')).toHaveTextContent('7');
      expect(screen.getByTestId('unassigned-count')).toHaveTextContent('100');
    });
  });

  it('displays assigned jobs list with technician and time details', async () => {
    render(<SchedulePage />);

    await waitFor(() => {
      expect(screen.getByText('JOB-101')).toBeInTheDocument();
      expect(screen.getByText('Blocked drain clearance')).toBeInTheDocument();
      expect(screen.getByText('Karthik Gowda')).toBeInTheDocument();
      expect(screen.getByText('Protected')).toBeInTheDocument();
    });
  });

  it('switches to Unassigned tab and renders unassigned explanations', async () => {
    render(<SchedulePage />);

    await waitFor(() => {
      expect(screen.getByTestId('tab-unassigned')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId('tab-unassigned'));

    await waitFor(() => {
      expect(screen.getByText('JOB-017')).toBeInTheDocument();
      expect(screen.getByText('Substation inspection')).toBeInTheDocument();
      expect(screen.getByText('JOB-014')).toBeInTheDocument();
      expect(screen.getByText('High-voltage line audit')).toBeInTheDocument();
      expect(screen.getByText(/Job is located in Zone 'Z6'/)).toBeInTheDocument();
      expect(screen.getByText(/Job requires unsupported specialized skill/)).toBeInTheDocument();
    });
  });

  it('triggers schedule generation and updates assigned count', async () => {
    render(<SchedulePage />);

    await waitFor(() => {
      expect(screen.getByTestId('assigned-count')).toHaveTextContent('7');
    });

    fireEvent.click(screen.getByTestId('generate-schedule-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('assigned-count')).toHaveTextContent('88');
      expect(screen.getByTestId('unassigned-count')).toHaveTextContent('19');
    });

    // Verify newly scheduled job is now in the list
    expect(screen.getByText('JOB-001')).toBeInTheDocument();
    expect(screen.getByText('Sanjana Hegde')).toBeInTheDocument();
  });

  it('switches to Technician Itineraries tab and displays timeline', async () => {
    render(<SchedulePage />);

    await waitFor(() => {
      expect(screen.getByTestId('tab-timeline')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId('tab-timeline'));

    await waitFor(() => {
      expect(screen.getByText('Technician Dispatch Itinerary')).toBeInTheDocument();
      expect(screen.getByText('Home Depot Base')).toBeInTheDocument();
    });
  });
});
