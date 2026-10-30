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
  Edit2,
  Trash2,
  History,
  AlertTriangle,
  Lock,
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

interface StateHistoryItem {
  id: number;
  job_id: string;
  from_status: string | null;
  to_status: string;
  reason: string | null;
  changed_at: string;
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

  // Modals State
  const [selectedJob, setSelectedJob] = useState<Job | null>(null);
  const [historyList, setHistoryList] = useState<StateHistoryItem[]>([]);
  const [loadingHistory, setLoadingHistory] = useState<boolean>(false);

  // Create Modal
  const [isCreateOpen, setIsCreateOpen] = useState<boolean>(false);
  const [createSubmitting, setCreateSubmitting] = useState<boolean>(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [createSuccess, setCreateSuccess] = useState<string | null>(null);

  // Edit Modal
  const [editingJob, setEditingJob] = useState<Job | null>(null);
  const [editSubmitting, setEditSubmitting] = useState<boolean>(false);
  const [editError, setEditError] = useState<string | null>(null);

  // Cancel Confirmation Modal
  const [cancellingJob, setCancellingJob] = useState<Job | null>(null);
  const [cancelReason, setCancelReason] = useState<string>('Customer request');
  const [cancelSubmitting, setCancelSubmitting] = useState<boolean>(false);
  const [cancelError, setCancelError] = useState<string | null>(null);

  // Forms State
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

  const [editFormData, setEditFormData] = useState({
    title: '',
    customer_name: '',
    priority: 3,
    zone_id: 'Z1',
    duration_minutes: 60,
    required_skills: ['electrical'],
    required_equipment: ['multimeter'],
    reason: '',
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

  const loadJobHistory = async (jobId: string) => {
    setLoadingHistory(true);
    try {
      const apiUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
      const res = await fetch(`${apiUrl}/api/v1/jobs/${jobId}/history`);
      if (res.ok) {
        const data = await res.json();
        setHistoryList(data);
      }
    } catch {
      setHistoryList([]);
    } finally {
      setLoadingHistory(false);
    }
  };

  const handleSelectJob = (job: Job) => {
    setSelectedJob(job);
    loadJobHistory(job.id);
  };

  const handleOpenEdit = (job: Job, e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    if (job.status === 'completed' || job.status === 'cancelled') return;
    setEditingJob(job);
    setEditError(null);
    setEditFormData({
      title: job.title,
      customer_name: job.customer_name,
      priority: job.priority,
      zone_id: job.zone_id || 'Z1',
      duration_minutes: job.duration_minutes,
      required_skills: job.required_skills || [],
      required_equipment: job.required_equipment || [],
      reason: 'Dispatcher manual revision',
    });
  };

  const handleOpenCancel = (job: Job, e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    if (job.status === 'completed' || job.status === 'cancelled') return;
    setCancellingJob(job);
    setCancelError(null);
    setCancelReason('Customer requested cancellation');
  };

  const handleCancelSubmit = async () => {
    if (!cancellingJob) return;
    setCancelSubmitting(true);
    setCancelError(null);

    try {
      const apiUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
      const res = await fetch(`${apiUrl}/api/v1/jobs/${cancellingJob.id}/cancel`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason: cancelReason }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || `HTTP ${res.status}`);
      }

      await fetchJobs(true);
      if (selectedJob && selectedJob.id === cancellingJob.id) {
        setSelectedJob(data);
        loadJobHistory(data.id);
      }
      setCancellingJob(null);
    } catch (err: unknown) {
      setCancelError(err instanceof Error ? err.message : 'Cancellation failed');
    } finally {
      setCancelSubmitting(false);
    }
  };

  const handleEditSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingJob) return;
    setEditSubmitting(true);
    setEditError(null);

    if (!editFormData.title.trim() || !editFormData.customer_name.trim()) {
      setEditError('Title and Customer Name cannot be empty');
      setEditSubmitting(false);
      return;
    }

