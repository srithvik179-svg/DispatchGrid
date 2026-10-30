import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { JobsPage } from './JobsPage';

const mockJobsList = [
  {
    id: 'JOB-001',
    customer_name: 'Pioneer Apartments',
    title: 'Firewall setup',
    zone_id: 'Z3',
    lat: 12.2535,
    lng: 76.6514,
    address: '18 Industrial Estate Road',
    priority: 3,
    priority_label: 'medium',
    duration_minutes: 45,
    required_skills: ['networking'],
    required_equipment: ['fiber_splicer'],
    time_window_start: '2026-11-02T13:45:00+05:30',
    time_window_end: '2026-11-02T18:15:00+05:30',
    sla_deadline: '2026-11-02T18:15:00+05:30',
    status: 'pending',
    assigned_technician_id: null,
    scheduled_start: null,
    scheduled_end: null,
    created_at: '2026-11-01T20:30:00+05:30',
    tags: [],
  },
  {
    id: 'JOB-101',
    customer_name: 'Apex Residency',
    title: 'Water filter maintenance',
    zone_id: 'Z2',
    lat: 12.355,
    lng: 76.64,
    address: '42 Main St',
    priority: 1,
    priority_label: 'urgent',
    duration_minutes: 75,
    required_skills: ['plumbing'],
    required_equipment: ['pipe_wrench'],
    time_window_start: '2026-11-02T08:00:00+05:30',
    time_window_end: '2026-11-02T10:00:00+05:30',
    sla_deadline: '2026-11-02T10:00:00+05:30',
    status: 'completed',
    assigned_technician_id: 'T03',
    scheduled_start: '2026-11-02T08:00:00+05:30',
    scheduled_end: '2026-11-02T09:15:00+05:30',
    created_at: '2026-11-01T18:00:00+05:30',
    tags: [],
  },
];

const mockHistoryList = [
  {
    id: 1,
    job_id: 'JOB-001',
    from_status: null,
    to_status: 'pending',
    reason: 'Initial dataset import',
    changed_by: 'system',
    changed_at: '2026-11-02T10:00:00+05:30',
  },
];

