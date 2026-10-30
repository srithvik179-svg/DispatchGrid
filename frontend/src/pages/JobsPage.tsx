import React, { useEffect, useState, useMemo, useCallback } from 'react';
import { PageHeader } from '../components/common/PageHeader';
import {
  Briefcase,
  Plus,
  Search,
  RefreshCw,
  AlertCircle,
  X,
  MapPin,
  Clock,
  Wrench,
  CheckCircle2,
} from 'lucide-react';

interface Job {
  id: string;
  idempotency_key?: string | null;
  customer_name: string;
  title: string;
  zone_id: string | null;
  lat: number;
  lng: number;
  address: string;
  priority: number;
  priority_label: string;
  duration_minutes: number;
  required_skills: string[];
  required_equipment: string[];
  time_window_start: string;
  time_window_end: string;
  sla_deadline: string;
  status: string;
  assigned_technician_id: string | null;
  scheduled_start: string | null;
  scheduled_end: string | null;
  created_at: string;
  tags: string[];
}

const AVAILABLE_SKILLS = [
  'electrical',
  'plumbing',
  'hvac',
  'networking',
  'appliance_repair',
  'solar',
  'cctv',
  'elevator',
];

const AVAILABLE_EQUIPMENT = [
  'ladder',
  'multimeter',
  'fiber_splicer',
  'pipe_wrench',
  'appliance_toolkit',
  'hvac_gauge',
  'scissor_lift',
];

const ZONES = ['Z1', 'Z2', 'Z3', 'Z4', 'Z5', 'Z6'];