    try {
      const apiUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
      const payload = {
        title: editFormData.title.trim(),
        customer_name: editFormData.customer_name.trim(),
        priority: Number(editFormData.priority),
        zone_id: editFormData.zone_id,
        duration_minutes: Number(editFormData.duration_minutes),
        required_skills: editFormData.required_skills,
        required_equipment: editFormData.required_equipment,
        reason: editFormData.reason.trim() || 'Dispatcher manual update',
      };

      const res = await clientPatch(`${apiUrl}/api/v1/jobs/${editingJob.id}`, payload);
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || `HTTP ${res.status}`);
      }

      await fetchJobs(true);
      if (selectedJob && selectedJob.id === editingJob.id) {
        setSelectedJob(data);
        loadJobHistory(data.id);
      }
      setEditingJob(null);
    } catch (err: unknown) {
      setEditError(err instanceof Error ? err.message : 'Update failed');
    } finally {
      setEditSubmitting(false);
    }
  };

  const clientPatch = (url: string, body: any) =>
    fetch(url, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });

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
      await fetchJobs(true);
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
        return 'bg-rose-950/70 text-rose-300 border-rose-800 line-through';
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
        description="Catalog, inspection, and creation of customer field service requests, with full lifecycle management."
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

        <div className="flex flex-wrap items-center gap-2">
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            aria-label="Filter by Status"
            className="px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-xs text-slate-300 focus:outline-none focus:border-indigo-500"
          >
            <option value="all">All Statuses</option>
            <option value="pending">Pending</option>
            <option value="assigned">Assigned</option>
            <option value="in_progress">In Progress</option>
            <option value="completed">Completed</option>
            <option value="cancelled">Cancelled</option>
          </select>

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
                    <th className="py-3 px-4 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60 font-normal">
                  {filteredJobs.map((job) => {
                    const isTerminal = job.status === 'completed' || job.status === 'cancelled';
                    return (
                      <tr
                        key={job.id}
                        className="hover:bg-slate-800/40 transition cursor-pointer"
                        onClick={() => handleSelectJob(job)}
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
                        <td className="py-3 px-4 text-right">
                          <div
                            className="inline-flex items-center space-x-1"
                            onClick={(e) => e.stopPropagation()}
                          >
                            <button
                              onClick={() => handleSelectJob(job)}
                              className="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-[11px] text-slate-200 border border-slate-700 transition"
                              aria-label={`View Details for ${job.id}`}
                            >
                              Details
                            </button>

                            {!isTerminal ? (
                              <>
                                <button
                                  onClick={(e) => handleOpenEdit(job, e)}
                                  className="p-1.5 rounded bg-slate-800 hover:bg-indigo-900/60 text-slate-400 hover:text-indigo-300 border border-slate-700 transition"
                                  title="Edit Job"
                                  aria-label={`Edit ${job.id}`}
                                >
                                  <Edit2 className="w-3.5 h-3.5" />
                                </button>
                                <button
                                  onClick={(e) => handleOpenCancel(job, e)}
                                  className="p-1.5 rounded bg-slate-800 hover:bg-rose-900/60 text-slate-400 hover:text-rose-300 border border-slate-700 transition"
                                  title="Cancel Job"
                                  aria-label={`Cancel ${job.id}`}
                                >
                                  <Trash2 className="w-3.5 h-3.5" />
                                </button>
                              </>
                            ) : (
                              <span
                                className="p-1.5 text-slate-600 cursor-not-allowed"
                                title="Completed/Cancelled jobs are protected"
                              >
                                <Lock className="w-3.5 h-3.5" />
                              </span>
                            )}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* JOB DETAIL & HISTORY MODAL */}
      {selectedJob && (
        <div
          data-testid="job-detail-modal"
          className="fixed inset-0 bg-black/75 backdrop-blur-sm z-50 flex items-center justify-center p-4 overflow-y-auto"
          onClick={() => setSelectedJob(null)}
        >
          <div
            className="bg-slate-900 border border-slate-800 rounded-2xl max-w-xl w-full p-6 text-left shadow-2xl relative max-h-[90vh] overflow-y-auto"
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

              {/* State History Audit Log */}
              <div className="p-3 rounded-lg bg-slate-950 border border-slate-800">
                <div className="flex items-center space-x-1.5 text-slate-400 mb-2">
                  <History className="w-3.5 h-3.5 text-indigo-400" />
                  <span className="font-medium text-slate-300">State Transition Audit Trail</span>
                </div>
                {loadingHistory ? (
                  <span className="text-slate-500">Loading audit history...</span>
                ) : historyList.length === 0 ? (
                  <span className="text-slate-500 italic">No transition events recorded yet.</span>
                ) : (
                  <div className="space-y-2">
                    {historyList.map((h) => (
                      <div
                        key={h.id}
                        className="flex items-start justify-between pb-1.5 border-b border-slate-900 last:border-0"
                      >
                        <div>
                          <div className="flex items-center space-x-2">
                            <span className="px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 font-mono text-[10px]">
                              {h.from_status || 'CREATED'}
                            </span>
                            <span className="text-slate-500">&rarr;</span>
                            <span className="px-1.5 py-0.5 rounded bg-indigo-950/80 text-indigo-300 border border-indigo-800 text-[10px] font-semibold">
                              {h.to_status}
                            </span>
                          </div>
                          {h.reason && (
                            <p className="text-[11px] text-slate-400 mt-1">{h.reason}</p>
                          )}
                        </div>
                        <span className="text-[10px] font-mono text-slate-500">
                          {formatDateTime(h.changed_at)}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>

            <div className="pt-4 border-t border-slate-800 flex items-center justify-between">
              <div>
                {selectedJob.status !== 'completed' && selectedJob.status !== 'cancelled' ? (
                  <div className="flex items-center space-x-2">
                    <button
                      onClick={() => handleOpenEdit(selectedJob)}
                      className="px-3 py-1.5 rounded-lg bg-indigo-950 text-indigo-300 hover:bg-indigo-900 border border-indigo-800 text-xs font-medium transition"
                    >
                      Edit Job
                    </button>
                    <button
                      onClick={() => handleOpenCancel(selectedJob)}
                      className="px-3 py-1.5 rounded-lg bg-rose-950 text-rose-300 hover:bg-rose-900 border border-rose-800 text-xs font-medium transition"
                    >
                      Cancel Job
                    </button>
                  </div>
                ) : (
                  <span className="text-[11px] text-slate-500 flex items-center">
                    <Lock className="w-3.5 h-3.5 mr-1" />
                    Protected ({selectedJob.status})
                  </span>
                )}
              </div>

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

      {/* CANCEL CONFIRMATION DIALOG */}
      {cancellingJob && (
        <div
          data-testid="cancel-confirm-modal"
          className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4"
          onClick={() => setCancellingJob(null)}
        >
          <div
            className="bg-slate-900 border border-rose-900/60 rounded-2xl max-w-md w-full p-6 text-left shadow-2xl relative"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start space-x-3">
              <div className="w-10 h-10 rounded-full bg-rose-950 border border-rose-800 flex items-center justify-center text-rose-400 shrink-0">
                <AlertTriangle className="w-5 h-5" />
              </div>
              <div>
                <h3 className="text-base font-bold text-white">
                  Cancel Job {cancellingJob.id}?
                </h3>
                <p className="text-xs text-slate-400 mt-1">
                  Are you sure you want to cancel &ldquo;{cancellingJob.title}&rdquo;? This action
                  is irreversible and will release any assigned technician.
                </p>
              </div>
            </div>

            {cancelError && (
              <div className="mt-3 p-2.5 rounded-lg bg-rose-950 border border-rose-800 text-rose-300 text-xs">
                {cancelError}
              </div>
            )}

            <div className="mt-4">
              <label className="block text-xs text-slate-400 mb-1">
                Cancellation Reason (Audited)
              </label>
              <input
                type="text"
                value={cancelReason}
                onChange={(e) => setCancelReason(e.target.value)}
                placeholder="e.g. Customer cancelled appointment"
                className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-xs text-white focus:outline-none focus:border-rose-500"
              />
            </div>

            <div className="mt-6 flex justify-end space-x-3">
              <button
                type="button"
                onClick={() => setCancellingJob(null)}
                className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-white transition"
              >
                Keep Job
              </button>
              <button
                type="button"
                disabled={cancelSubmitting}
                onClick={handleCancelSubmit}
                className="px-4 py-2 rounded-lg bg-rose-600 hover:bg-rose-500 text-xs font-semibold text-white transition shadow-md shadow-rose-600/30 disabled:opacity-50"
              >
                {cancelSubmitting ? 'Cancelling...' : 'Confirm Cancellation'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* EDIT JOB MODAL */}
      {editingJob && (
        <div
          data-testid="edit-job-modal"
          className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4 overflow-y-auto"
          onClick={() => setEditingJob(null)}
        >
          <div
            className="bg-slate-900 border border-slate-800 rounded-2xl max-w-xl w-full p-6 text-left shadow-2xl relative max-h-[90vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between pb-4 border-b border-slate-800">
              <div>
                <h3 className="text-base font-bold text-white">Edit Job {editingJob.id}</h3>
                <p className="text-xs text-slate-400">
                  Update service parameters while preserving constraints.
                </p>
              </div>
              <button
                onClick={() => setEditingJob(null)}
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
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-400 mb-1">Job Title *</label>
                  <input
                    type="text"
                    required
                    value={editFormData.title}
                    onChange={(e) => setEditFormData({ ...editFormData, title: e.target.value })}
                    className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-white focus:outline-none focus:border-indigo-500"
                  />
                </div>
                <div>
                  <label className="block text-slate-400 mb-1">Customer Name *</label>
                  <input
                    type="text"
                    required
                    value={editFormData.customer_name}
                    onChange={(e) => setEditFormData({ ...editFormData, customer_name: e.target.value })}
                    className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-white focus:outline-none focus:border-indigo-500"
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div>
                  <label className="block text-slate-400 mb-1">Priority *</label>
                  <select
                    value={editFormData.priority}
                    onChange={(e) => setEditFormData({ ...editFormData, priority: Number(e.target.value) })}
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
                    value={editFormData.duration_minutes}
                    onChange={(e) => setEditFormData({ ...editFormData, duration_minutes: Number(e.target.value) })}
                    className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-white focus:outline-none focus:border-indigo-500"
                  />
                </div>
                <div>
                  <label className="block text-slate-400 mb-1">Zone *</label>
                  <select
                    value={editFormData.zone_id}
                    onChange={(e) => setEditFormData({ ...editFormData, zone_id: e.target.value })}
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
                <label className="block text-slate-400 mb-1">Reason for Change (Audit)</label>
                <input
                  type="text"
                  value={editFormData.reason}
                  onChange={(e) => setEditFormData({ ...editFormData, reason: e.target.value })}
                  placeholder="e.g. Customer requested shorter duration"
                  className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-white focus:outline-none focus:border-indigo-500"
                />
              </div>

              <div className="pt-2 border-t border-slate-800 flex justify-end space-x-3">
                <button
                  type="button"
                  onClick={() => setEditingJob(null)}
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
