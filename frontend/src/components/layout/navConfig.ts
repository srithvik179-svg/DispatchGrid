import {
  LayoutDashboard,
  Briefcase,
  Users,
  Calendar,
  Zap,
  AlertTriangle,
  History,
  BarChart3,
  Settings as SettingsIcon,
  LucideIcon,
} from 'lucide-react';

export interface NavItem {
  name: string;
  path: string;
  icon: LucideIcon;
  badge?: string;
  description: string;
}

export const NAV_ITEMS: NavItem[] = [
  {
    name: 'Overview',
    path: '/',
    icon: LayoutDashboard,
    description: 'Executive overview and system status',
  },
  {
    name: 'Jobs',
    path: '/jobs',
    icon: Briefcase,
    description: 'Job registry, time windows, and SLA constraints',
  },
  {
    name: 'Technicians',
    path: '/technicians',
    icon: Users,
    description: 'Technician fleet, skills, shifts, and equipment',
  },
  {
    name: 'Schedule',
    path: '/schedule',
    icon: Calendar,
    description: 'Timeline and assignment dispatch board',
  },
  {
    name: 'Optimisation',
    path: '/optimisation',
    icon: Zap,
    description: 'Deterministic solver and objective weights',
  },
  {
    name: 'Disruptions',
    path: '/disruptions',
    icon: AlertTriangle,
    description: 'Operational disruptions and real-time recovery',
  },
  {
    name: 'Audit History',
    path: '/audit-history',
    icon: History,
    description: 'Run logs, explainability reasons, and traces',
  },
  {
    name: 'Analytics',
    path: '/analytics',
    icon: BarChart3,
    description: 'Workload, SLA performance, and travel metrics',
  },
  {
    name: 'Settings',
    path: '/settings',
    icon: SettingsIcon,
    description: 'Simulation clock, rules, and system parameters',
  },
];
