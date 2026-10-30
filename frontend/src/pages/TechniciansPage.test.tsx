import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { TechniciansPage } from './TechniciansPage';

const mockTechniciansList = [
  {
    id: 'T01',
    name: 'Arjun Rao',
    home_zone_id: 'Z1',
    home_lat: 12.3052,
    home_lng: 76.6552,
    home_location: {
      lat: 12.3052,
      lng: 76.6552,
    },
    eligible_zones: ['Z1', 'Z2'],
    skills: ['electrical', 'solar'],
    equipment: ['ladder', 'multimeter'],
    shifts: [
      {
        date: '2026-11-02',
        start: '2026-11-02T09:00:00+05:30',
        end: '2026-11-02T18:00:00+05:30',
      },
    ],
    unavailable_periods: [],
    overtime_allowed: true,
    max_overtime_minutes: 60,
    overtime: {
      allowed: true,
      max_minutes_per_shift: 60,
    },
  },
  {
    id: 'T02',
    name: 'Meera Nair',
    home_zone_id: 'Z4',
    home_lat: 12.3,
    home_lng: 76.72,
    home_location: {
      lat: 12.3,
      lng: 76.72,
    },
    eligible_zones: ['Z4', 'Z1'],
    skills: ['hvac', 'appliance_repair'],
    equipment: ['appliance_toolkit', 'hvac_gauge'],
    shifts: [
      {
        date: '2026-11-02',
        start: '2026-11-02T10:00:00+05:30',
        end: '2026-11-02T19:00:00+05:30',
      },
    ],
    unavailable_periods: [
      {
        start: '2026-11-02T14:00:00+05:30',
        end: '2026-11-02T16:00:00+05:30',
        reason: 'training',
      },
    ],
    overtime_allowed: false,
    max_overtime_minutes: 0,
    overtime: {
      allowed: false,
      max_minutes_per_shift: 0,
    },
  },
];

describe('TechniciansPage Component', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((_url: string, opts?: any) => {
        if (opts && opts.method === 'PATCH') {
          return Promise.resolve({
            ok: true,
            json: async () => ({
              ...mockTechniciansList[0],
              name: 'Arjun Rao Updated',
              skills: ['electrical', 'solar', 'networking'],
            }),
          });
        }
        if (opts && opts.method === 'POST') {
          return Promise.resolve({
            ok: true,
            json: async () => ({
              id: 'T21',
              name: 'Suresh Kumar',
              home_zone_id: 'Z3',
              home_lat: 12.25,
              home_lng: 76.645,
              home_location: { lat: 12.25, lng: 76.645 },
              eligible_zones: ['Z3'],
              skills: ['networking'],
              equipment: ['fiber_splicer'],
              shifts: [
                {
                  date: '2026-11-02',
                  start: '2026-11-02T09:00:00+05:30',
                  end: '2026-11-02T18:00:00+05:30',
                },
              ],
              unavailable_periods: [],
              overtime_allowed: true,
              max_overtime_minutes: 60,
              overtime: { allowed: true, max_minutes_per_shift: 60 },
            }),
          });
        }
        return Promise.resolve({
          ok: true,
          json: async () => mockTechniciansList,
        });
      })
    );
  });

  it('renders technician fleet list with database attributes', async () => {
    render(<TechniciansPage />);

    await waitFor(() => {
      expect(screen.getByText('T01')).toBeInTheDocument();
      expect(screen.getByText('Arjun Rao')).toBeInTheDocument();
      expect(screen.getByText('T02')).toBeInTheDocument();
      expect(screen.getByText('Meera Nair')).toBeInTheDocument();
    });
  });

  it('filters technicians using search input', async () => {
    render(<TechniciansPage />);

    await waitFor(() => {
      expect(screen.getByText('Arjun Rao')).toBeInTheDocument();
    });

    const searchInput = screen.getByPlaceholderText(/Search by ID, name, skill, or equipment/i);
    fireEvent.change(searchInput, { target: { value: 'Meera' } });

    await waitFor(() => {
      expect(screen.queryByText('Arjun Rao')).not.toBeInTheDocument();
      expect(screen.getByText('Meera Nair')).toBeInTheDocument();
    });
  });

  it('filters technicians using zone filter dropdown', async () => {
    render(<TechniciansPage />);

    await waitFor(() => {
      expect(screen.getByText('Arjun Rao')).toBeInTheDocument();
    });

    const zoneSelect = screen.getByLabelText(/Filter by Zone/i);
    fireEvent.change(zoneSelect, { target: { value: 'Z4' } });

    await waitFor(() => {
      expect(screen.getByText('Meera Nair')).toBeInTheDocument();
      expect(screen.queryByText('Arjun Rao')).not.toBeInTheDocument();
    });
  });

  it('filters technicians using skill filter dropdown', async () => {
    render(<TechniciansPage />);

    await waitFor(() => {
      expect(screen.getByText('Arjun Rao')).toBeInTheDocument();
    });

    const skillSelect = screen.getByLabelText(/Filter by Skill/i);
    fireEvent.change(skillSelect, { target: { value: 'hvac' } });

    await waitFor(() => {
      expect(screen.queryByText('Arjun Rao')).not.toBeInTheDocument();
      expect(screen.getByText('Meera Nair')).toBeInTheDocument();
    });
  });

  it('opens technician detail inspection modal on click', async () => {
    render(<TechniciansPage />);

    await waitFor(() => {
      expect(screen.getByText('Arjun Rao')).toBeInTheDocument();
    });

    const detailsBtn = screen.getByLabelText('View Details for T01');
    fireEvent.click(detailsBtn);

    await waitFor(() => {
      expect(screen.getByTestId('technician-detail-modal')).toBeInTheDocument();
      expect(screen.getByText('Working Shifts Schedule')).toBeInTheDocument();
      expect(screen.getByText('Certified Skill Credentials')).toBeInTheDocument();
    });
  });

  it('opens technician registration modal and submits new technician', async () => {
    render(<TechniciansPage />);

    const registerBtn = screen.getByRole('button', { name: /Register Technician/i });
    fireEvent.click(registerBtn);

    await waitFor(() => {
      expect(screen.getByTestId('create-technician-modal')).toBeInTheDocument();
    });

    // Enter name
    const nameInput = screen.getByPlaceholderText(/e.g. Ramesh Kumar/i);
    fireEvent.change(nameInput, { target: { value: 'Suresh Kumar' } });

    // Submit form
    const submitBtn = screen.getByTestId('submit-register-tech-btn');
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(
        screen.getByText(/Technician T21 \(Suresh Kumar\) registered successfully!/i)
      ).toBeInTheDocument();
    });
  });

  it('opens edit modal and updates technician credentials', async () => {
    render(<TechniciansPage />);

    await waitFor(() => {
      expect(screen.getByText('Arjun Rao')).toBeInTheDocument();
    });

    const editBtn = screen.getByLabelText('Edit T01');
    fireEvent.click(editBtn);

    await waitFor(() => {
      expect(screen.getByTestId('edit-technician-modal')).toBeInTheDocument();
      expect(screen.getByText(/Edit Technician T01/i)).toBeInTheDocument();
    });

    const nameInput = screen.getByDisplayValue('Arjun Rao');
    fireEvent.change(nameInput, { target: { value: 'Arjun Rao Updated' } });

    const saveBtn = screen.getByRole('button', { name: /Save Changes/i });
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(screen.queryByTestId('edit-technician-modal')).not.toBeInTheDocument();
    });
  });
});