export const JobsPage: React.FC = () => {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // Filters & Search
  const [searchTerm, setSearchTerm] = useState<string>('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [priorityFilter, setPriorityFilter] = useState<string>('all');
  const [zoneFilter, setZoneFilter] = useState<string>('all');

  // Detail Modal State
  const [selectedJob, setSelectedJob] = useState<Job | null>(null);

  // Create Job Modal State
  const [isCreateOpen, setIsCreateOpen] = useState<boolean>(false);
  const [createSubmitting, setCreateSubmitting] = useState<boolean>(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [createSuccess, setCreateSuccess] = useState<string | null>(null);

  // Form State
  const [formData, setFormData] = useState({
    title: '',
    customer_name: '',
    priority: 3,
    zone_id: 'Z1',
    lat: 12.3052,
    lng: 76.6552,
    address: '',
    duration_minutes: 60,
    required_skills: ['electrical'],
    required_equipment: ['multimeter'],
    time_window_start: '2026-11-02T10:00',
    time_window_end: '2026-11-02T14:00',
    sla_deadline: '2026-11-02T14:00',
    idempotency_key: '',
  });

  const fetchJobs = useCallback(async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    else setLoading(true);

    try {
      const apiUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
      const res = await fetch(`${apiUrl}/api/v1/jobs?limit=200`);
      if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
      const data = await res.json();
      setJobs(Array.isArray(data) ? data : []);
      setError(null);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load jobs');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchJobs();
  }, [fetchJobs]);

  // Client-side search and filtering
  const filteredJobs = useMemo(() => {
    return jobs.filter((job) => {
      const matchesSearch =
        searchTerm === '' ||
        job.id.toLowerCase().includes(searchTerm.toLowerCase()) ||
        job.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
        job.customer_name.toLowerCase().includes(searchTerm.toLowerCase());

      const matchesStatus = statusFilter === 'all' || job.status === statusFilter;
      const matchesPriority =
        priorityFilter === 'all' || job.priority.toString() === priorityFilter;
      const matchesZone = zoneFilter === 'all' || job.zone_id === zoneFilter;

      return matchesSearch && matchesStatus && matchesPriority && matchesZone;
    });
  }, [jobs, searchTerm, statusFilter, priorityFilter, zoneFilter]);

  const handleCreateSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setCreateSubmitting(true);
    setCreateError(null);
    setCreateSuccess(null);

    // Client-side validation
    if (!formData.title.trim() || !formData.customer_name.trim()) {
      setCreateError('Title and Customer Name are required.');
      setCreateSubmitting(false);
      return;
    }

    if (formData.duration_minutes <= 0) {
      setCreateError('Duration must be greater than 0 minutes.');
      setCreateSubmitting(false);
      return;
    }

    if (formData.required_skills.length === 0) {
      setCreateError('Select at least one required skill.');
      setCreateSubmitting(false);
      return;
    }

    const startDt = new Date(formData.time_window_start);
    const endDt = new Date(formData.time_window_end);

    if (startDt >= endDt) {
      setCreateError('Time window start must be strictly earlier than time window end.');
      setCreateSubmitting(false);
      return;
    }

    const diffMins = (endDt.getTime() - startDt.getTime()) / (1000 * 60);
    if (diffMins < formData.duration_minutes) {
      setCreateError(
        `Time window (${diffMins} mins) is shorter than job duration (${formData.duration_minutes} mins).`
      );
      setCreateSubmitting(false);
      return;
    }

    try {
      const apiUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
      // ISO strings with timezone
      const payload = {
        title: formData.title.trim(),
        customer_name: formData.customer_name.trim(),
        priority: Number(formData.priority),
        zone_id: formData.zone_id,
        location: {
          lat: Number(formData.lat),
          lng: Number(formData.lng),
          address: formData.address.trim() || undefined,
        },
        duration_minutes: Number(formData.duration_minutes),
        required_skills: formData.required_skills,
        required_equipment: formData.required_equipment,
        time_window_start: `${formData.time_window_start}:00+05:30`,
        time_window_end: `${formData.time_window_end}:00+05:30`,
        sla_deadline: formData.sla_deadline
          ? `${formData.sla_deadline}:00+05:30`
          : undefined,
        idempotency_key: formData.idempotency_key.trim() || undefined,
      };

      const res = await fetch(`${apiUrl}/api/v1/jobs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      const resJson = await res.json();
      if (!res.ok) {
        throw new Error(resJson.detail || `Server returned HTTP ${res.status}`);
      }

      setCreateSuccess(`Job ${resJson.id} successfully created!`);
      // Refresh list
      await fetchJobs(true);
      // Reset form
      setFormData({
        title: '',
        customer_name: '',
        priority: 3,
        zone_id: 'Z1',
        lat: 12.3052,
        lng: 76.6552,
        address: '',
        duration_minutes: 60,
        required_skills: ['electrical'],
        required_equipment: ['multimeter'],
        time_window_start: '2026-11-02T10:00',
        time_window_end: '2026-11-02T14:00',
        sla_deadline: '2026-11-02T14:00',
        idempotency_key: '',
      });
      setTimeout(() => {
        setIsCreateOpen(false);
        setCreateSuccess(null);
      }, 1200);
    } catch (err: unknown) {
      setCreateError(err instanceof Error ? err.message : 'Failed to create job');
    } finally {
      setCreateSubmitting(false);
    }
  };

  const getPriorityBadgeClass = (priority: number) => {
    switch (priority) {
      case 1:
        return 'bg-rose-950/70 text-rose-300 border-rose-800';
      case 2:
        return 'bg-amber-950/70 text-amber-300 border-amber-800';
      case 3:
        return 'bg-indigo-950/70 text-indigo-300 border-indigo-800';
      default:
        return 'bg-slate-800 text-slate-300 border-slate-700';
    }
  };

  const getStatusBadgeClass = (status: string) => {
    switch (status) {
      case 'completed':
        return 'bg-emerald-950/70 text-emerald-300 border-emerald-800';
      case 'in_progress':
        return 'bg-blue-950/70 text-blue-300 border-blue-800';
      case 'cancelled':
        return 'bg-rose-950/70 text-rose-300 border-rose-800';
      case 'pending':
      default:
        return 'bg-amber-950/60 text-amber-300 border-amber-800/80';
    }
  };

  const formatDateTime = (dtStr: string) => {
    try {
      const dt = new Date(dtStr);
      return dt.toLocaleTimeString('en-US', {
        month: 'short',
        day: 'numeric',
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
        title="Jobs Management"
        description="Catalog, inspection, and creation of customer field service requests."
        badge={`${jobs.length} Active Records`}
        action={
          <div className="flex items-center space-x-3">
            <button
              onClick={() => fetchJobs(true)}
              disabled={refreshing || loading}
              className="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-300 hover:text-white transition"
              aria-label="Refresh jobs"
            >
              <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin text-indigo-400' : ''}`} />
            </button>

            <button
              onClick={() => setIsCreateOpen(true)}
              className="inline-flex items-center space-x-2 px-3.5 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold shadow-md shadow-indigo-600/30 transition"
              aria-label="New Job Request"
            >
              <Plus className="w-4 h-4" />
              <span>Create Job</span>
            </button>
          </div>
        }
      />

      {/* Global Error Banner */}
      {error && (
        <div className="p-4 rounded-xl bg-rose-950/50 border border-rose-800/80 text-rose-200 flex items-start space-x-3 text-sm">
          <AlertCircle className="w-5 h-5 text-rose-400 shrink-0 mt-0.5" />
          <div className="flex-1">
            <span className="font-semibold block">Failed to load jobs</span>
            <span className="text-xs text-rose-300">{error}</span>
          </div>
          <button
            onClick={() => fetchJobs(false)}
            className="px-3 py-1 rounded bg-rose-900/80 hover:bg-rose-800 text-xs font-medium text-white transition border border-rose-700"
          >
            Retry
          </button>
        </div>
      )}

      {/* Search and Filters Bar */}
      <div className="p-4 rounded-xl bg-slate-900/70 border border-slate-800 flex flex-col md:flex-row items-stretch md:items-center justify-between gap-4">
        {/* Search Input */}
        <div className="relative flex-1">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            placeholder="Search by job ID, title, or customer name..."
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

        {/* Filter Dropdowns */}
        <div className="flex flex-wrap items-center gap-2">
          {/* Status Filter */}
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            aria-label="Filter by Status"
            className="px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-xs text-slate-300 focus:outline-none focus:border-indigo-500"
          >
            <option value="all">All Statuses</option>
            <option value="pending">Pending</option>
            <option value="in_progress">In Progress</option>
            <option value="completed">Completed</option>
            <option value="cancelled">Cancelled</option>
          </select>

          {/* Priority Filter */}
          <select
            value={priorityFilter}
            onChange={(e) => setPriorityFilter(e.target.value)}
            aria-label="Filter by Priority"
            className="px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-xs text-slate-300 focus:outline-none focus:border-indigo-500"
          >
            <option value="all">All Priorities</option>
            <option value="1">P1 - Urgent</option>
            <option value="2">P2 - High</option>
            <option value="3">P3 - Medium</option>
            <option value="4">P4 - Low</option>
          </select>

          {/* Zone Filter */}
          <select
            value={zoneFilter}
            onChange={(e) => setZoneFilter(e.target.value)}
            aria-label="Filter by Zone"
            className="px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-xs text-slate-300 focus:outline-none focus:border-indigo-500"
          >
            <option value="all">All Zones</option>
            {ZONES.map((z) => (
              <option key={z} value={z}>
                Zone {z}
              </option>
            ))}
          </select>

          {(searchTerm || statusFilter !== 'all' || priorityFilter !== 'all' || zoneFilter !== 'all') && (
            <button
              onClick={() => {
                setSearchTerm('');
                setStatusFilter('all');
                setPriorityFilter('all');
                setZoneFilter('all');
              }}
              className="text-xs text-indigo-400 hover:text-indigo-300 px-2 py-1 font-medium"
            >
              Reset
            </button>
          )}
        </div>
      </div>

      {/* Loading Skeleton */}
      {loading && !jobs.length && (
        <div className="space-y-3 animate-pulse" data-testid="jobs-skeleton">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <div key={i} className="h-16 bg-slate-900/80 rounded-xl border border-slate-800" />
          ))}
        </div>
      )}

      {/* Jobs Table */}
      {!loading && (
        <div className="rounded-2xl bg-slate-900/70 border border-slate-800 shadow-md overflow-hidden">
          {filteredJobs.length === 0 ? (
            <div className="p-12 text-center text-slate-400">
              <Briefcase className="w-10 h-10 text-slate-600 mx-auto mb-3" />
              <h3 className="text-sm font-semibold text-white">No service jobs found</h3>
              <p className="text-xs text-slate-500 mt-1">
                Try adjusting your search query or active filter selections.
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs text-slate-300">
                <thead className="bg-slate-950/70 text-slate-400 font-semibold uppercase tracking-wider border-b border-slate-800">
                  <tr>
                    <th className="py-3 px-4">ID</th>
                    <th className="py-3 px-4">Title &amp; Customer</th>
                    <th className="py-3 px-4">Zone</th>
                    <th className="py-3 px-4">Priority</th>
                    <th className="py-3 px-4">Duration</th>
                    <th className="py-3 px-4">Time Window</th>
                    <th className="py-3 px-4">Status</th>
                    <th className="py-3 px-4">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60 font-normal">
                  {filteredJobs.map((job) => (
                    <tr
                      key={job.id}
                      className="hover:bg-slate-800/40 transition cursor-pointer"
                      onClick={() => setSelectedJob(job)}
                    >
                      <td className="py-3 px-4 font-mono font-medium text-indigo-300">
                        {job.id}
                      </td>
                      <td className="py-3 px-4">
                        <div className="font-semibold text-white">{job.title}</div>
                        <div className="text-[11px] text-slate-400">{job.customer_name}</div>
                      </td>
                      <td className="py-3 px-4">
                        <span className="px-2 py-0.5 rounded bg-slate-800 border border-slate-700 text-slate-300 font-mono">
                          {job.zone_id || 'None'}
                        </span>
                      </td>
                      <td className="py-3 px-4">
                        <span
                          className={`px-2 py-0.5 rounded border text-[10px] font-semibold uppercase tracking-wider ${getPriorityBadgeClass(
                            job.priority
                          )}`}
                        >
                          P{job.priority} &bull; {job.priority_label}
                        </span>
                      </td>
                      <td className="py-3 px-4 text-slate-400 font-mono">
                        {job.duration_minutes}m
                      </td>
                      <td className="py-3 px-4 text-slate-400 font-mono text-[11px]">
                        {formatDateTime(job.time_window_start)} &ndash; {formatDateTime(job.time_window_end)}
                      </td>
                      <td className="py-3 px-4">
                        <span
                          className={`px-2 py-0.5 rounded border text-[10px] font-semibold uppercase tracking-wider ${getStatusBadgeClass(
                            job.status
                          )}`}
                        >
                          {job.status}
                        </span>
                      </td>
                      <td className="py-3 px-4">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setSelectedJob(job);
                          }}
                          className="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-[11px] text-indigo-300 hover:text-white border border-slate-700 transition"
                        >
                          View Details
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* JOB DETAIL MODAL */}
      {selectedJob && (
        <div
          data-testid="job-detail-modal"
          className="fixed inset-0 bg-black/75 backdrop-blur-sm z-50 flex items-center justify-center p-4 overflow-y-auto"
          onClick={() => setSelectedJob(null)}
        >
          <div
            className="bg-slate-900 border border-slate-800 rounded-2xl max-w-xl w-full p-6 text-left shadow-2xl relative"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between pb-4 border-b border-slate-800">
              <div>
                <div className="flex items-center space-x-2">
                  <span className="font-mono text-sm font-bold text-indigo-400">
                    {selectedJob.id}
                  </span>
                  <span
                    className={`px-2 py-0.5 rounded border text-[10px] font-semibold uppercase tracking-wider ${getStatusBadgeClass(
                      selectedJob.status
                    )}`}
                  >
                    {selectedJob.status}
                  </span>
                </div>
                <h3 className="text-lg font-bold text-white mt-1">{selectedJob.title}</h3>
                <p className="text-xs text-slate-400">{selectedJob.customer_name}</p>
              </div>
              <button
                onClick={() => setSelectedJob(null)}
                className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="py-4 space-y-4 text-xs">
              <div className="grid grid-cols-2 gap-3">
                <div className="p-3 rounded-lg bg-slate-950 border border-slate-800">
                  <span className="text-slate-500 block mb-1">Priority</span>
                  <span
                    className={`px-2 py-0.5 rounded border text-[10px] font-semibold uppercase tracking-wider ${getPriorityBadgeClass(
                      selectedJob.priority
                    )}`}
                  >
                    P{selectedJob.priority} &bull; {selectedJob.priority_label}
                  </span>
                </div>
                <div className="p-3 rounded-lg bg-slate-950 border border-slate-800">
                  <span className="text-slate-500 block mb-1">Duration</span>
                  <span className="text-white font-mono font-medium">
                    {selectedJob.duration_minutes} minutes
                  </span>
                </div>
              </div>

              <div className="p-3 rounded-lg bg-slate-950 border border-slate-800">
                <div className="flex items-center space-x-1.5 text-slate-400 mb-1">
                  <MapPin className="w-3.5 h-3.5 text-indigo-400" />
                  <span className="font-medium text-slate-300">Location &amp; Zone</span>
                </div>
                <div className="text-slate-300">{selectedJob.address}</div>
                <div className="text-slate-500 font-mono text-[11px] mt-1">
                  Zone: {selectedJob.zone_id || 'Auto-resolved'} &bull; Lat: {selectedJob.lat.toFixed(4)}, Lng: {selectedJob.lng.toFixed(4)}
                </div>
              </div>

              <div className="p-3 rounded-lg bg-slate-950 border border-slate-800">
                <div className="flex items-center space-x-1.5 text-slate-400 mb-1">
                  <Clock className="w-3.5 h-3.5 text-amber-400" />
                  <span className="font-medium text-slate-300">Operational Timing Constraints</span>
                </div>
                <div className="grid grid-cols-2 gap-2 mt-2">
                  <div>
                    <span className="text-slate-500 block">Time Window (Hard)</span>
                    <span className="text-slate-200 font-mono">
                      {formatDateTime(selectedJob.time_window_start)} &ndash; {formatDateTime(selectedJob.time_window_end)}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-500 block">SLA Deadline (Soft)</span>
                    <span className="text-slate-200 font-mono">
                      {formatDateTime(selectedJob.sla_deadline)}
                    </span>
                  </div>
                </div>
              </div>

              <div className="p-3 rounded-lg bg-slate-950 border border-slate-800">
                <div className="flex items-center space-x-1.5 text-slate-400 mb-2">
                  <Wrench className="w-3.5 h-3.5 text-emerald-400" />
                  <span className="font-medium text-slate-300">Prerequisites</span>
                </div>
                <div className="space-y-1.5">
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <span className="text-slate-500 text-[11px]">Skills:</span>
                    {selectedJob.required_skills.map((s) => (
                      <span
                        key={s}
                        className="px-1.5 py-0.5 rounded bg-indigo-950/70 text-indigo-300 border border-indigo-800 text-[10px]"
                      >
                        {s}
                      </span>
                    ))}
                  </div>
                  {selectedJob.required_equipment.length > 0 && (
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <span className="text-slate-500 text-[11px]">Equipment:</span>
                      {selectedJob.required_equipment.map((eq) => (
                        <span
                          key={eq}
                          className="px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 text-[10px]"
                        >
                          {eq}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              <div className="p-3 rounded-lg bg-slate-950 border border-slate-800 flex items-center justify-between">
                <div>
                  <span className="text-slate-500 block">Assigned Technician</span>
                  <span className="text-slate-200 font-medium">
                    {selectedJob.assigned_technician_id ? (
                      <span className="text-emerald-400 font-mono font-semibold">
                        {selectedJob.assigned_technician_id}
                      </span>
                    ) : (
                      <span className="text-slate-500 italic">Unassigned (Pending Dispatch)</span>
                    )}
                  </span>
                </div>
                {selectedJob.tags.length > 0 && (
                  <div className="text-right">
                    <span className="text-slate-500 block">Tags</span>
                    <span className="text-slate-400 font-mono text-[10px]">
                      {selectedJob.tags.join(', ')}
                    </span>
                  </div>
                )}
              </div>
            </div>

            <div className="pt-3 border-t border-slate-800 flex justify-end">
              <button
                onClick={() => setSelectedJob(null)}
                className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-white transition"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* CREATE JOB MODAL */}
      {isCreateOpen && (
        <div
          data-testid="create-job-modal"
          className="fixed inset-0 bg-black/75 backdrop-blur-sm z-50 flex items-center justify-center p-4 overflow-y-auto"
          onClick={() => setIsCreateOpen(false)}
        >
          <div
            className="bg-slate-900 border border-slate-800 rounded-2xl max-w-xl w-full p-6 text-left shadow-2xl relative max-h-[90vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between pb-4 border-b border-slate-800">
              <div>
                <h3 className="text-base font-bold text-white">Create New Service Job</h3>
                <p className="text-xs text-slate-400">
                  Register a customer service request with operational constraints.
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
                  <label className="block text-slate-400 mb-1">Job Title *</label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. Elevator motor inspection"
                    value={formData.title}
                    onChange={(e) => setFormData({ ...formData, title: e.target.value })}
                    className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-white focus:outline-none focus:border-indigo-500"
                  />
                </div>
                <div>
                  <label className="block text-slate-400 mb-1">Customer Name *</label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. Skyline Towers"
                    value={formData.customer_name}
                    onChange={(e) => setFormData({ ...formData, customer_name: e.target.value })}
                    className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-white focus:outline-none focus:border-indigo-500"
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div>
                  <label className="block text-slate-400 mb-1">Priority *</label>
                  <select
                    value={formData.priority}
                    onChange={(e) => setFormData({ ...formData, priority: Number(e.target.value) })}
                    className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-white focus:outline-none focus:border-indigo-500"
                  >
                    <option value={1}>1 - Urgent</option>
                    <option value={2}>2 - High</option>
                    <option value={3}>3 - Medium</option>
                    <option value={4}>4 - Low</option>
                  </select>
                </div>
                <div>
                  <label className="block text-slate-400 mb-1">Duration (Mins) *</label>
                  <input
                    type="number"
                    min={1}
                    required
                    value={formData.duration_minutes}
                    onChange={(e) => setFormData({ ...formData, duration_minutes: Number(e.target.value) })}
                    className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-white focus:outline-none focus:border-indigo-500"
                  />
                </div>
                <div>
                  <label className="block text-slate-400 mb-1">Zone *</label>
                  <select
                    value={formData.zone_id}
                    onChange={(e) => setFormData({ ...formData, zone_id: e.target.value })}
                    className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-white focus:outline-none focus:border-indigo-500"
                  >
                    {ZONES.map((z) => (
                      <option key={z} value={z}>
                        Zone {z}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-slate-400 mb-1">Address / Landmark</label>
                <input
                  type="text"
                  placeholder="Street address or building"
                  value={formData.address}
                  onChange={(e) => setFormData({ ...formData, address: e.target.value })}
                  className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-white focus:outline-none focus:border-indigo-500"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-400 mb-1">Latitude</label>
                  <input
                    type="number"
                    step="0.0001"
                    value={formData.lat}
                    onChange={(e) => setFormData({ ...formData, lat: Number(e.target.value) })}
                    className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-white focus:outline-none focus:border-indigo-500"
                  />
                </div>
                <div>
                  <label className="block text-slate-400 mb-1">Longitude</label>
                  <input
                    type="number"
                    step="0.0001"
                    value={formData.lng}
                    onChange={(e) => setFormData({ ...formData, lng: Number(e.target.value) })}
                    className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-white focus:outline-none focus:border-indigo-500"
                  />
                </div>
              </div>

              <div>
                <label className="block text-slate-400 mb-1">Required Skills *</label>
                <div className="flex flex-wrap gap-2 pt-1">
                  {AVAILABLE_SKILLS.map((skill) => {
                    const isSelected = formData.required_skills.includes(skill);
                    return (
                      <button
                        type="button"
                        key={skill}
                        onClick={() => {
                          if (isSelected) {
                            setFormData({
                              ...formData,
                              required_skills: formData.required_skills.filter((s) => s !== skill),
                            });
                          } else {
                            setFormData({
                              ...formData,
                              required_skills: [...formData.required_skills, skill],
                            });
                          }
                        }}
                        className={`px-2.5 py-1 rounded-md text-[11px] font-medium border transition ${
                          isSelected
                            ? 'bg-indigo-600 text-white border-indigo-500 shadow-sm'
                            : 'bg-slate-950 text-slate-400 border-slate-800 hover:text-white'
                        }`}
                      >
                        {skill}
                      </button>
                    );
                  })}
                </div>
              </div>

              <div>
                <label className="block text-slate-400 mb-1">Required Equipment</label>
                <div className="flex flex-wrap gap-2 pt-1">
                  {AVAILABLE_EQUIPMENT.map((eq) => {
                    const isSelected = formData.required_equipment.includes(eq);
                    return (
                      <button
                        type="button"
                        key={eq}
                        onClick={() => {
                          if (isSelected) {
                            setFormData({
                              ...formData,
                              required_equipment: formData.required_equipment.filter((item) => item !== eq),
                            });
                          } else {
                            setFormData({
                              ...formData,
                              required_equipment: [...formData.required_equipment, eq],
                            });
                          }
                        }}
                        className={`px-2 py-1 rounded-md text-[11px] font-medium border transition ${
                          isSelected
                            ? 'bg-emerald-600 text-white border-emerald-500 shadow-sm'
                            : 'bg-slate-950 text-slate-400 border-slate-800 hover:text-white'
                        }`}
                      >
                        {eq}
                      </button>
                    );
                  })}
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-400 mb-1">Window Start (Hard) *</label>
                  <input
                    type="datetime-local"
                    required
                    value={formData.time_window_start}
                    onChange={(e) => setFormData({ ...formData, time_window_start: e.target.value })}
                    className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-white focus:outline-none focus:border-indigo-500"
                  />
                </div>
                <div>
                  <label className="block text-slate-400 mb-1">Window End (Hard) *</label>
                  <input
                    type="datetime-local"
                    required
                    value={formData.time_window_end}
                    onChange={(e) => setFormData({ ...formData, time_window_end: e.target.value })}
                    className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-white focus:outline-none focus:border-indigo-500"
                  />
                </div>
              </div>

              <div className="pt-2 border-t border-slate-800 flex justify-end space-x-3">
                <button
                  type="button"
                  onClick={() => setIsCreateOpen(false)}
                  className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-white transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={createSubmitting}
                  className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-xs font-semibold text-white transition shadow-md shadow-indigo-600/30 disabled:opacity-50"
                >
                  {createSubmitting ? 'Creating...' : 'Submit Job Request'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
