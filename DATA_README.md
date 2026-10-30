# DispatchGrid seed data

## Generate / load
```bash
python generate_seed.py                          # writes ./data/*.json
python generate_seed.py --out data --sqlite seed.db   # also builds a SQLite DB
```
Deterministic (fixed seed), stdlib only. Scheduling clock (`as_of`) = Mon 2 Nov 2026 10:00 IST; horizon = 2–3 Nov.

## What is inside
| File | Contents |
|---|---|
| `meta.json` | as_of time, zones (+adjacency), skills, travel model, hard/soft constraint conventions |
| `technicians.json` | 20 technicians: skills, equipment, eligible zones, shifts, unavailable periods, overtime rules |
| `jobs.json` | 108 jobs: 100 pending, 4 completed, 3 in_progress, 1 cancelled |
| `existing_assignments.json` | the 7 completed/in-progress assignments that must be preserved |
| `disruptions.json` | 9 disruption scenarios + 3 reliability scenarios, each with expected behaviour |

## Requirement coverage
- **20 technicians / 100 jobs**: yes (100 pending jobs to schedule).
- **Multiple skills and zones**: 8 skills, 5 served zones (+1 uncovered zone `Z6`).
- **Priorities and SLA deadlines**: urgent/high/medium/low (1–4); `sla_deadline` is a soft target, `time_window_*` is hard.
- **Conflicting time windows**: 3 competing urgent pairs (A: elevator, B: electrical, C: fibre networking) and a 6-job East-zone HVAC crunch (13:00–16:00).
- **Technician unavailable periods**: T02, T05, T07, T13, T20 (plus single-day shifts for T09, T15, T16).
- **Jobs that cannot be assigned** (tag `unassignable_*`): missing skill, missing equipment, uncovered zone, outside all shifts, window shorter than duration, no single tech with all skills, cannot reach in time. One job (`sla_already_breached_assign_late`) is assignable but already late.
- **Disruptions**: technician unavailable, urgent job, two urgent jobs competing, duration change, cancellation, invalid state transition, finishing early/late, technician leaving during an in-progress job, duplicate request, concurrent runs, interrupted run.

Hard constraints: skills, equipment, zone eligibility, shifts, unavailable periods, time windows, no overlap, travel time.
Soft (objective): SLA lateness, travel time, unassigned high-priority jobs, overtime, changes to existing assignments.
