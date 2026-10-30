import React, { useEffect, useState, useCallback } from 'react';
import { PageHeader } from '../components/common/PageHeader';
import {
  Briefcase,
  Users,
  CheckCircle2,
  Clock,
  RefreshCw,
  AlertCircle,
  MapPin,
  Calendar,
  Sparkles,
} from 'lucide-react';

interface JobSummary {
  id: string;
  title: string;
  customer_name: string;
  zone_id: string | null;
  priority: number;
  priority_label: string;
  duration_minutes: number;
  status: string;
  required_skills: string[];
  time_window_start: string;
  time_window_end: string;
  sla_deadline: string;
  assigned_technician_id: string | null;
}

interface TechnicianSummary {
  id: string;
  name: string;
  home_zone_id: string | null;
  skills: string[];
  equipment: string[];
  eligible_zones: string[];
  shifts_count: number;
  overtime_allowed: boolean;
}

interface OverviewData {
  total_jobs: number;
  job_counts_by_status: {
    pending: number;
    completed: number;
    in_progress: number;
    cancelled: number;
    [key: string]: number;
  };
  job_counts_by_priority: Record<string, number>;
  total_technicians: number;
  total_assignments: number;
  total_zones: number;
  simulation_clock: string;
  jobs: JobSummary[];
  technicians: TechnicianSummary[];
}

