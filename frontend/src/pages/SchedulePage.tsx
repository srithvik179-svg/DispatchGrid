import React, { useEffect, useState, useMemo, useCallback } from 'react';
import { PageHeader } from '../components/common/PageHeader';
import {
  Calendar,
  RotateCcw,
  RefreshCw,
  Search,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  User,
  Info,
  Navigation,
  ArrowRight,
  Sparkles,
  Layers,
  X,
} from 'lucide-react';

interface AssignmentItem {
  assignment_id: number | null;
  job_id: string;
  technician_id: string;
  technician_name: string | null;
  job_title: string | null;
  customer_name: string | null;
  zone_id: string | null;
  priority: number | null;
  priority_label: string | null;
  start_time: string;
  end_time: string;
  duration_minutes: number;
  travel_time_minutes: number;
  distance_km: number;
  status: string;
  is_existing: boolean;
}

interface UnassignedJobItem {
  job_id: string;
  title: string;
  customer_name: string;
  zone_id: string | null;
  priority: number;
  priority_label: string;
  duration_minutes: number;
  classification: 'currently_infeasible' | 'permanently_impossible';
  primary_category: string;
  rejection_summary: string;
  actionable_recommendation: string;
  required_skills: string[];
  required_equipment: string[];
}

interface ScheduleResponse {
  run_id?: string;
  as_of: string;
  total_jobs: number;
  assigned_count: number;
  unassigned_count: number;
  technicians_count: number;
  technicians_utilized: number;
  assignments: AssignmentItem[];
  unassigned_jobs: UnassignedJobItem[];
  metrics: Record<string, any>;
}

interface TechnicianItineraryItem {
  assignment_id: number | null;
  job_id: string;
  job_title: string;
  customer_name: string;
  zone_id: string | null;
  lat: number;
  lng: number;
  start_time: string;
  end_time: string;
  duration_minutes: number;
  travel_from_previous_minutes: number;
  distance_from_previous_km: number;
  status: string;
  is_existing: boolean;
}

interface TechnicianSchedule {
  technician_id: string;
  technician_name: string;
  home_zone_id: string | null;
  home_lat: number;
  home_lng: number;
  eligible_zones: string[];
  skills: string[];
  equipment: string[];
  total_assigned_jobs: number;
  total_working_minutes: number;
  total_travel_minutes: number;
  itinerary: TechnicianItineraryItem[];
}

interface FeasibilityModalData {
  job_id: string;
  classification: string;
  primary_category: string;
  rejection_summary: string;
  actionable_recommendation: string;
  technician_rejections: Array<{
    technician_id: string;
    technician_name: string | null;
    is_structurally_capable: boolean;
    rejection_category: string;
    rejection_code: string;
    missing_skills: string[];
    missing_equipment: string[];
    zone_certified: boolean;
    explanation: string;
  }>;
}

const ZONES = ['Z1', 'Z2', 'Z3', 'Z4', 'Z5', 'Z6'];

