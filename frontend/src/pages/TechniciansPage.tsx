import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { PageHeader } from '../components/common/PageHeader';
import {
  Users,
  Search,
  Plus,
  RefreshCw,
  AlertCircle,
  CheckCircle2,
  X,
  Edit2,
  Clock,
  MapPin,
  Calendar,
  AlertTriangle,
} from 'lucide-react';

export interface Shift {
  date: string;
  start: string;
  end: string;
}

export interface UnavailablePeriod {
  start: string;
  end: string;
  reason?: string;
}

export interface OvertimeConfig {
  allowed: boolean;
  max_minutes_per_shift: number;
}

export interface LocationData {
  lat: number;
  lng: number;
  address?: string;
}

export interface Technician {
  id: string;
  name: string;
  home_zone_id: string | null;
  home_lat: number;
  home_lng: number;
  home_location: LocationData;
  eligible_zones: string[];
  skills: string[];
  equipment: string[];
  shifts: Shift[];
  unavailable_periods: UnavailablePeriod[];
  overtime_allowed: boolean;
  max_overtime_minutes: number;
  overtime: OvertimeConfig;
}

const STANDARD_SKILLS = [
  'electrical',
  'plumbing',
  'hvac',
  'networking',
  'appliance_repair',
  'solar',
  'cctv',
  'elevator',
];

const STANDARD_EQUIPMENT = [
  'ladder',
  'multimeter',
  'hvac_gauge',
  'pipe_wrench',
  'appliance_toolkit',
  'fiber_splicer',
  'scissor_lift',
];

const ZONE_COORDINATES: Record<string, { name: string; lat: number; lng: number }> = {
  Z1: { name: 'Central', lat: 12.3052, lng: 76.6552 },
  Z2: { name: 'North', lat: 12.355, lng: 76.64 },
  Z3: { name: 'South', lat: 12.25, lng: 76.645 },
  Z4: { name: 'East', lat: 12.3, lng: 76.72 },
  Z5: { name: 'West', lat: 12.3, lng: 76.57 },
  Z6: { name: 'Outskirts', lat: 12.45, lng: 76.85 },
};

const ZONES = ['Z1', 'Z2', 'Z3', 'Z4', 'Z5', 'Z6'];