describe('JobsPage Component', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((url: string, opts?: any) => {
        if (typeof url === 'string' && url.includes('/history')) {
          return Promise.resolve({
            ok: true,
            json: async () => mockHistoryList,
          });
        }
        if (opts && opts.method === 'PATCH') {
          return Promise.resolve({
            ok: true,
            json: async () => ({
              ...mockJobsList[0],
              title: 'Firewall setup updated',
              priority: 2,
              priority_label: 'high',
            }),
          });
        }
        if (opts && opts.method === 'POST' && typeof url === 'string' && url.includes('/cancel')) {
          return Promise.resolve({
            ok: true,
            json: async () => ({
              ...mockJobsList[0],
              status: 'cancelled',
            }),
          });
        }
        if (opts && opts.method === 'POST') {
          return Promise.resolve({
            ok: true,
            json: async () => ({
              id: 'JOB-109',
              title: 'New Emergency Request',
              customer_name: 'City Hospital',
              zone_id: 'Z1',
              priority: 1,
              priority_label: 'urgent',
              duration_minutes: 60,
              required_skills: ['electrical'],
              required_equipment: ['multimeter'],
              time_window_start: '2026-11-02T10:00:00+05:30',
              time_window_end: '2026-11-02T14:00:00+05:30',
              sla_deadline: '2026-11-02T14:00:00+05:30',
              status: 'pending',
              lat: 12.3052,
              lng: 76.6552,
              address: 'City Center',
              tags: [],
              created_at: '2026-11-02T10:00:00+05:30',
            }),
          });
        }
        return Promise.resolve({
          ok: true,
          json: async () => mockJobsList,
        });
      })
    );
  });

  it('renders job list with items from the backend', async () => {
    render(<JobsPage />);

    await waitFor(() => {
      expect(screen.getByText('JOB-001')).toBeInTheDocument();
      expect(screen.getByText('Firewall setup')).toBeInTheDocument();
      expect(screen.getByText('JOB-101')).toBeInTheDocument();
      expect(screen.getByText('Water filter maintenance')).toBeInTheDocument();
    });
  });

  it('filters jobs using search input', async () => {
    render(<JobsPage />);

    await waitFor(() => {
      expect(screen.getByText('Firewall setup')).toBeInTheDocument();
    });

    const searchInput = screen.getByPlaceholderText(/Search by job ID, title, or customer name/i);
    fireEvent.change(searchInput, { target: { value: 'Water filter' } });

    await waitFor(() => {
      expect(screen.queryByText('Firewall setup')).not.toBeInTheDocument();
      expect(screen.getByText('Water filter maintenance')).toBeInTheDocument();
    });
  });

  it('filters jobs using status dropdown', async () => {
    render(<JobsPage />);

    await waitFor(() => {
      expect(screen.getByText('Firewall setup')).toBeInTheDocument();
    });

    const statusSelect = screen.getByLabelText(/Filter by Status/i);
    fireEvent.change(statusSelect, { target: { value: 'completed' } });

    await waitFor(() => {
      expect(screen.queryByText('Firewall setup')).not.toBeInTheDocument();
      expect(screen.getByText('Water filter maintenance')).toBeInTheDocument();
    });
  });

  it('opens job detail modal and displays state history', async () => {
    render(<JobsPage />);

    await waitFor(() => {
      expect(screen.getByText('Firewall setup')).toBeInTheDocument();
    });

    const viewButton = screen.getAllByRole('button', { name: /View Details/i })[0];
    fireEvent.click(viewButton);

    await waitFor(() => {
      expect(screen.getByTestId('job-detail-modal')).toBeInTheDocument();
      expect(screen.getByText('Operational Timing Constraints')).toBeInTheDocument();
      expect(screen.getByText('State Transition Audit Trail')).toBeInTheDocument();
      expect(screen.getByText('Initial dataset import')).toBeInTheDocument();
    });
  });

  it('opens create job modal and submits new job request', async () => {
    render(<JobsPage />);

    const createButton = screen.getByRole('button', { name: /New Job Request/i });
    fireEvent.click(createButton);

    await waitFor(() => {
      expect(screen.getByTestId('create-job-modal')).toBeInTheDocument();
    });

    // Fill form inputs
    fireEvent.change(screen.getByPlaceholderText(/e.g. Elevator motor inspection/i), {
      target: { value: 'New Emergency Request' },
    });
    fireEvent.change(screen.getByPlaceholderText(/e.g. Skyline Towers/i), {
      target: { value: 'City Hospital' },
    });

    const submitBtn = screen.getByRole('button', { name: /Submit Job Request/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByText(/Job JOB-109 successfully created!/i)).toBeInTheDocument();
    });
  });

  it('opens edit modal and updates job details', async () => {
    render(<JobsPage />);

    await waitFor(() => {
      expect(screen.getByText('Firewall setup')).toBeInTheDocument();
    });

    const editBtn = screen.getByLabelText('Edit JOB-001');
    fireEvent.click(editBtn);

    await waitFor(() => {
      expect(screen.getByTestId('edit-job-modal')).toBeInTheDocument();
      expect(screen.getByText(/Edit Job JOB-001/i)).toBeInTheDocument();
    });

    // Change title
    const titleInput = screen.getByDisplayValue('Firewall setup');
    fireEvent.change(titleInput, { target: { value: 'Firewall setup updated' } });

    // Submit edit form
    const saveBtn = screen.getByRole('button', { name: /Save Changes/i });
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(screen.queryByTestId('edit-job-modal')).not.toBeInTheDocument();
    });
  });

  it('opens cancel modal and confirms cancellation with reason', async () => {
    render(<JobsPage />);

    await waitFor(() => {
      expect(screen.getByText('Firewall setup')).toBeInTheDocument();
    });

    const cancelBtn = screen.getByLabelText('Cancel JOB-001');
    fireEvent.click(cancelBtn);

    await waitFor(() => {
      expect(screen.getByTestId('cancel-confirm-modal')).toBeInTheDocument();
      expect(screen.getByText(/Cancel Job JOB-001\?/i)).toBeInTheDocument();
    });

    // Enter cancellation reason
    const reasonInput = screen.getByPlaceholderText(/e.g. Customer cancelled appointment/i);
    fireEvent.change(reasonInput, { target: { value: 'Client requested postponement' } });

    // Submit cancellation
    const confirmBtn = screen.getByRole('button', { name: /Confirm Cancellation/i });
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(screen.queryByTestId('cancel-confirm-modal')).not.toBeInTheDocument();
    });
  });

  it('protects completed jobs by disabling edit and cancel actions', async () => {
    render(<JobsPage />);

    await waitFor(() => {
      expect(screen.getByText('Water filter maintenance')).toBeInTheDocument();
    });

    // JOB-101 is completed, so it should have a lock icon indicator and no Edit/Cancel buttons
    expect(screen.queryByLabelText('Edit JOB-101')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Cancel JOB-101')).not.toBeInTheDocument();
    expect(screen.getByTitle(/Completed\/Cancelled jobs are protected/i)).toBeInTheDocument();
  });
});