export const OverviewPage: React.FC = () => {
  const [data, setData] = useState<OverviewData | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'jobs' | 'technicians'>('jobs');

  const fetchOverview = useCallback(async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    else setLoading(true);

    try {
      const apiUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
      const res = await fetch(`${apiUrl}/api/v1/overview`);
      if (!res.ok) {
        throw new Error(`Server returned HTTP ${res.status}: ${res.statusText}`);
      }
      const json = await res.json();
      setData(json);
      setError(null);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to fetch overview data');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchOverview();
  }, [fetchOverview]);

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
        return 'bg-blue-950/70 text-blue-300 border-blue-800 animate-pulse';
      case 'cancelled':
        return 'bg-rose-950/70 text-rose-300 border-rose-800';
      case 'pending':
      default:
        return 'bg-amber-950/60 text-amber-300 border-amber-800/80';
    }
  };

  return (
    <div className="space-y-6">
      {/* Page Header with live Refresh Action */}
      <PageHeader
        title="Overview"
        description="Real-time operational status and fleet summary derived from the database."
        badge="Live Database Integration"
        action={
          <button
            onClick={() => fetchOverview(true)}
            disabled={refreshing || loading}
            className="inline-flex items-center space-x-2 px-3.5 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-xs font-semibold text-slate-200 hover:text-white transition shadow-sm disabled:opacity-50"
            aria-label="Refresh data"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin text-indigo-400' : ''}`} />
            <span>{refreshing ? 'Refreshing...' : 'Refresh Data'}</span>
          </button>
        }
      />

      {/* Error State Banner */}
      {error && (
        <div className="p-4 rounded-xl bg-rose-950/50 border border-rose-800/80 text-rose-200 flex items-start space-x-3 text-sm">
          <AlertCircle className="w-5 h-5 text-rose-400 shrink-0 mt-0.5" />
          <div className="flex-1">
            <span className="font-semibold block">Failed to load overview data</span>
            <span className="text-xs text-rose-300">{error}</span>
          </div>
          <button
            onClick={() => fetchOverview(false)}
            className="px-3 py-1 rounded bg-rose-900/80 hover:bg-rose-800 text-xs font-medium text-white transition border border-rose-700"
          >
            Retry
          </button>
        </div>
      )}

      {/* Loading Skeleton */}
      {loading && !data && (
        <div className="space-y-6 animate-pulse" data-testid="loading-skeleton">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="h-28 bg-slate-900/80 rounded-xl border border-slate-800 p-4" />
            ))}
          </div>
          <div className="h-64 bg-slate-900/80 rounded-xl border border-slate-800 p-4" />
        </div>
      )}

      {/* Main Content when loaded */}
      {data && (
        <>
          {/* Key Metric Overview Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {/* Card 1: Total Jobs */}
            <div className="p-5 rounded-xl bg-slate-900/70 border border-slate-800 flex flex-col justify-between shadow-sm">
              <div className="flex items-center justify-between text-slate-400">
                <span className="text-xs font-semibold uppercase tracking-wider">Total Service Jobs</span>
                <div className="p-2 rounded-lg bg-indigo-950 text-indigo-400 border border-indigo-800/60">
                  <Briefcase className="w-4 h-4" />
                </div>
              </div>
              <div className="mt-2">
                <div className="text-3xl font-extrabold text-white font-mono tracking-tight">
                  {data.total_jobs}
                </div>
                <div className="flex items-center gap-1.5 mt-2 flex-wrap text-[11px]">
                  <span className="px-2 py-0.5 rounded bg-amber-950/60 text-amber-300 border border-amber-800/60 font-medium">
                    {data.job_counts_by_status.pending ?? 0} Pending
                  </span>
                  <span className="px-2 py-0.5 rounded bg-blue-950/60 text-blue-300 border border-blue-800/60 font-medium">
                    {data.job_counts_by_status.in_progress ?? 0} In Progress
                  </span>
                  <span className="px-2 py-0.5 rounded bg-emerald-950/60 text-emerald-300 border border-emerald-800/60 font-medium">
                    {data.job_counts_by_status.completed ?? 0} Done
                  </span>
                </div>
              </div>
            </div>

            {/* Card 2: Fleet Technicians */}
            <div className="p-5 rounded-xl bg-slate-900/70 border border-slate-800 flex flex-col justify-between shadow-sm">
              <div className="flex items-center justify-between text-slate-400">
                <span className="text-xs font-semibold uppercase tracking-wider">Field Fleet</span>
                <div className="p-2 rounded-lg bg-emerald-950 text-emerald-400 border border-emerald-800/60">
                  <Users className="w-4 h-4" />
                </div>
              </div>
              <div className="mt-2">
                <div className="text-3xl font-extrabold text-white font-mono tracking-tight">
                  {data.total_technicians}
                </div>
                <div className="text-xs text-slate-400 mt-2 flex items-center space-x-1">
                  <MapPin className="w-3.5 h-3.5 text-slate-500" />
                  <span>Deployed across {data.total_zones} service zones</span>
                </div>
              </div>
            </div>

            {/* Card 3: Active & Completed Assignments */}
            <div className="p-5 rounded-xl bg-slate-900/70 border border-slate-800 flex flex-col justify-between shadow-sm">
              <div className="flex items-center justify-between text-slate-400">
                <span className="text-xs font-semibold uppercase tracking-wider">Preserved Assignments</span>
                <div className="p-2 rounded-lg bg-blue-950 text-blue-400 border border-blue-800/60">
                  <CheckCircle2 className="w-4 h-4" />
                </div>
              </div>
              <div className="mt-2">
                <div className="text-3xl font-extrabold text-white font-mono tracking-tight">
                  {data.total_assignments}
                </div>
                <div className="text-xs text-slate-400 mt-2 flex items-center space-x-1">
                  <Sparkles className="w-3.5 h-3.5 text-indigo-400" />
                  <span>Authoritative seed assignments active</span>
                </div>
              </div>
            </div>

            {/* Card 4: Simulation Clock Reference */}
            <div className="p-5 rounded-xl bg-slate-900/70 border border-slate-800 flex flex-col justify-between shadow-sm">
              <div className="flex items-center justify-between text-slate-400">
                <span className="text-xs font-semibold uppercase tracking-wider">Simulation Clock</span>
                <div className="p-2 rounded-lg bg-amber-950 text-amber-400 border border-amber-800/60">
                  <Clock className="w-4 h-4" />
                </div>
              </div>
              <div className="mt-2">
                <div className="text-lg font-bold text-white font-mono tracking-tight truncate">
                  2026-11-02 10:00 IST
                </div>
                <div className="text-xs text-slate-400 mt-2 flex items-center space-x-1">
                  <Calendar className="w-3.5 h-3.5 text-slate-500" />
                  <span>Planning Horizon: 2–3 Nov 2026</span>
                </div>
              </div>
            </div>
          </div>

          {/* Interactive Preview Tables Section */}
          <div className="rounded-2xl bg-slate-900/70 border border-slate-800 shadow-md overflow-hidden">
            {/* Tab Navigation Controls */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800 bg-slate-900/90">
              <div className="flex items-center space-x-2">
                <button
                  onClick={() => setActiveTab('jobs')}
                  className={`px-4 py-2 rounded-lg text-xs font-semibold transition ${
                    activeTab === 'jobs'
                      ? 'bg-indigo-600 text-white shadow-sm shadow-indigo-600/30'
                      : 'text-slate-400 hover:text-white hover:bg-slate-800'
                  }`}
                >
                  Service Jobs ({data.total_jobs})
                </button>
                <button
                  onClick={() => setActiveTab('technicians')}
                  className={`px-4 py-2 rounded-lg text-xs font-semibold transition ${
                    activeTab === 'technicians'
                      ? 'bg-indigo-600 text-white shadow-sm shadow-indigo-600/30'
                      : 'text-slate-400 hover:text-white hover:bg-slate-800'
                  }`}
                >
                  Technicians Fleet ({data.total_technicians})
                </button>
              </div>

              <span className="text-xs text-slate-400 font-medium hidden sm:inline">
                Displaying authentic database records
              </span>
            </div>

            {/* TAB 1: Jobs Table View */}
            {activeTab === 'jobs' && (
              <div className="overflow-x-auto">
                {data.jobs.length === 0 ? (
                  <div className="p-8 text-center text-slate-500 text-sm">
                    No jobs currently found in the database.
                  </div>
                ) : (
                  <table className="w-full text-left text-xs text-slate-300">
                    <thead className="bg-slate-950/70 text-slate-400 font-semibold uppercase tracking-wider border-b border-slate-800">
                      <tr>
                        <th className="py-3 px-4">ID</th>
                        <th className="py-3 px-4">Job Title &amp; Customer</th>
                        <th className="py-3 px-4">Zone</th>
                        <th className="py-3 px-4">Priority</th>
                        <th className="py-3 px-4">Duration</th>
                        <th className="py-3 px-4">Time Window</th>
                        <th className="py-3 px-4">Status</th>
                        <th className="py-3 px-4">Technician</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/60 font-normal">
                      {data.jobs.map((job) => (
                        <tr key={job.id} className="hover:bg-slate-800/40 transition">
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
                          <td className="py-3 px-4 font-mono text-[11px] text-slate-300">
                            {job.assigned_technician_id ? (
                              <span className="text-emerald-400 font-semibold">
                                {job.assigned_technician_id}
                              </span>
                            ) : (
                              <span className="text-slate-500 italic">Unassigned</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            )}

            {/* TAB 2: Technicians Table View */}
            {activeTab === 'technicians' && (
              <div className="overflow-x-auto">
                {data.technicians.length === 0 ? (
                  <div className="p-8 text-center text-slate-500 text-sm">
                    No technicians found in the database.
                  </div>
                ) : (
                  <table className="w-full text-left text-xs text-slate-300">
                    <thead className="bg-slate-950/70 text-slate-400 font-semibold uppercase tracking-wider border-b border-slate-800">
                      <tr>
                        <th className="py-3 px-4">ID</th>
                        <th className="py-3 px-4">Technician Name</th>
                        <th className="py-3 px-4">Home Zone</th>
                        <th className="py-3 px-4">Eligible Zones</th>
                        <th className="py-3 px-4">Certified Skills</th>
                        <th className="py-3 px-4">Equipment Kit</th>
                        <th className="py-3 px-4">Shifts</th>
                        <th className="py-3 px-4">Overtime</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/60 font-normal">
                      {data.technicians.map((tech) => (
                        <tr key={tech.id} className="hover:bg-slate-800/40 transition">
                          <td className="py-3 px-4 font-mono font-medium text-emerald-400">
                            {tech.id}
                          </td>
                          <td className="py-3 px-4 font-semibold text-white">
                            {tech.name}
                          </td>
                          <td className="py-3 px-4">
                            <span className="px-2 py-0.5 rounded bg-slate-800 border border-slate-700 text-slate-300 font-mono">
                              {tech.home_zone_id || 'Z1'}
                            </span>
                          </td>
                          <td className="py-3 px-4">
                            <div className="flex gap-1 flex-wrap">
                              {tech.eligible_zones.map((z) => (
                                <span
                                  key={z}
                                  className="px-1.5 py-0.5 rounded bg-slate-800 text-[10px] text-slate-300 border border-slate-700 font-mono"
                                >
                                  {z}
                                </span>
                              ))}
                            </div>
                          </td>
                          <td className="py-3 px-4">
                            <div className="flex gap-1 flex-wrap max-w-xs">
                              {tech.skills.map((skill) => (
                                <span
                                  key={skill}
                                  className="px-1.5 py-0.5 rounded bg-indigo-950/70 text-indigo-300 border border-indigo-800 text-[10px] font-medium"
                                >
                                  {skill}
                                </span>
                              ))}
                            </div>
                          </td>
                          <td className="py-3 px-4">
                            <div className="flex gap-1 flex-wrap max-w-xs">
                              {tech.equipment.map((eq) => (
                                <span
                                  key={eq}
                                  className="px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 text-[10px]"
                                >
                                  {eq}
                                </span>
                              ))}
                            </div>
                          </td>
                          <td className="py-3 px-4 font-mono text-slate-300">
                            {tech.shifts_count} shifts
                          </td>
                          <td className="py-3 px-4">
                            {tech.overtime_allowed ? (
                              <span className="px-2 py-0.5 rounded bg-emerald-950/70 text-emerald-300 border border-emerald-800 text-[10px] font-medium">
                                Allowed
                              </span>
                            ) : (
                              <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-400 text-[10px] font-medium">
                                No
                              </span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
};