export const TechniciansPage: React.FC = () => {
  const [technicians, setTechnicians] = useState<Technician[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Search & Filter state
  const [searchTerm, setSearchTerm] = useState('');
  const [zoneFilter, setZoneFilter] = useState('all');
  const [skillFilter, setSkillFilter] = useState('all');
  const [overtimeFilter, setOvertimeFilter] = useState('all');

  // Modals state
  const [selectedTechnician, setSelectedTechnician] = useState<Technician | null>(null);
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [editingTechnician, setEditingTechnician] = useState<Technician | null>(null);

  // Create Form State
  const [createSubmitting, setCreateSubmitting] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [createSuccess, setCreateSuccess] = useState<string | null>(null);
  const [createForm, setCreateForm] = useState({
    id: '',
    name: '',
    home_zone_id: 'Z1',
    home_lat: 12.3052,
    home_lng: 76.6552,
    eligible_zones: ['Z1'],
    skills: ['electrical'],
    equipment: ['multimeter', 'ladder'],
    shifts: [
      {
        date: '2026-11-02',
        start: '2026-11-02T09:00',
        end: '2026-11-02T18:00',
      },
    ],
    unavailable_periods: [] as { start: string; end: string; reason: string }[],
    overtime_allowed: true,
    max_overtime_minutes: 60,
  });

  // Edit Form State
  const [editSubmitting, setEditSubmitting] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);
  const [editForm, setEditForm] = useState({
    name: '',
    home_zone_id: 'Z1',
    home_lat: 12.3052,
    home_lng: 76.6552,
    eligible_zones: [] as string[],
    skills: [] as string[],
    equipment: [] as string[],
    shifts: [] as { date: string; start: string; end: string }[],
    unavailable_periods: [] as { start: string; end: string; reason: string }[],
    overtime_allowed: false,
    max_overtime_minutes: 0,
  });

  const fetchTechnicians = useCallback(async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    else setLoading(true);

    try {
      const apiUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
      const res = await fetch(`${apiUrl}/api/v1/technicians?limit=200`);
      if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
      const data = await res.json();
      setTechnicians(Array.isArray(data) ? data : []);
      setError(null);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load technicians');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchTechnicians();
  }, [fetchTechnicians]);

  // Open Edit Modal with pre-filled state
  const handleOpenEdit = (tech: Technician, e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    setEditingTechnician(tech);
    setEditError(null);
    setEditForm({
      name: tech.name,
      home_zone_id: tech.home_zone_id || 'Z1',
      home_lat: tech.home_lat,
      home_lng: tech.home_lng,
      eligible_zones: [...tech.eligible_zones],
      skills: [...tech.skills],
      equipment: [...tech.equipment],
      shifts: tech.shifts.map((s) => ({
        date: s.date,
        start: s.start.slice(0, 16),
        end: s.end.slice(0, 16),
      })),
      unavailable_periods: tech.unavailable_periods.map((u) => ({
        start: u.start.slice(0, 16),
        end: u.end.slice(0, 16),
        reason: u.reason || 'unavailable',
      })),
      overtime_allowed: tech.overtime_allowed,
      max_overtime_minutes: tech.max_overtime_minutes,
    });
  };

  // Submit Create Technician
  const handleCreateSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setCreateSubmitting(true);
    setCreateError(null);
    setCreateSuccess(null);

    try {
      if (!createForm.name.trim()) {
        throw new Error('Technician name cannot be empty');
      }

      const payload = {
        id: createForm.id.trim() || undefined,
        name: createForm.name.trim(),
        home_zone_id: createForm.home_zone_id,
        home_location: {
          lat: Number(createForm.home_lat),
          lng: Number(createForm.home_lng),
        },
        eligible_zones: createForm.eligible_zones,
        skills: createForm.skills,
        equipment: createForm.equipment,
        shifts: createForm.shifts.map((s) => ({
          date: s.date,
          start: `${s.start}:00+05:30`,
          end: `${s.end}:00+05:30`,
        })),
        unavailable_periods: createForm.unavailable_periods.map((u) => ({
          start: `${u.start}:00+05:30`,
          end: `${u.end}:00+05:30`,
          reason: u.reason,
        })),
        overtime: {
          allowed: createForm.overtime_allowed,
          max_minutes_per_shift: Number(createForm.max_overtime_minutes),
        },
      };

      const apiUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
      const res = await fetch(`${apiUrl}/api/v1/technicians`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || `Registration failed (HTTP ${res.status})`);
      }

      setCreateSuccess(`Technician ${data.id} (${data.name}) registered successfully!`);
      await fetchTechnicians(true);
      setTimeout(() => {
        setIsCreateOpen(false);
        setCreateSuccess(null);
      }, 1200);
    } catch (err: unknown) {
      setCreateError(err instanceof Error ? err.message : 'Registration failed');
    } finally {
      setCreateSubmitting(false);
    }
  };

  // Submit Edit Technician
  const handleEditSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingTechnician) return;
    setEditSubmitting(true);
    setEditError(null);

    try {
      if (!editForm.name.trim()) {
        throw new Error('Technician name cannot be empty');
      }

      const payload = {
        name: editForm.name.trim(),
        home_zone_id: editForm.home_zone_id,
        home_location: {
          lat: Number(editForm.home_lat),
          lng: Number(editForm.home_lng),
        },
        eligible_zones: editForm.eligible_zones,
        skills: editForm.skills,
        equipment: editForm.equipment,
        shifts: editForm.shifts.map((s) => ({
          date: s.date,
          start: `${s.start}:00+05:30`,
          end: `${s.end}:00+05:30`,
        })),
        unavailable_periods: editForm.unavailable_periods.map((u) => ({
          start: `${u.start}:00+05:30`,
          end: `${u.end}:00+05:30`,
          reason: u.reason,
        })),
        overtime: {
          allowed: editForm.overtime_allowed,
          max_minutes_per_shift: Number(editForm.max_overtime_minutes),
        },
      };

      const apiUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
      const res = await fetch(`${apiUrl}/api/v1/technicians/${editingTechnician.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || `Update failed (HTTP ${res.status})`);
      }

      await fetchTechnicians(true);
      if (selectedTechnician && selectedTechnician.id === editingTechnician.id) {
        setSelectedTechnician(data);
      }
      setEditingTechnician(null);
    } catch (err: unknown) {
      setEditError(err instanceof Error ? err.message : 'Update failed');
    } finally {
      setEditSubmitting(false);
    }
  };

  // Filtered technicians list
  const filteredTechnicians = useMemo(() => {
    return technicians.filter((tech) => {
      // Search matching ID, name, skills, equipment
      if (searchTerm) {
        const q = searchTerm.toLowerCase();
        const matchesId = tech.id.toLowerCase().includes(q);
        const matchesName = tech.name.toLowerCase().includes(q);
        const matchesSkill = tech.skills.some((s) => s.toLowerCase().includes(q));
        const matchesEquip = tech.equipment.some((e) => e.toLowerCase().includes(q));
        if (!matchesId && !matchesName && !matchesSkill && !matchesEquip) return false;
      }

      // Zone filter
      if (zoneFilter !== 'all') {
        const matchesHome = tech.home_zone_id === zoneFilter;
        const matchesEligible = tech.eligible_zones.includes(zoneFilter);
        if (!matchesHome && !matchesEligible) return false;
      }

      // Skill filter
      if (skillFilter !== 'all') {
        if (!tech.skills.includes(skillFilter)) return false;
      }

      // Overtime filter
      if (overtimeFilter !== 'all') {
        if (overtimeFilter === 'allowed' && !tech.overtime_allowed) return false;
        if (overtimeFilter === 'prohibited' && tech.overtime_allowed) return false;
      }

      return true;
    });
  }, [technicians, searchTerm, zoneFilter, skillFilter, overtimeFilter]);

  const formatTimeOnly = (dtStr: string) => {
    try {
      const d = new Date(dtStr);
      return d.toLocaleTimeString('en-IN', {
        hour: '2-digit',
        minute: '2-digit',
        hour12: false,
      });
    } catch {
      return dtStr;
    }
  };

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <PageHeader
        title="Technicians Fleet"
        description="Field workforce registry, certified skill sets, onboard equipment kits, shifts, and operational availability."
        badge={`${technicians.length} Active Technicians`}
        action={
          <div className="flex items-center space-x-3">
            <button
              onClick={() => fetchTechnicians(true)}
              disabled={refreshing || loading}
              className="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-300 hover:text-white transition"
              aria-label="Refresh technicians"
            >
              <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin text-indigo-400' : ''}`} />
            </button>

            <button
              onClick={() => setIsCreateOpen(true)}
              className="inline-flex items-center space-x-2 px-3.5 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold shadow-md shadow-indigo-600/30 transition"
              aria-label="Register Technician"
            >
              <Plus className="w-4 h-4" />
              <span>Register Technician</span>
            </button>
          </div>
        }
      />

      {/* Subheader Context */}
      <div className="flex items-center space-x-2 text-xs text-slate-400 bg-slate-900/40 p-2.5 rounded-lg border border-slate-800/80">
        <Users className="w-4 h-4 text-indigo-400 shrink-0" />
        <span className="font-semibold text-white">Technicians Fleet Engine Interface</span>
        <span className="text-slate-600">&bull;</span>
        <span>Real-time workforce registry, multi-zone certifications, and operational shifts.</span>
      </div>

      {/* Global Error Banner */}
      {error && (
        <div className="p-4 rounded-xl bg-rose-950/50 border border-rose-800/80 text-rose-200 flex items-start space-x-3 text-sm">
          <AlertCircle className="w-5 h-5 text-rose-400 shrink-0 mt-0.5" />
          <div className="flex-1">
            <span className="font-semibold block">Failed to load technician fleet</span>
            <span className="text-xs text-rose-300">{error}</span>
          </div>
          <button
            onClick={() => fetchTechnicians(false)}
            className="px-3 py-1 rounded bg-rose-900/80 hover:bg-rose-800 text-xs font-medium text-white transition border border-rose-700"
          >
            Retry
          </button>
        </div>
      )}

      {/* Summary KPI Badges */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800">
          <div className="flex items-center justify-between">
            <span className="text-xs text-slate-400">Total Fleet</span>
            <Users className="w-4 h-4 text-indigo-400" />
          </div>
          <div className="text-2xl font-bold text-white mt-1">{technicians.length}</div>
          <div className="text-[11px] text-slate-500 mt-0.5">Field service resources</div>
        </div>

        <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800">
          <div className="flex items-center justify-between">
            <span className="text-xs text-slate-400">Overtime Ready</span>
            <Clock className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="text-2xl font-bold text-white mt-1">
            {technicians.filter((t) => t.overtime_allowed).length}
          </div>
          <div className="text-[11px] text-slate-500 mt-0.5">Policy authorized</div>
        </div>

        <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800">
          <div className="flex items-center justify-between">
            <span className="text-xs text-slate-400">Multi-Zone Fleet</span>
            <MapPin className="w-4 h-4 text-blue-400" />
          </div>
          <div className="text-2xl font-bold text-white mt-1">
            {technicians.filter((t) => t.eligible_zones.length > 1).length}
          </div>
          <div className="text-[11px] text-slate-500 mt-0.5">Cross-zone certified</div>
        </div>

        <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800">
          <div className="flex items-center justify-between">
            <span className="text-xs text-slate-400">Scheduled Leaves</span>
            <AlertTriangle className="w-4 h-4 text-amber-400" />
          </div>
          <div className="text-2xl font-bold text-white mt-1">
            {technicians.filter((t) => t.unavailable_periods.length > 0).length}
          </div>
          <div className="text-[11px] text-slate-500 mt-0.5">With planned breaks</div>
        </div>
      </div>

      {/* Search and Filters Bar */}
      <div className="p-4 rounded-xl bg-slate-900/70 border border-slate-800 flex flex-col md:flex-row items-stretch md:items-center justify-between gap-4">
        <div className="relative flex-1">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            placeholder="Search by ID, name, skill, or equipment..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full pl-9 pr-4 py-2 rounded-lg bg-slate-950 border border-slate-800 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500"
          />
          {searchTerm && (
            <button
              onClick={() => setSearchTerm('')}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <select
            value={zoneFilter}
            onChange={(e) => setZoneFilter(e.target.value)}
            aria-label="Filter by Zone"
            className="px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-xs text-slate-300 focus:outline-none focus:border-indigo-500"
          >
            <option value="all">All Zones</option>
            {ZONES.map((z) => (
              <option key={z} value={z}>
                Zone {z} ({ZONE_COORDINATES[z]?.name})
              </option>
            ))}
          </select>

          <select
            value={skillFilter}
            onChange={(e) => setSkillFilter(e.target.value)}
            aria-label="Filter by Skill"
            className="px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-xs text-slate-300 focus:outline-none focus:border-indigo-500"
          >
            <option value="all">All Skills</option>
            {STANDARD_SKILLS.map((s) => (
              <option key={s} value={s}>
                {s.replace('_', ' ').toUpperCase()}
              </option>
            ))}
          </select>

          <select
            value={overtimeFilter}
            onChange={(e) => setOvertimeFilter(e.target.value)}
            aria-label="Filter by Overtime"
            className="px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-xs text-slate-300 focus:outline-none focus:border-indigo-500"
          >
            <option value="all">All Overtime Policies</option>
            <option value="allowed">Overtime Authorized</option>
            <option value="prohibited">Overtime Prohibited</option>
          </select>

          {(searchTerm || zoneFilter !== 'all' || skillFilter !== 'all' || overtimeFilter !== 'all') && (
            <button
              onClick={() => {
                setSearchTerm('');
                setZoneFilter('all');
                setSkillFilter('all');
                setOvertimeFilter('all');
              }}
              className="text-xs text-indigo-400 hover:text-indigo-300 px-2 py-1 font-medium"
            >
              Reset
            </button>
          )}
        </div>
      </div>

      {/* Loading Skeleton */}
      {loading && !technicians.length && (
        <div className="space-y-3 animate-pulse" data-testid="technicians-skeleton">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <div key={i} className="h-16 bg-slate-900/80 rounded-xl border border-slate-800" />
          ))}
        </div>
      )}

      {/* Technicians Table */}
      {!loading && (
        <div className="rounded-2xl bg-slate-900/70 border border-slate-800 shadow-md overflow-hidden">
          {filteredTechnicians.length === 0 ? (
            <div className="p-12 text-center text-slate-400">
              <Users className="w-10 h-10 text-slate-600 mx-auto mb-3" />
              <h3 className="text-sm font-semibold text-white">No technicians found</h3>
              <p className="text-xs text-slate-500 mt-1">
                Try adjusting your search criteria or active filters.
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs text-slate-300">
                <thead className="bg-slate-950/70 text-slate-400 font-semibold uppercase tracking-wider border-b border-slate-800">
                  <tr>
                    <th className="py-3 px-4">ID</th>
                    <th className="py-3 px-4">Name &amp; Base</th>
                    <th className="py-3 px-4">Eligible Zones</th>
                    <th className="py-3 px-4">Certified Skills</th>
                    <th className="py-3 px-4">Equipment Kit</th>
                    <th className="py-3 px-4">Working Shifts</th>
                    <th className="py-3 px-4">Overtime</th>
                    <th className="py-3 px-4 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60 font-normal">
                  {filteredTechnicians.map((tech) => (
                    <tr
                      key={tech.id}
                      className="hover:bg-slate-800/40 transition cursor-pointer"
                      onClick={() => setSelectedTechnician(tech)}
                    >
                      <td className="py-3 px-4 font-mono font-medium text-indigo-300">
                        {tech.id}
                      </td>
                      <td className="py-3 px-4">
                        <div className="font-semibold text-white">{tech.name}</div>
                        <div className="text-[11px] text-slate-400 flex items-center mt-0.5">
                          <MapPin className="w-3 h-3 text-slate-500 mr-1" />
                          <span>
                            {tech.home_zone_id || 'Base'} ({ZONE_COORDINATES[tech.home_zone_id || '']?.name || 'Local'})
                          </span>
                        </div>
                      </td>
                      <td className="py-3 px-4">
                        <div className="flex flex-wrap gap-1">
                          {tech.eligible_zones.map((z) => (
                            <span
                              key={z}
                              className="px-1.5 py-0.5 rounded bg-slate-800 border border-slate-700 text-[10px] font-mono text-slate-300"
                            >
                              {z}
                            </span>
                          ))}
                        </div>
                      </td>
                      <td className="py-3 px-4">
                        <div className="flex flex-wrap gap-1 max-w-[200px]">
                          {tech.skills.map((s) => (
                            <span
                              key={s}
                              className="px-1.5 py-0.5 rounded bg-indigo-950/70 border border-indigo-800/80 text-[10px] font-medium text-indigo-300"
                            >
                              {s}
                            </span>
                          ))}
                        </div>
                      </td>
                      <td className="py-3 px-4">
                        <div className="flex flex-wrap gap-1 max-w-[180px]">
                          {tech.equipment.map((eq) => (
                            <span
                              key={eq}
                              className="px-1.5 py-0.5 rounded bg-slate-800 text-[10px] text-slate-400"
                            >
                              {eq}
                            </span>
                          ))}
                        </div>
                      </td>
                      <td className="py-3 px-4">
                        <div className="text-slate-300">
                          {tech.shifts.length} Shifts Scheduled
                        </div>
                        <div className="text-[10px] text-slate-500 font-mono mt-0.5">
                          {tech.shifts[0]
                            ? `${formatTimeOnly(tech.shifts[0].start)} - ${formatTimeOnly(tech.shifts[0].end)}`
                            : 'Unscheduled'}
                        </div>
                      </td>
                      <td className="py-3 px-4">
                        {tech.overtime_allowed ? (
                          <span className="px-2 py-0.5 rounded border border-emerald-800/80 bg-emerald-950/60 text-[10px] font-semibold text-emerald-300 uppercase tracking-wider">
                            +{tech.max_overtime_minutes}m
                          </span>
                        ) : (
                          <span className="px-2 py-0.5 rounded border border-slate-800 bg-slate-900 text-[10px] font-semibold text-slate-500 uppercase tracking-wider">
                            None
                          </span>
                        )}
                      </td>
                      <td className="py-3 px-4 text-right">
                        <div
                          className="inline-flex items-center space-x-1"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <button
                            onClick={() => setSelectedTechnician(tech)}
                            className="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-[11px] text-slate-200 border border-slate-700 transition"
                            aria-label={`View Details for ${tech.id}`}
                          >
                            Details
                          </button>
                          <button
                            onClick={(e) => handleOpenEdit(tech, e)}
                            className="p-1.5 rounded bg-slate-800 hover:bg-indigo-900/60 text-slate-400 hover:text-indigo-300 border border-slate-700 transition"
                            title="Edit Technician"
                            aria-label={`Edit ${tech.id}`}
                          >
                            <Edit2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* TECHNICIAN DETAIL INSPECTION MODAL */}
      {selectedTechnician && (
        <div
          data-testid="technician-detail-modal"
          className="fixed inset-0 bg-black/75 backdrop-blur-sm z-50 flex items-center justify-center p-4 overflow-y-auto"
          onClick={() => setSelectedTechnician(null)}
        >
          <div
            className="bg-slate-900 border border-slate-800 rounded-2xl max-w-xl w-full p-6 text-left shadow-2xl relative max-h-[90vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between pb-4 border-b border-slate-800">
              <div>
                <div className="flex items-center space-x-2">
                  <span className="font-mono text-sm font-bold text-indigo-400">
                    {selectedTechnician.id}
                  </span>
                  <span className="px-2 py-0.5 rounded border border-indigo-800 bg-indigo-950 text-indigo-300 text-[10px] font-semibold uppercase tracking-wider">
                    {selectedTechnician.home_zone_id || 'Z1'} Base
                  </span>
                </div>
                <h3 className="text-lg font-bold text-white mt-1">{selectedTechnician.name}</h3>
                <p className="text-xs text-slate-400">
                  Base Depot Coordinates: {selectedTechnician.home_lat.toFixed(4)},{' '}
                  {selectedTechnician.home_lng.toFixed(4)}
                </p>
              </div>
              <button
                onClick={() => setSelectedTechnician(null)}
                className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="py-4 space-y-4 text-xs">
              {/* Eligible Zones */}
              <div className="p-3 rounded-lg bg-slate-950 border border-slate-800">
                <span className="text-slate-500 block mb-1">Eligible Service Zones</span>
                <div className="flex flex-wrap gap-1.5 mt-1">
                  {selectedTechnician.eligible_zones.map((z) => (
                    <span
                      key={z}
                      className="px-2 py-1 rounded bg-slate-800 border border-slate-700 text-slate-200 font-mono text-xs"
                    >
                      {z} - {ZONE_COORDINATES[z]?.name || 'District'}
                    </span>
                  ))}
                </div>
              </div>

              {/* Certified Skills */}
              <div className="p-3 rounded-lg bg-slate-950 border border-slate-800">
                <span className="text-slate-500 block mb-1">Certified Skill Credentials</span>
                <div className="flex flex-wrap gap-1.5 mt-1">
                  {selectedTechnician.skills.map((s) => (
                    <span
                      key={s}
                      className="px-2 py-1 rounded bg-indigo-950 border border-indigo-800 text-indigo-300 font-medium"
                    >
                      {s}
                    </span>
                  ))}
                </div>
              </div>

              {/* Onboard Equipment */}
              <div className="p-3 rounded-lg bg-slate-950 border border-slate-800">
                <span className="text-slate-500 block mb-1">Onboard Equipment &amp; Tooling</span>
                <div className="flex flex-wrap gap-1.5 mt-1">
                  {selectedTechnician.equipment.map((eq) => (
                    <span
                      key={eq}
                      className="px-2 py-0.5 rounded bg-slate-800 border border-slate-700 text-slate-300"
                    >
                      {eq}
                    </span>
                  ))}
                </div>
              </div>

              {/* Shifts Schedule */}
              <div className="p-3 rounded-lg bg-slate-950 border border-slate-800">
                <div className="flex items-center space-x-1.5 text-slate-400 mb-2">
                  <Calendar className="w-4 h-4 text-indigo-400" />
                  <span className="font-medium text-slate-300">Working Shifts Schedule</span>
                </div>
                {selectedTechnician.shifts.length === 0 ? (
                  <span className="text-slate-500 italic">No shifts assigned.</span>
                ) : (
                  <div className="space-y-1.5">
                    {selectedTechnician.shifts.map((s, idx) => (
                      <div
                        key={idx}
                        className="flex items-center justify-between p-2 rounded bg-slate-900 border border-slate-800 text-[11px]"
                      >
                        <div className="font-mono text-white font-semibold">{s.date}</div>
                        <div className="font-mono text-slate-400">
                          {formatTimeOnly(s.start)} &ndash; {formatTimeOnly(s.end)}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Unavailable Periods */}
              <div className="p-3 rounded-lg bg-slate-950 border border-slate-800">
                <div className="flex items-center space-x-1.5 text-slate-400 mb-2">
                  <AlertTriangle className="w-4 h-4 text-amber-400" />
                  <span className="font-medium text-slate-300">Pre-Scheduled Unavailabilities</span>
                </div>
                {selectedTechnician.unavailable_periods.length === 0 ? (
                  <span className="text-slate-500 italic">No unavailable intervals recorded.</span>
                ) : (
                  <div className="space-y-1.5">
                    {selectedTechnician.unavailable_periods.map((u, idx) => (
                      <div
                        key={idx}
                        className="flex items-center justify-between p-2 rounded bg-rose-950/30 border border-rose-900/50 text-[11px]"
                      >
                        <div>
                          <span className="font-medium text-rose-300 capitalize">
                            {u.reason || 'Unavailable'}
                          </span>
                        </div>
                        <div className="font-mono text-slate-400">
                          {formatTimeOnly(u.start)} &ndash; {formatTimeOnly(u.end)}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Overtime Policy */}
              <div className="p-3 rounded-lg bg-slate-950 border border-slate-800 flex items-center justify-between">
                <div>
                  <span className="text-slate-500 block">Overtime Policy</span>
                  <span className="font-semibold text-white">
                    {selectedTechnician.overtime_allowed ? 'Authorized' : 'Prohibited'}
                  </span>
                </div>
                {selectedTechnician.overtime_allowed && (
                  <div className="text-right">
                    <span className="text-slate-500 block">Max Per Shift</span>
                    <span className="font-mono text-emerald-400 font-bold">
                      +{selectedTechnician.max_overtime_minutes} minutes
                    </span>
                  </div>
                )}
              </div>
            </div>

            <div className="pt-4 border-t border-slate-800 flex items-center justify-between">
              <button
                onClick={() => {
                  const tech = selectedTechnician;
                  setSelectedTechnician(null);
                  handleOpenEdit(tech);
                }}
                className="px-3.5 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-xs font-semibold text-white transition flex items-center space-x-1.5"
              >
                <Edit2 className="w-3.5 h-3.5" />
                <span>Edit Profile</span>
              </button>

              <button
                onClick={() => setSelectedTechnician(null)}
                className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-white transition"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* REGISTER TECHNICIAN MODAL */}
      {isCreateOpen && (
        <div
          data-testid="create-technician-modal"
          className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4 overflow-y-auto"
          onClick={() => setIsCreateOpen(false)}
        >
          <div
            className="bg-slate-900 border border-slate-800 rounded-2xl max-w-xl w-full p-6 text-left shadow-2xl relative max-h-[90vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between pb-4 border-b border-slate-800">
              <div>
                <h3 className="text-base font-bold text-white">Register Field Technician</h3>
                <p className="text-xs text-slate-400">
                  Enroll field resource with certified skills, equipment, and operating constraints.
                </p>
              </div>
              <button
                onClick={() => setIsCreateOpen(false)}
                className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {createError && (
              <div className="mt-4 p-3 rounded-lg bg-rose-950/60 border border-rose-800 text-rose-300 text-xs flex items-start space-x-2">
                <AlertCircle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
                <span>{createError}</span>
              </div>
            )}

            {createSuccess && (
              <div className="mt-4 p-3 rounded-lg bg-emerald-950/60 border border-emerald-800 text-emerald-300 text-xs flex items-center space-x-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                <span>{createSuccess}</span>
              </div>
            )}

            <form onSubmit={handleCreateSubmit} className="py-4 space-y-4 text-xs">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-400 mb-1">Technician Name *</label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. Ramesh Kumar"
                    value={createForm.name}
                    onChange={(e) => setCreateForm({ ...createForm, name: e.target.value })}
                    className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-white focus:outline-none focus:border-indigo-500"
                  />
                </div>
                <div>
                  <label className="block text-slate-400 mb-1">Custom ID (Optional)</label>
                  <input
                    type="text"
                    placeholder="e.g. T21 (Auto-generated if blank)"
                    value={createForm.id}
                    onChange={(e) => setCreateForm({ ...createForm, id: e.target.value })}
                    className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-white font-mono focus:outline-none focus:border-indigo-500"
                  />
                </div>
              </div>

              {/* Home Zone & Coordinates */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div>
                  <label className="block text-slate-400 mb-1">Home Zone</label>
                  <select
                    value={createForm.home_zone_id}
                    onChange={(e) => {
                      const z = e.target.value;
                      const coords = ZONE_COORDINATES[z] || { lat: 12.3052, lng: 76.6552 };
                      setCreateForm({
                        ...createForm,
                        home_zone_id: z,
                        home_lat: coords.lat,
                        home_lng: coords.lng,
                        eligible_zones: createForm.eligible_zones.includes(z)
                          ? createForm.eligible_zones
                          : [...createForm.eligible_zones, z],
                      });
                    }}
                    className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-white focus:outline-none focus:border-indigo-500"
                  >
                    {ZONES.map((z) => (
                      <option key={z} value={z}>
                        {z} ({ZONE_COORDINATES[z]?.name})
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-slate-400 mb-1">Base Latitude</label>
                  <input
                    type="number"
                    step="any"
                    required
                    value={createForm.home_lat}
                    onChange={(e) =>
                      setCreateForm({ ...createForm, home_lat: parseFloat(e.target.value) || 0 })
                    }
                    className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-white font-mono focus:outline-none focus:border-indigo-500"
                  />
                </div>
                <div>
                  <label className="block text-slate-400 mb-1">Base Longitude</label>
                  <input
                    type="number"
                    step="any"
                    required
                    value={createForm.home_lng}
                    onChange={(e) =>
                      setCreateForm({ ...createForm, home_lng: parseFloat(e.target.value) || 0 })
                    }
                    className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-white font-mono focus:outline-none focus:border-indigo-500"
                  />
                </div>
              </div>

              {/* Eligible Zones Selection */}
              <div>
                <label className="block text-slate-400 mb-1">Eligible Zones</label>
                <div className="flex flex-wrap gap-2">
                  {ZONES.map((z) => {
                    const checked = createForm.eligible_zones.includes(z);
                    return (
                      <button
                        type="button"
                        key={z}
                        onClick={() => {
                          const newZones = checked
                            ? createForm.eligible_zones.filter((item) => item !== z)
                            : [...createForm.eligible_zones, z];
                          setCreateForm({ ...createForm, eligible_zones: newZones });
                        }}
                        className={`px-2.5 py-1 rounded-lg border text-xs font-mono transition ${
                          checked
                            ? 'bg-indigo-600/30 border-indigo-500 text-indigo-300 font-bold'
                            : 'bg-slate-950 border-slate-800 text-slate-400'
                        }`}
                      >
                        {z}
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Certified Skills */}
              <div>
                <label className="block text-slate-400 mb-1">Certified Skills</label>
                <div className="flex flex-wrap gap-2">
                  {STANDARD_SKILLS.map((skill) => {
                    const selected = createForm.skills.includes(skill);
                    return (
                      <button
                        type="button"
                        key={skill}
                        onClick={() => {
                          const newSkills = selected
                            ? createForm.skills.filter((s) => s !== skill)
                            : [...createForm.skills, skill];
                          setCreateForm({ ...createForm, skills: newSkills });
                        }}
                        className={`px-2.5 py-1 rounded-lg border text-xs transition ${
                          selected
                            ? 'bg-indigo-600 border-indigo-400 text-white font-medium'
                            : 'bg-slate-950 border-slate-800 text-slate-400'
                        }`}
                      >
                        {skill}
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Onboard Equipment */}
              <div>
                <label className="block text-slate-400 mb-1">Onboard Equipment</label>
                <div className="flex flex-wrap gap-2">
                  {STANDARD_EQUIPMENT.map((eq) => {
                    const selected = createForm.equipment.includes(eq);
                    return (
                      <button
                        type="button"
                        key={eq}
                        onClick={() => {
                          const newEq = selected
                            ? createForm.equipment.filter((item) => item !== eq)
                            : [...createForm.equipment, eq];
                          setCreateForm({ ...createForm, equipment: newEq });
                        }}
                        className={`px-2.5 py-1 rounded-lg border text-xs transition ${
                          selected
                            ? 'bg-slate-700 border-slate-500 text-white'
                            : 'bg-slate-950 border-slate-800 text-slate-400'
                        }`}
                      >
                        {eq}
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Initial Shift Configuration */}
              <div className="p-3 rounded-lg bg-slate-950 border border-slate-800 space-y-2">
                <span className="text-slate-400 font-semibold block">Working Shift Configuration</span>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                  <div>
                    <label className="block text-slate-500 text-[10px]">Date</label>
                    <input
                      type="date"
                      required
                      value={createForm.shifts[0]?.date || '2026-11-02'}
                      onChange={(e) => {
                        const date = e.target.value;
                        setCreateForm({
                          ...createForm,
                          shifts: [
                            {
                              date,
                              start: `${date}T${createForm.shifts[0]?.start.slice(11) || '09:00'}`,
                              end: `${date}T${createForm.shifts[0]?.end.slice(11) || '18:00'}`,
                            },
                          ],
                        });
                      }}
                      className="w-full px-2 py-1.5 rounded bg-slate-900 border border-slate-800 text-white text-xs"
                    />
                  </div>
                  <div>
                    <label className="block text-slate-500 text-[10px]">Shift Start</label>
                    <input
                      type="datetime-local"
                      required
                      value={createForm.shifts[0]?.start || '2026-11-02T09:00'}
                      onChange={(e) =>
                        setCreateForm({
                          ...createForm,
                          shifts: [
                            {
                              ...createForm.shifts[0],
                              start: e.target.value,
                            },
                          ],
                        })
                      }
                      className="w-full px-2 py-1.5 rounded bg-slate-900 border border-slate-800 text-white text-xs"
                    />
                  </div>
                  <div>
                    <label className="block text-slate-500 text-[10px]">Shift End</label>
                    <input
                      type="datetime-local"
                      required
                      value={createForm.shifts[0]?.end || '2026-11-02T18:00'}
                      onChange={(e) =>
                        setCreateForm({
                          ...createForm,
                          shifts: [
                            {
                              ...createForm.shifts[0],
                              end: e.target.value,
                            },
                          ],
                        })
                      }
                      className="w-full px-2 py-1.5 rounded bg-slate-900 border border-slate-800 text-white text-xs"
                    />
                  </div>
                </div>
              </div>

              {/* Overtime Settings */}
              <div className="p-3 rounded-lg bg-slate-950 border border-slate-800 flex items-center justify-between">
                <label className="flex items-center space-x-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={createForm.overtime_allowed}
                    onChange={(e) =>
                      setCreateForm({ ...createForm, overtime_allowed: e.target.checked })
                    }
                    className="rounded border-slate-800 text-indigo-600 focus:ring-indigo-500 bg-slate-900"
                  />
                  <span className="text-white font-medium">Authorize Overtime</span>
                </label>
                {createForm.overtime_allowed && (
                  <div className="flex items-center space-x-2">
                    <span className="text-slate-400 text-xs">Max Extra:</span>
                    <input
                      type="number"
                      min="0"
                      max="240"
                      step="15"
                      value={createForm.max_overtime_minutes}
                      onChange={(e) =>
                        setCreateForm({
                          ...createForm,
                          max_overtime_minutes: parseInt(e.target.value) || 0,
                        })
                      }
                      className="w-20 px-2 py-1 rounded bg-slate-900 border border-slate-800 text-white text-xs text-right font-mono"
                    />
                    <span className="text-slate-400 text-xs">mins</span>
                  </div>
                )}
              </div>

              <div className="pt-4 border-t border-slate-800 flex justify-end space-x-3">
                <button
                  type="button"
                  onClick={() => setIsCreateOpen(false)}
                  className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-white transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  data-testid="submit-register-tech-btn"
                  aria-label="Confirm Registration"
                  disabled={createSubmitting}
                  className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-xs font-semibold text-white transition shadow-md shadow-indigo-600/30 disabled:opacity-50"
                >
                  {createSubmitting ? 'Registering...' : 'Register Technician'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* EDIT TECHNICIAN MODAL */}
      {editingTechnician && (
        <div
          data-testid="edit-technician-modal"
          className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4 overflow-y-auto"
          onClick={() => setEditingTechnician(null)}
        >
          <div
            className="bg-slate-900 border border-slate-800 rounded-2xl max-w-xl w-full p-6 text-left shadow-2xl relative max-h-[90vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between pb-4 border-b border-slate-800">
              <div>
                <h3 className="text-base font-bold text-white">
                  Edit Technician {editingTechnician.id}
                </h3>
                <p className="text-xs text-slate-400">
                  Update technician profile, credentials, and availability parameters.
                </p>
              </div>
              <button
                onClick={() => setEditingTechnician(null)}
                className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {editError && (
              <div className="mt-4 p-3 rounded-lg bg-rose-950/60 border border-rose-800 text-rose-300 text-xs flex items-start space-x-2">
                <AlertCircle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
                <span>{editError}</span>
              </div>
            )}

            <form onSubmit={handleEditSubmit} className="py-4 space-y-4 text-xs">
              <div>
                <label className="block text-slate-400 mb-1">Technician Name *</label>
                <input
                  type="text"
                  required
                  value={editForm.name}
                  onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                  className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-white focus:outline-none focus:border-indigo-500"
                />
              </div>

              {/* Base Zone & Coordinates */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div>
                  <label className="block text-slate-400 mb-1">Home Zone</label>
                  <select
                    value={editForm.home_zone_id}
                    onChange={(e) => {
                      const z = e.target.value;
                      const coords = ZONE_COORDINATES[z] || { lat: 12.3052, lng: 76.6552 };
                      setEditForm({
                        ...editForm,
                        home_zone_id: z,
                        home_lat: coords.lat,
                        home_lng: coords.lng,
                      });
                    }}
                    className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-white focus:outline-none focus:border-indigo-500"
                  >
                    {ZONES.map((z) => (
                      <option key={z} value={z}>
                        {z} ({ZONE_COORDINATES[z]?.name})
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-slate-400 mb-1">Base Latitude</label>
                  <input
                    type="number"
                    step="any"
                    required
                    value={editForm.home_lat}
                    onChange={(e) =>
                      setEditForm({ ...editForm, home_lat: parseFloat(e.target.value) || 0 })
                    }
                    className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-white font-mono focus:outline-none focus:border-indigo-500"
                  />
                </div>
                <div>
                  <label className="block text-slate-400 mb-1">Base Longitude</label>
                  <input
                    type="number"
                    step="any"
                    required
                    value={editForm.home_lng}
                    onChange={(e) =>
                      setEditForm({ ...editForm, home_lng: parseFloat(e.target.value) || 0 })
                    }
                    className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-white font-mono focus:outline-none focus:border-indigo-500"
                  />
                </div>
              </div>

              {/* Eligible Zones */}
              <div>
                <label className="block text-slate-400 mb-1">Eligible Zones</label>
                <div className="flex flex-wrap gap-2">
                  {ZONES.map((z) => {
                    const checked = editForm.eligible_zones.includes(z);
                    return (
                      <button
                        type="button"
                        key={z}
                        onClick={() => {
                          const newZones = checked
                            ? editForm.eligible_zones.filter((item) => item !== z)
                            : [...editForm.eligible_zones, z];
                          setEditForm({ ...editForm, eligible_zones: newZones });
                        }}
                        className={`px-2.5 py-1 rounded-lg border text-xs font-mono transition ${
                          checked
                            ? 'bg-indigo-600/30 border-indigo-500 text-indigo-300 font-bold'
                            : 'bg-slate-950 border-slate-800 text-slate-400'
                        }`}
                      >
                        {z}
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Skills */}
              <div>
                <label className="block text-slate-400 mb-1">Certified Skills</label>
                <div className="flex flex-wrap gap-2">
                  {STANDARD_SKILLS.map((skill) => {
                    const selected = editForm.skills.includes(skill);
                    return (
                      <button
                        type="button"
                        key={skill}
                        onClick={() => {
                          const newSkills = selected
                            ? editForm.skills.filter((s) => s !== skill)
                            : [...editForm.skills, skill];
                          setEditForm({ ...editForm, skills: newSkills });
                        }}
                        className={`px-2.5 py-1 rounded-lg border text-xs transition ${
                          selected
                            ? 'bg-indigo-600 border-indigo-400 text-white font-medium'
                            : 'bg-slate-950 border-slate-800 text-slate-400'
                        }`}
                      >
                        {skill}
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Equipment */}
              <div>
                <label className="block text-slate-400 mb-1">Onboard Equipment</label>
                <div className="flex flex-wrap gap-2">
                  {STANDARD_EQUIPMENT.map((eq) => {
                    const selected = editForm.equipment.includes(eq);
                    return (
                      <button
                        type="button"
                        key={eq}
                        onClick={() => {
                          const newEq = selected
                            ? editForm.equipment.filter((item) => item !== eq)
                            : [...editForm.equipment, eq];
                          setEditForm({ ...editForm, equipment: newEq });
                        }}
                        className={`px-2.5 py-1 rounded-lg border text-xs transition ${
                          selected
                            ? 'bg-slate-700 border-slate-500 text-white'
                            : 'bg-slate-950 border-slate-800 text-slate-400'
                        }`}
                      >
                        {eq}
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Overtime Settings */}
              <div className="p-3 rounded-lg bg-slate-950 border border-slate-800 flex items-center justify-between">
                <label className="flex items-center space-x-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={editForm.overtime_allowed}
                    onChange={(e) =>
                      setEditForm({ ...editForm, overtime_allowed: e.target.checked })
                    }
                    className="rounded border-slate-800 text-indigo-600 focus:ring-indigo-500 bg-slate-900"
                  />
                  <span className="text-white font-medium">Authorize Overtime</span>
                </label>
                {editForm.overtime_allowed && (
                  <div className="flex items-center space-x-2">
                    <span className="text-slate-400 text-xs">Max Extra:</span>
                    <input
                      type="number"
                      min="0"
                      max="240"
                      step="15"
                      value={editForm.max_overtime_minutes}
                      onChange={(e) =>
                        setEditForm({
                          ...editForm,
                          max_overtime_minutes: parseInt(e.target.value) || 0,
                        })
                      }
                      className="w-20 px-2 py-1 rounded bg-slate-900 border border-slate-800 text-white text-xs text-right font-mono"
                    />
                    <span className="text-slate-400 text-xs">mins</span>
                  </div>
                )}
              </div>

              <div className="pt-4 border-t border-slate-800 flex justify-end space-x-3">
                <button
                  type="button"
                  onClick={() => setEditingTechnician(null)}
                  className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-white transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={editSubmitting}
                  className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-xs font-semibold text-white transition shadow-md shadow-indigo-600/30 disabled:opacity-50"
                >
                  {editSubmitting ? 'Saving...' : 'Save Changes'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