export const SchedulePage: React.FC = () => {
  const [scheduleData, setScheduleData] = useState<ScheduleResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [generating, setGenerating] = useState<boolean>(false);
  const [resetting, setResetting] = useState<boolean>(false);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [notification, setNotification] = useState<{ type: 'success' | 'error' | 'info'; message: string } | null>(null);

  // Active View Tab: 'assigned' | 'unassigned' | 'timeline'
  const [activeTab, setActiveTab] = useState<'assigned' | 'unassigned' | 'timeline'>('assigned');

  // Search & Filters
  const [searchTerm, setSearchTerm] = useState<string>('');
  const [zoneFilter, setZoneFilter] = useState<string>('all');
  const [priorityFilter, setPriorityFilter] = useState<string>('all');
  const [categoryFilter, setCategoryFilter] = useState<string>('all');

  // Technician Timeline View
  const [selectedTechId, setSelectedTechId] = useState<string>('T01');
  const [techSchedule, setTechSchedule] = useState<TechnicianSchedule | null>(null);
  const [loadingTechSchedule, setLoadingTechSchedule] = useState<boolean>(false);

  // Feasibility Inspection Modal
  const [feasibilityModal, setFeasibilityModal] = useState<FeasibilityModalData | null>(null);
  const [loadingFeasibility, setLoadingFeasibility] = useState<boolean>(false);

  // Auto-dismiss notification after 6 seconds
  useEffect(() => {
    if (notification) {
      const timer = setTimeout(() => setNotification(null), 6000);
      return () => clearTimeout(timer);
    }
  }, [notification]);

  // Load Current Schedule
  const loadSchedule = useCallback(async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    else setLoading(true);

    try {
      const resp = await fetch('/api/v1/schedule/current');
      if (!resp.ok) {
        throw new Error(`Failed to load schedule: ${resp.statusText}`);
      }
      const data: ScheduleResponse = await resp.json();
      setScheduleData(data);
    } catch (err: any) {
      setNotification({
        type: 'error',
        message: err.message || 'Error communicating with scheduling API',
      });
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadSchedule();
  }, [loadSchedule]);

  // Load specific technician schedule when in timeline tab
  const loadTechSchedule = useCallback(async (techId: string) => {
    setLoadingTechSchedule(true);
    try {
      const resp = await fetch(`/api/v1/technicians/${techId}/schedule`);
      if (!resp.ok) {
        throw new Error(`Failed to load technician schedule: ${resp.statusText}`);
      }
      const data: TechnicianSchedule = await resp.json();
      setTechSchedule(data);
    } catch (err: any) {
      setNotification({
        type: 'error',
        message: err.message || 'Error loading technician schedule',
      });
    } finally {
      setLoadingTechSchedule(false);
    }
  }, []);

  useEffect(() => {
    if (activeTab === 'timeline' && selectedTechId) {
      loadTechSchedule(selectedTechId);
    }
  }, [activeTab, selectedTechId, loadTechSchedule]);

  // Trigger Automatic Schedule Generation
  const handleGenerateSchedule = async () => {
    setGenerating(true);
    setNotification({
      type: 'info',
      message: 'Running deterministic scheduling engine across pending jobs...',
    });

    try {
      const resp = await fetch('/api/v1/schedule/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ persist: true, mode: 'baseline', respect_existing_assignments: true }),
      });

      if (!resp.ok) {
        const errorData = await resp.json().catch(() => ({}));
        throw new Error(errorData.detail || `Schedule generation failed (${resp.status})`);
      }

      const generated: ScheduleResponse = await resp.json();
      setScheduleData(generated);
      setNotification({
        type: 'success',
        message: `Schedule generated successfully: ${generated.assigned_count} jobs assigned (${generated.technicians_utilized} technicians utilized), ${generated.unassigned_count} unassigned.`,
      });

      // Refresh technician itinerary if timeline tab is active
      if (activeTab === 'timeline') {
        loadTechSchedule(selectedTechId);
      }
    } catch (err: any) {
      setNotification({
        type: 'error',
        message: err.message || 'An error occurred during schedule generation',
      });
    } finally {
      setGenerating(false);
    }
  };

  // Reset Schedule to Baseline
  const handleResetSchedule = async () => {
    if (!window.confirm('Reset schedule to baseline? This will clear all newly generated assignments while strictly preserving the 7 pre-existing assignments.')) {
      return;
    }

    setResetting(true);
    try {
      const resp = await fetch('/api/v1/schedule/reset', { method: 'POST' });
      if (!resp.ok) {
        throw new Error(`Reset failed (${resp.status})`);
      }
      const result = await resp.json();
      await loadSchedule();
      setNotification({
        type: 'success',
        message: `Schedule reset to baseline: ${result.deleted_assignments} assignments cleared, 7 pre-existing assignments preserved.`,
      });
      if (activeTab === 'timeline') {
        loadTechSchedule(selectedTechId);
      }
    } catch (err: any) {
      setNotification({
        type: 'error',
        message: err.message || 'An error occurred while resetting the schedule',
      });
    } finally {
      setResetting(false);
    }
  };

  // Inspect Feasibility Details Modal for an unassigned job
  const handleOpenFeasibility = async (jobId: string) => {
    setLoadingFeasibility(true);
    try {
      const resp = await fetch(`/api/v1/scheduling/feasibility/job/${jobId}`);
      if (!resp.ok) {
        throw new Error(`Could not fetch feasibility details (${resp.status})`);
      }
      const data: FeasibilityModalData = await resp.json();
      setFeasibilityModal(data);
    } catch (err: any) {
      setNotification({
        type: 'error',
        message: err.message || 'Error fetching feasibility diagnosis',
      });
    } finally {
      setLoadingFeasibility(false);
    }
  };

  // Filtered Assigned Jobs
  const filteredAssignments = useMemo(() => {
    if (!scheduleData) return [];
    return scheduleData.assignments.filter((item) => {
      // Search
      const term = searchTerm.toLowerCase();
      const matchesSearch =
        !term ||
        item.job_id.toLowerCase().includes(term) ||
        (item.job_title && item.job_title.toLowerCase().includes(term)) ||
        (item.customer_name && item.customer_name.toLowerCase().includes(term)) ||
        (item.technician_name && item.technician_name.toLowerCase().includes(term)) ||
        item.technician_id.toLowerCase().includes(term);

      // Zone
      const matchesZone = zoneFilter === 'all' || item.zone_id === zoneFilter;

      // Priority
      const matchesPriority =
        priorityFilter === 'all' ||
        (item.priority && String(item.priority) === priorityFilter);

      return matchesSearch && matchesZone && matchesPriority;
    });
  }, [scheduleData, searchTerm, zoneFilter, priorityFilter]);

  // Filtered Unassigned Jobs
  const filteredUnassigned = useMemo(() => {
    if (!scheduleData) return [];
    return scheduleData.unassigned_jobs.filter((item) => {
      // Search
      const term = searchTerm.toLowerCase();
      const matchesSearch =
        !term ||
        item.job_id.toLowerCase().includes(term) ||
        item.title.toLowerCase().includes(term) ||
        item.customer_name.toLowerCase().includes(term);

      // Zone
      const matchesZone = zoneFilter === 'all' || item.zone_id === zoneFilter;

      // Priority
      const matchesPriority =
        priorityFilter === 'all' || String(item.priority) === priorityFilter;

      // Category / Classification
      const matchesCategory =
        categoryFilter === 'all' ||
        item.classification === categoryFilter ||
        item.primary_category === categoryFilter;

      return matchesSearch && matchesZone && matchesPriority && matchesCategory;
    });
  }, [scheduleData, searchTerm, zoneFilter, priorityFilter, categoryFilter]);

  // Format Helper
  const formatTime = (isoString?: string) => {
    if (!isoString) return '--:--';
    try {
      const dt = new Date(isoString);
      return dt.toLocaleTimeString('en-US', {
        hour: '2-digit',
        minute: '2-digit',
        hour12: false,
      });
    } catch {
      return isoString;
    }
  };

  const formatDate = (isoString?: string) => {
    if (!isoString) return '';
    try {
      const dt = new Date(isoString);
      return dt.toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
      });
    } catch {
      return '';
    }
  };

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <PageHeader
        title="Workforce Schedule & Dispatch"
        description="Automated schedule generation, assignment routes, and unassigned feasibility diagnostics."
        badge="Module B – Phase 22"
        action={
          <div className="flex items-center space-x-2">
            <button
              onClick={() => loadSchedule(true)}
              disabled={loading || refreshing || generating}
              className="inline-flex items-center px-3 py-2 text-xs font-medium rounded-lg bg-slate-800 text-slate-300 hover:bg-slate-700 border border-slate-700 transition-colors disabled:opacity-50"
              title="Refresh Current Schedule"
            >
              <RefreshCw className={`w-3.5 h-3.5 mr-1.5 ${refreshing ? 'animate-spin' : ''}`} />
              Refresh
            </button>
            <button
              onClick={handleResetSchedule}
              disabled={loading || resetting || generating}
              className="inline-flex items-center px-3 py-2 text-xs font-medium rounded-lg bg-slate-800 text-amber-300 hover:bg-slate-700 border border-amber-900/40 transition-colors disabled:opacity-50"
              title="Reset newly created assignments back to baseline (preserves 7 seeded assignments)"
            >
              <RotateCcw className={`w-3.5 h-3.5 mr-1.5 ${resetting ? 'animate-spin' : ''}`} />
              Reset
            </button>
            <button
              onClick={handleGenerateSchedule}
              disabled={loading || generating || resetting}
              className="inline-flex items-center px-4 py-2 text-xs font-semibold rounded-lg bg-indigo-600 text-white hover:bg-indigo-500 shadow-sm shadow-indigo-600/30 transition-all disabled:opacity-50"
              data-testid="generate-schedule-btn"
            >
              {generating ? (
                <>
                  <RefreshCw className="w-3.5 h-3.5 mr-2 animate-spin" />
                  Generating Schedule...
                </>
              ) : (
                <>
                  <Sparkles className="w-3.5 h-3.5 mr-2 text-indigo-200" />
                  Generate Schedule
                </>
              )}
            </button>
          </div>
        }
      />

      {/* Notification Toast Banner */}
      {notification && (
        <div
          className={`flex items-start justify-between p-4 rounded-lg border text-sm transition-all ${
            notification.type === 'success'
              ? 'bg-emerald-950/70 border-emerald-700/80 text-emerald-200'
              : notification.type === 'error'
              ? 'bg-rose-950/70 border-rose-700/80 text-rose-200'
              : 'bg-indigo-950/70 border-indigo-700/80 text-indigo-200'
          }`}
          role="alert"
        >
          <div className="flex items-center space-x-2">
            {notification.type === 'success' && <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />}
            {notification.type === 'error' && <XCircle className="w-4 h-4 text-rose-400 shrink-0" />}
            {notification.type === 'info' && <Info className="w-4 h-4 text-indigo-400 shrink-0" />}
            <span className="font-medium">{notification.message}</span>
          </div>
          <button
            onClick={() => setNotification(null)}
            className="text-slate-400 hover:text-white ml-3"
            aria-label="Dismiss alert"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* KPI Stats Overview Bar */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <div className="bg-slate-900 border border-slate-800 rounded-lg p-3.5">
          <p className="text-xs text-slate-400 font-medium">Total Backlog</p>
          <p className="text-xl font-bold text-white mt-1">
            {scheduleData ? scheduleData.total_jobs : '--'}
          </p>
          <p className="text-[11px] text-slate-500 mt-0.5">108 Jobs in system</p>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-lg p-3.5">
          <p className="text-xs text-emerald-400 font-medium">Assigned Jobs</p>
          <p className="text-xl font-bold text-emerald-400 mt-1" data-testid="assigned-count">
            {scheduleData ? scheduleData.assigned_count : '--'}
          </p>
          <p className="text-[11px] text-slate-500 mt-0.5">
            {scheduleData?.metrics?.locked_existing_assignments ?? 7} locked existing
          </p>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-lg p-3.5">
          <p className="text-xs text-amber-400 font-medium">Unassigned Jobs</p>
          <p className="text-xl font-bold text-amber-400 mt-1" data-testid="unassigned-count">
            {scheduleData ? scheduleData.unassigned_count : '--'}
          </p>
          <p className="text-[11px] text-slate-500 mt-0.5">With diagnostic reasons</p>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-lg p-3.5">
          <p className="text-xs text-indigo-400 font-medium">Active Roster</p>
          <p className="text-xl font-bold text-indigo-300 mt-1">
            {scheduleData ? `${scheduleData.technicians_utilized} / ${scheduleData.technicians_count}` : '--'}
          </p>
          <p className="text-[11px] text-slate-500 mt-0.5">Technicians dispatched</p>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-lg p-3.5 col-span-2 md:col-span-1">
          <p className="text-xs text-slate-400 font-medium">Simulation Clock</p>
          <p className="text-sm font-semibold text-slate-200 mt-1">
            {scheduleData ? formatTime(scheduleData.as_of) : '--:--'}
          </p>
          <p className="text-[11px] text-slate-500 mt-0.5">
            {scheduleData ? formatDate(scheduleData.as_of) : 'Reference as_of'}
          </p>
        </div>
      </div>

      {/* Main Tabs Navigation */}
      <div className="flex border-b border-slate-800 space-x-6">
        <button
          onClick={() => setActiveTab('assigned')}
          className={`pb-3 text-sm font-medium flex items-center space-x-2 border-b-2 transition-colors ${
            activeTab === 'assigned'
              ? 'border-indigo-500 text-indigo-400'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
          data-testid="tab-assigned"
        >
          <CheckCircle2 className="w-4 h-4" />
          <span>Assigned Jobs</span>
          {scheduleData && (
            <span className="text-xs px-2 py-0.5 rounded-full bg-slate-800 text-slate-300">
              {scheduleData.assigned_count}
            </span>
          )}
        </button>

        <button
          onClick={() => setActiveTab('unassigned')}
          className={`pb-3 text-sm font-medium flex items-center space-x-2 border-b-2 transition-colors ${
            activeTab === 'unassigned'
              ? 'border-indigo-500 text-indigo-400'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
          data-testid="tab-unassigned"
        >
          <AlertTriangle className="w-4 h-4 text-amber-400" />
          <span>Unassigned & Feasibility</span>
          {scheduleData && (
            <span className="text-xs px-2 py-0.5 rounded-full bg-amber-950 text-amber-300 border border-amber-800/60">
              {scheduleData.unassigned_count}
            </span>
          )}
        </button>

        <button
          onClick={() => setActiveTab('timeline')}
          className={`pb-3 text-sm font-medium flex items-center space-x-2 border-b-2 transition-colors ${
            activeTab === 'timeline'
              ? 'border-indigo-500 text-indigo-400'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
          data-testid="tab-timeline"
        >
          <Layers className="w-4 h-4" />
          <span>Technician Itineraries</span>
        </button>
      </div>

      {/* Search and Filters Bar */}
      <div className="bg-slate-900 border border-slate-800 rounded-lg p-3.5 flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[220px]">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            placeholder={
              activeTab === 'assigned'
                ? 'Search by Job ID, title, customer, or technician...'
                : 'Search by Job ID, title, or customer...'
            }
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full pl-9 pr-3 py-1.5 text-xs bg-slate-950 border border-slate-800 rounded-md text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500"
          />
        </div>

        {/* Zone Filter */}
        <div className="flex items-center space-x-1.5">
          <label className="text-xs text-slate-400">Zone:</label>
          <select
            value={zoneFilter}
            onChange={(e) => setZoneFilter(e.target.value)}
            className="text-xs bg-slate-950 border border-slate-800 rounded-md px-2.5 py-1.5 text-slate-200 focus:outline-none focus:border-indigo-500"
          >
            <option value="all">All Zones</option>
            {ZONES.map((z) => (
              <option key={z} value={z}>{z}</option>
            ))}
          </select>
        </div>

        {/* Priority Filter */}
        <div className="flex items-center space-x-1.5">
          <label className="text-xs text-slate-400">Priority:</label>
          <select
            value={priorityFilter}
            onChange={(e) => setPriorityFilter(e.target.value)}
            className="text-xs bg-slate-950 border border-slate-800 rounded-md px-2.5 py-1.5 text-slate-200 focus:outline-none focus:border-indigo-500"
          >
            <option value="all">All Priorities</option>
            <option value="1">1 - Urgent</option>
            <option value="2">2 - High</option>
            <option value="3">3 - Medium</option>
            <option value="4">4 - Low</option>
          </select>
        </div>

        {/* Feasibility Category Filter (Only on Unassigned Tab) */}
        {activeTab === 'unassigned' && (
          <div className="flex items-center space-x-1.5">
            <label className="text-xs text-slate-400">Category:</label>
            <select
              value={categoryFilter}
              onChange={(e) => setCategoryFilter(e.target.value)}
              className="text-xs bg-slate-950 border border-slate-800 rounded-md px-2.5 py-1.5 text-slate-200 focus:outline-none focus:border-indigo-500"
            >
              <option value="all">All Diagnostics</option>
              <option value="currently_infeasible">Currently Infeasible (Temporary)</option>
              <option value="permanently_impossible">Permanently Impossible (Capability)</option>
              <option value="unsupported_skill">Unsupported Skill</option>
              <option value="uncovered_zone">Uncovered Zone (Z6)</option>
              <option value="missing_equipment">Missing Equipment</option>
              <option value="missing_skill">Missing Skill Combo</option>
              <option value="shift_hours">Shift / Hours Cap</option>
            </select>
          </div>
        )}
      </div>

      {/* ========================================================================= */}
      {/* TAB 1: ASSIGNED JOBS LIST                                                 */}
      {/* ========================================================================= */}
      {activeTab === 'assigned' && (
        <div className="space-y-4">
          {loading ? (
            <div className="p-8 text-center text-slate-400 text-sm">
              <RefreshCw className="w-5 h-5 mx-auto mb-2 animate-spin text-indigo-400" />
              Loading current assignments...
            </div>
          ) : filteredAssignments.length === 0 ? (
            <div className="bg-slate-900 border border-slate-800 rounded-lg p-10 text-center">
              <Calendar className="w-8 h-8 mx-auto text-slate-600 mb-2" />
              <p className="text-sm font-medium text-slate-300">No matching assignments found</p>
              <p className="text-xs text-slate-500 mt-1">
                {scheduleData?.assigned_count === 7
                  ? 'Only 7 baseline pre-existing assignments are active. Click "Generate Schedule" to dispatch remaining jobs.'
                  : 'Try modifying your search query or filter selection.'}
              </p>
            </div>
          ) : (
            <div className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs text-slate-300">
                  <thead className="bg-slate-950/70 border-b border-slate-800 text-[11px] uppercase tracking-wider text-slate-400">
                    <tr>
                      <th className="py-3 px-4">Job Details</th>
                      <th className="py-3 px-4">Zone & Priority</th>
                      <th className="py-3 px-4">Assigned Technician</th>
                      <th className="py-3 px-4">Scheduled Window</th>
                      <th className="py-3 px-4">Transit / Buffer</th>
                      <th className="py-3 px-4 text-right">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60 font-mono text-xs">
                    {filteredAssignments.map((assign) => (
                      <tr key={`${assign.job_id}-${assign.assignment_id || 'new'}`} className="hover:bg-slate-850/40">
                        {/* Job Details */}
                        <td className="py-3 px-4 font-sans">
                          <div className="flex items-center space-x-2">
                            <span className="font-mono font-semibold text-indigo-400">{assign.job_id}</span>
                            {assign.is_existing && (
                              <span className="text-[10px] px-1.5 py-0.5 rounded bg-blue-950 text-blue-400 border border-blue-800">
                                Protected
                              </span>
                            )}
                          </div>
                          <p className="text-xs font-medium text-white truncate max-w-xs mt-0.5">
                            {assign.job_title || 'Service Job'}
                          </p>
                          <p className="text-[11px] text-slate-400">{assign.customer_name || 'Customer'}</p>
                        </td>

                        {/* Zone & Priority */}
                        <td className="py-3 px-4 font-sans">
                          <div className="flex items-center space-x-1.5">
                            <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-300 text-[11px] font-mono">
                              {assign.zone_id || 'Z1'}
                            </span>
                            <span
                              className={`text-[10px] px-2 py-0.5 rounded font-medium ${
                                assign.priority === 1
                                  ? 'bg-rose-950 text-rose-300 border border-rose-800'
                                  : assign.priority === 2
                                  ? 'bg-orange-950 text-orange-300 border border-orange-800'
                                  : 'bg-slate-800 text-slate-300'
                              }`}
                            >
                              P{assign.priority || 3} {assign.priority_label}
                            </span>
                          </div>
                          <p className="text-[11px] text-slate-400 mt-1">{assign.duration_minutes}m duration</p>
                        </td>

                        {/* Assigned Technician */}
                        <td className="py-3 px-4 font-sans">
                          <button
                            onClick={() => {
                              setSelectedTechId(assign.technician_id);
                              setActiveTab('timeline');
                            }}
                            className="flex items-center space-x-2 text-left hover:text-indigo-300 transition-colors group"
                            title="Inspect Technician Itinerary"
                          >
                            <div className="w-6 h-6 rounded-full bg-indigo-950 border border-indigo-700 flex items-center justify-center text-[11px] font-bold text-indigo-400 group-hover:border-indigo-400">
                              {assign.technician_id}
                            </div>
                            <div>
                              <p className="text-xs font-semibold text-white group-hover:text-indigo-300">
                                {assign.technician_name}
                              </p>
                              <p className="text-[10px] text-slate-400">ID: {assign.technician_id}</p>
                            </div>
                          </button>
                        </td>

                        {/* Scheduled Window */}
                        <td className="py-3 px-4">
                          <div className="text-white text-xs">
                            {formatTime(assign.start_time)} – {formatTime(assign.end_time)}
                          </div>
                          <div className="text-[11px] text-slate-400">{formatDate(assign.start_time)}</div>
                        </td>

                        {/* Transit / Buffer */}
                        <td className="py-3 px-4 font-sans">
                          <div className="text-xs text-slate-300">
                            {assign.travel_time_minutes > 0 ? `${assign.travel_time_minutes} mins` : 'Adjacent stop'}
                          </div>
                          <div className="text-[11px] text-slate-500">
                            {assign.distance_km > 0 ? `${assign.distance_km} km` : '0 km'}
                          </div>
                        </td>

                        {/* Status */}
                        <td className="py-3 px-4 text-right font-sans">
                          <span
                            className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium ${
                              assign.status === 'completed'
                                ? 'bg-emerald-950 text-emerald-300 border border-emerald-800'
                                : assign.status === 'in_progress'
                                ? 'bg-amber-950 text-amber-300 border border-amber-800'
                                : 'bg-indigo-950 text-indigo-300 border border-indigo-800'
                            }`}
                          >
                            {assign.status}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ========================================================================= */}
      {/* TAB 2: UNASSIGNED JOBS & FEASIBILITY EXPLANATIONS                          */}
      {/* ========================================================================= */}
      {activeTab === 'unassigned' && (
        <div className="space-y-4">
          {loading ? (
            <div className="p-8 text-center text-slate-400 text-sm">
              <RefreshCw className="w-5 h-5 mx-auto mb-2 animate-spin text-indigo-400" />
              Loading unassigned feasibility diagnostics...
            </div>
          ) : filteredUnassigned.length === 0 ? (
            <div className="bg-slate-900 border border-slate-800 rounded-lg p-10 text-center">
              <CheckCircle2 className="w-8 h-8 mx-auto text-emerald-400 mb-2" />
              <p className="text-sm font-medium text-slate-200">Zero unassigned jobs in this view</p>
              <p className="text-xs text-slate-500 mt-1">
                Every job matching the current criteria is scheduled.
              </p>
            </div>
          ) : (
            <div className="space-y-3" data-testid="unassigned-list">
              {filteredUnassigned.map((job) => (
                <div
                  key={job.job_id}
                  className="bg-slate-900 border border-slate-800 hover:border-slate-700 rounded-lg p-4 transition-all"
                  data-testid={`unassigned-job-${job.job_id}`}
                >
                  <div className="flex flex-col md:flex-row md:items-start justify-between gap-3">
                    {/* Job Info */}
                    <div className="flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-mono font-bold text-amber-400 text-sm">{job.job_id}</span>
                        <span className="text-xs px-2 py-0.5 rounded bg-slate-800 text-slate-300 font-mono">
                          {job.zone_id || 'Z1'}
                        </span>
                        <span
                          className={`text-xs px-2 py-0.5 rounded font-medium ${
                            job.priority === 1
                              ? 'bg-rose-950 text-rose-300 border border-rose-800'
                              : job.priority === 2
                              ? 'bg-orange-950 text-orange-300 border border-orange-800'
                              : 'bg-slate-800 text-slate-300'
                          }`}
                        >
                          P{job.priority} {job.priority_label}
                        </span>

                        {/* Feasibility Classification Badge */}
                        <span
                          className={`text-xs px-2.5 py-0.5 rounded-full font-semibold border ${
                            job.classification === 'permanently_impossible'
                              ? 'bg-rose-950/80 text-rose-300 border-rose-700'
                              : 'bg-amber-950/80 text-amber-300 border-amber-700'
                          }`}
                        >
                          {job.classification === 'permanently_impossible'
                            ? 'Permanently Impossible (Structural Deficit)'
                            : 'Currently Infeasible (Capacity Limit)'}
                        </span>

                        {/* Category Tag */}
                        <span className="text-[11px] px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700 font-mono">
                          {job.primary_category}
                        </span>
                      </div>

                      <h3 className="text-sm font-semibold text-white mt-2">{job.title}</h3>
                      <p className="text-xs text-slate-400">
                        Customer: <span className="text-slate-300">{job.customer_name}</span> • Duration: {job.duration_minutes}m
                      </p>

                      {/* Required Skills & Equipment tags */}
                      <div className="flex flex-wrap gap-1.5 mt-2.5">
                        {job.required_skills.map((s) => (
                          <span
                            key={s}
                            className={`text-[11px] px-2 py-0.5 rounded ${
                              s === 'high_voltage'
                                ? 'bg-rose-950 text-rose-300 border border-rose-800 font-semibold'
                                : 'bg-slate-800 text-slate-300'
                            }`}
                          >
                            Skill: {s}
                          </span>
                        ))}
                        {job.required_equipment.map((eq) => (
                          <span
                            key={eq}
                            className={`text-[11px] px-2 py-0.5 rounded ${
                              eq === 'crane'
                                ? 'bg-rose-950 text-rose-300 border border-rose-800 font-semibold'
                                : 'bg-slate-800 text-slate-300'
                            }`}
                          >
                            Tool: {eq}
                          </span>
                        ))}
                      </div>

                      {/* Diagnostic Explanation Banner */}
                      <div className="mt-3 p-3 rounded bg-slate-950/80 border border-slate-800/80 space-y-1.5 text-xs">
                        <div className="flex items-start space-x-2 text-slate-300">
                          <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
                          <div>
                            <span className="font-semibold text-white">Why unassigned: </span>
                            <span>{job.rejection_summary}</span>
                          </div>
                        </div>
                        <div className="flex items-start space-x-2 text-indigo-300 pl-6">
                          <ArrowRight className="w-3.5 h-3.5 text-indigo-400 shrink-0 mt-0.5" />
                          <div>
                            <span className="font-semibold text-indigo-200">Recommendation: </span>
                            <span>{job.actionable_recommendation}</span>
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* Inspect Button */}
                    <div className="self-end md:self-start mt-2 md:mt-0">
                      <button
                        onClick={() => handleOpenFeasibility(job.job_id)}
                        disabled={loadingFeasibility}
                        className="inline-flex items-center px-3 py-1.5 text-xs font-medium rounded bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition-colors"
                      >
                        <Info className="w-3.5 h-3.5 mr-1 text-slate-400" />
                        Technician Matrix
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ========================================================================= */}
      {/* TAB 3: TECHNICIAN ROUTE TIMELINES                                         */}
      {/* ========================================================================= */}
      {activeTab === 'timeline' && (
        <div className="space-y-4">
          {/* Technician Picker */}
          <div className="bg-slate-900 border border-slate-800 rounded-lg p-4 flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-center space-x-3">
              <User className="w-5 h-5 text-indigo-400" />
              <div>
                <h3 className="text-sm font-semibold text-white">Technician Dispatch Itinerary</h3>
                <p className="text-xs text-slate-400">Sequential routes with transit buffers and service stops</p>
              </div>
            </div>

            <div className="flex items-center space-x-2">
              <label className="text-xs text-slate-400 font-medium">Select Technician:</label>
              <select
                value={selectedTechId}
                onChange={(e) => setSelectedTechId(e.target.value)}
                className="text-xs bg-slate-950 border border-slate-700 rounded-md px-3 py-1.5 text-white font-medium focus:outline-none focus:border-indigo-500"
              >
                {Array.from({ length: 20 }, (_, i) => {
                  const id = `T${String(i + 1).padStart(2, '0')}`;
                  return (
                    <option key={id} value={id}>
                      {id} {id === selectedTechId && techSchedule ? `- ${techSchedule.technician_name}` : ''}
                    </option>
                  );
                })}
              </select>
            </div>
          </div>

          {loadingTechSchedule ? (
            <div className="p-8 text-center text-slate-400 text-sm">
              <RefreshCw className="w-5 h-5 mx-auto mb-2 animate-spin text-indigo-400" />
              Loading itinerary for {selectedTechId}...
            </div>
          ) : !techSchedule ? (
            <div className="bg-slate-900 border border-slate-800 rounded-lg p-8 text-center text-slate-400 text-sm">
              Select a technician to view their dispatch timeline.
            </div>
          ) : (
            <div className="space-y-4">
              {/* Technician Info Card */}
              <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
                <div className="flex flex-wrap items-center justify-between gap-4">
                  <div>
                    <div className="flex items-center space-x-2">
                      <span className="font-mono text-base font-bold text-indigo-400">{techSchedule.technician_id}</span>
                      <h4 className="text-sm font-bold text-white">{techSchedule.technician_name}</h4>
                      <span className="text-xs px-2 py-0.5 rounded bg-slate-800 text-slate-300">
                        Home: {techSchedule.home_zone_id || 'Z1'}
                      </span>
                    </div>
                    <p className="text-xs text-slate-400 mt-1">
                      Certified Zones: {techSchedule.eligible_zones.join(', ')} • Skills: {techSchedule.skills.join(', ')}
                    </p>
                  </div>

                  <div className="flex items-center space-x-4 text-xs">
                    <div className="text-right">
                      <span className="text-slate-400">Total Stops: </span>
                      <span className="font-bold text-white">{techSchedule.total_assigned_jobs}</span>
                    </div>
                    <div className="text-right">
                      <span className="text-slate-400">Working: </span>
                      <span className="font-bold text-white">{techSchedule.total_working_minutes} mins</span>
                    </div>
                    <div className="text-right">
                      <span className="text-slate-400">Transit: </span>
                      <span className="font-bold text-emerald-400">{techSchedule.total_travel_minutes} mins</span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Sequential Stops Timeline */}
              {techSchedule.itinerary.length === 0 ? (
                <div className="bg-slate-900 border border-slate-800 rounded-lg p-8 text-center text-slate-400 text-sm">
                  No assignments currently scheduled for {techSchedule.technician_name}.
                </div>
              ) : (
                <div className="bg-slate-900 border border-slate-800 rounded-lg p-5">
                  <div className="relative pl-6 space-y-6 before:absolute before:left-2.5 before:top-3 before:bottom-3 before:w-0.5 before:bg-slate-800">
                    {/* Home Depot Origin */}
                    <div className="relative flex items-start space-x-3 text-xs">
                      <div className="w-5 h-5 rounded-full bg-slate-800 border-2 border-slate-600 absolute -left-6 top-0 flex items-center justify-center">
                        <div className="w-1.5 h-1.5 rounded-full bg-slate-400" />
                      </div>
                      <div>
                        <p className="font-semibold text-slate-300">Home Depot Base</p>
                        <p className="text-[11px] text-slate-500">
                          {techSchedule.home_lat.toFixed(4)}, {techSchedule.home_lng.toFixed(4)} ({techSchedule.home_zone_id})
                        </p>
                      </div>
                    </div>

                    {/* Stops */}
                    {techSchedule.itinerary.map((stop, idx) => (
                      <div key={`${stop.job_id}-${idx}`} className="relative space-y-2">
                        {/* Travel Leg Buffer */}
                        <div className="relative flex items-center space-x-2 text-[11px] text-emerald-400 pl-2 py-1 rounded bg-slate-950/60 border border-slate-800/60 max-w-sm">
                          <Navigation className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                          <span>
                            Transit Leg {idx + 1}: {stop.travel_from_previous_minutes} mins ({stop.distance_from_previous_km} km @ 30 km/h)
                          </span>
                        </div>

                        {/* Service Stop */}
                        <div className="relative flex items-start space-x-3 text-xs pl-0">
                          <div className="w-5 h-5 rounded-full bg-indigo-900 border-2 border-indigo-500 absolute -left-6 top-1 flex items-center justify-center text-[10px] font-bold text-white">
                            {idx + 1}
                          </div>

                          <div className="bg-slate-950 border border-slate-800 rounded-lg p-3 flex-1 space-y-1">
                            <div className="flex items-center justify-between">
                              <div className="flex items-center space-x-2">
                                <span className="font-mono font-bold text-indigo-400">{stop.job_id}</span>
                                <span className="font-semibold text-white">{stop.job_title}</span>
                              </div>
                              <span className="text-[10px] px-2 py-0.5 rounded bg-slate-800 text-slate-300 font-mono">
                                {formatTime(stop.start_time)} – {formatTime(stop.end_time)}
                              </span>
                            </div>

                            <p className="text-xs text-slate-400">
                              Customer: {stop.customer_name} • Zone: {stop.zone_id} • Service: {stop.duration_minutes}m
                            </p>
                            <p className="text-[11px] text-slate-500 font-mono">
                              Coordinates: {stop.lat.toFixed(4)}, {stop.lng.toFixed(4)}
                            </p>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* ========================================================================= */}
      {/* SLIDE-OVER MODAL: TECHNICIAN REJECTION MATRIX                             */}
      {/* ========================================================================= */}
      {feasibilityModal && (
        <div className="fixed inset-0 z-50 overflow-y-auto bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-xl max-w-3xl w-full max-h-[85vh] flex flex-col shadow-2xl">
            {/* Modal Header */}
            <div className="p-5 border-b border-slate-800 flex items-center justify-between">
              <div>
                <div className="flex items-center space-x-2">
                  <span className="font-mono text-base font-bold text-amber-400">{feasibilityModal.job_id}</span>
                  <span className="text-xs px-2.5 py-0.5 rounded-full bg-slate-800 text-slate-200 border border-slate-700">
                    {feasibilityModal.classification}
                  </span>
                </div>
                <p className="text-xs text-slate-400 mt-1">
                  Full 20-technician evaluation matrix and constraint diagnostic
                </p>
              </div>
              <button
                onClick={() => setFeasibilityModal(null)}
                className="text-slate-400 hover:text-white p-1 rounded-md"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Modal Body */}
            <div className="p-5 overflow-y-auto space-y-4">
              <div className="p-3.5 rounded bg-slate-950 border border-slate-800 text-xs space-y-1">
                <p className="text-slate-300">
                  <span className="font-semibold text-white">Summary: </span>
                  {feasibilityModal.rejection_summary}
                </p>
                <p className="text-indigo-300">
                  <span className="font-semibold text-indigo-200">Recommended action: </span>
                  {feasibilityModal.actionable_recommendation}
                </p>
              </div>

              <h4 className="text-xs font-bold text-white uppercase tracking-wider">
                Technician Evaluation Breakdown ({feasibilityModal.technician_rejections.length} Evaluated)
              </h4>

              <div className="border border-slate-800 rounded-lg overflow-hidden">
                <table className="w-full text-left text-xs text-slate-300">
                  <thead className="bg-slate-950 text-[11px] uppercase tracking-wider text-slate-400 border-b border-slate-800">
                    <tr>
                      <th className="py-2.5 px-3">Technician</th>
                      <th className="py-2.5 px-3">Category</th>
                      <th className="py-2.5 px-3">Detailed Rejection Reason</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60 font-mono text-xs">
                    {feasibilityModal.technician_rejections.map((rej) => (
                      <tr key={rej.technician_id} className="hover:bg-slate-850/50">
                        <td className="py-2.5 px-3 font-sans">
                          <span className="font-mono font-bold text-indigo-400">{rej.technician_id}</span>
                          <span className="text-slate-300 ml-1.5">{rej.technician_name}</span>
                        </td>
                        <td className="py-2.5 px-3 font-sans">
                          <span className="text-[11px] px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">
                            {rej.rejection_category}
                          </span>
                        </td>
                        <td className="py-2.5 px-3 font-sans text-slate-300 text-xs">
                          {rej.explanation}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Modal Footer */}
            <div className="p-4 border-t border-slate-800 flex justify-end">
              <button
                onClick={() => setFeasibilityModal(null)}
                className="px-4 py-1.5 text-xs font-semibold rounded bg-slate-800 hover:bg-slate-700 text-white transition-colors"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
