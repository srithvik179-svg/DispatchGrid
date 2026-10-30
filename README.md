# DispatchGrid – Intelligent Workforce Scheduling & Recovery Engine

DispatchGrid is an enterprise-grade workforce scheduling platform engineered for field-service organizations. It deterministically assigns service jobs to technicians, rigorously enforces multi-dimensional operational constraints, optimizes assignment quality, recovers gracefully from disruptions, and provides complete traceability for every dispatch decision.

---

## 1. System Architecture & Tech Stack

- **Frontend**:
  - React 18 with TypeScript
  - Vite build tool
  - Tailwind CSS for modern enterprise UI
  - Vitest & React Testing Library for frontend testing
- **Backend**:
  - Python 3.9+ with FastAPI
  - Pydantic v2 data validation & settings management
  - SQLAlchemy 2.0 ORM / persistent storage
  - Pytest & HTTPX for integration and unit testing
- **Dataset**:
  - Authoritative dataset containing 20 technicians, 108 jobs (100 pending, 4 completed, 3 in progress, 1 cancelled), 6 zones (Z1–Z6), 8 skills, and 12 disruption/reliability scenarios.
  - Simulation clock: `2026-11-02T10:00:00+05:30`.
  - Planning horizon: 2 November – 3 November 2026.
  - Travel calculation: Haversine distance @ 30 km/h.

---

## 2. Project Directory Structure

```
DispatchGrid/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   └── v1/
│   │   │       ├── endpoints/
│   │   │       │   └── health.py        # Health check router
│   │   │       └── api.py               # Combined API v1 router
│   │   ├── core/
│   │   │   └── config.py                # Environment and app configuration
│   │   └── main.py                      # FastAPI application entrypoint
│   ├── tests/
│   │   ├── conftest.py                  # Pytest fixtures & HTTPX client
│   │   └── test_health.py               # Health endpoint verification
│   ├── .env.example                     # Backend environment template
│   └── requirements.txt                 # Backend Python dependencies
├── frontend/
│   ├── src/
│   │   ├── App.tsx                      # DispatchGrid landing page
│   │   ├── App.test.tsx                 # Frontend landing page tests
│   │   ├── main.tsx                     # React DOM bootstrap
│   │   ├── index.css                    # Tailwind CSS definitions
│   │   ├── setupTests.ts                # Jest-DOM matchers setup
│   │   └── vite-env.d.ts                # Vite environment typings
│   ├── index.html                       # HTML5 entrypoint
│   ├── package.json                     # Node dependencies & scripts
│   ├── tailwind.config.js               # Tailwind design system configuration
│   ├── tsconfig.json                    # TypeScript compiler options
│   └── vite.config.ts                   # Vite bundler & Vitest configuration
├── data/                                # Authoritative seed dataset
│   ├── disruptions.json
│   ├── existing_assignments.json
│   ├── jobs.json
│   ├── meta.json
│   └── technicians.json
├── generate_seed.py                     # Deterministic seed generator
├── seed.db                              # SQLite seed database
├── DATA_README.md                       # Dataset specification & rules
├── .env.example                         # Global environment template
├── .gitignore                           # Git ignore rules
└── README.md                            # Project documentation
```

---

## 3. Installation & Setup

### Prerequisites
- Python 3.9+ installed
- Node.js (v18+ or v20+) and npm installed
- PostgreSQL 14+ running locally or in Docker

### Database Setup
1. Create the PostgreSQL database:
   ```bash
   createdb dispatchgrid
   ```
2. Configure credentials in `backend/.env` (or pass environment variables):
   ```bash
   POSTGRES_SERVER=localhost
   POSTGRES_PORT=5432
   POSTGRES_USER=postgres
   POSTGRES_PASSWORD=postgres
   POSTGRES_DB=dispatchgrid
   ```
3. Run Alembic database migrations:
   ```bash
   cd backend
   source .venv/bin/activate
   alembic upgrade head
   ```
4. Load authoritative dataset into PostgreSQL:
   ```bash
   python -m app.cli.seed
   ```

### Backend Setup
1. Navigate to the `backend` directory:
   ```bash
   cd backend
   ```
2. Create and activate a Python virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```
3. Install dependencies:
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```
4. Copy the environment configuration:
   ```bash
   cp .env.example .env
   ```
5. Apply database migrations:
   ```bash
   alembic upgrade head
   ```

### Frontend Setup
1. Navigate to the `frontend` directory:
   ```bash
   cd frontend
   ```
2. Install dependencies:
   ```bash
   npm install
   ```

---

## 4. Running the Application

### Start the Backend
From the root or `backend` folder:
```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
- API Docs: `http://localhost:8000/docs`
- Health Endpoint: `http://localhost:8000/health` (or `http://localhost:8000/api/v1/health`)

### Start the Frontend
From the `frontend` folder:
```bash
cd frontend
npm run dev
```
- Access the web interface at: `http://localhost:5173`

The frontend connects directly to the backend health endpoint and indicates real-time operational status.

---

## 5. Running Automated Tests

### Backend Tests
```bash
cd backend
PYTHONPATH=. ./.venv/bin/pytest
```

### Frontend Tests
```bash
cd frontend
npm run test
```

### Frontend Production Build
```bash
cd frontend
npm run build
```

---

## 6. Development Status

- **Phase 01 – Project Initialisation**: Completed. Clean frontend and backend architecture established, live health endpoint verified, unit and integration tests passing, zero secrets committed.
- **Phase 02 – Basic Application Interface**: Completed. Collapsible enterprise application shell, header, simulation clock badge, active routing, and 9 module pages implemented.
- **Phase 03 – Database Integration**: Completed. PostgreSQL connectivity, connection pooling, reusable SQLAlchemy session management, Alembic migrations (`system_metadata`), database health monitoring, and credential masking verified.
- **Phase 04 – Dataset Integration**: Completed. Idempotent loading of authoritative hackathon dataset into PostgreSQL: 6 zones, 20 technicians, 108 jobs (100 pending, 4 completed, 3 in progress, 1 cancelled), 7 existing assignments, 12 disruption/reliability scenarios, and simulation clock (`2026-11-02T10:00:00+05:30`). Zero duplicate records on repeated execution.
- **Phase 05 – First Working Overview**: Completed. Connected frontend to `GET /api/v1/overview` displaying actual database counts (108 jobs: 100 pending, 4 completed, 3 in progress, 1 cancelled; 20 technicians; 7 assignments). Implemented live jobs & technicians preview tables, loading skeletons, error retry state, and data refresh.
- **Phase 06 – Job Creation API**: Completed. Implemented `POST /jobs` and `POST /api/v1/jobs` with Pydantic validation (customer name, title, priority 1–4, positive duration, geo-coordinates, required skills & equipment, time windows, and SLA deadlines), deterministic sequential ID generation, idempotency retry protection, duplicate prevention (409 Conflict), and persistent storage in PostgreSQL. Initial 108 seeded jobs remain completely intact.
- **Phase 07 – Job Management Interface**: Completed. Built full-featured job management interface (`JobsPage.tsx`) connected to live backend APIs. Features live search by ID/title/customer, multi-criteria filtering by priority, status, and zone, detailed slide-over job inspection modal, complete job creation modal with client-side & API error validation, loading skeletons, and empty state handling.
- **Phase 08 – Job Update and Cancellation**: Completed. Implemented deterministic state machine and lifecycle APIs (`PATCH /api/v1/jobs/{id}`, `POST /api/v1/jobs/{id}/cancel`, `GET /api/v1/jobs/{id}/history`). Enforced permitted transitions across `pending`, `unassigned`, `assigned`, `in_progress`, `completed`, and `cancelled`. Protected completed and cancelled jobs from alteration or cancellation (HTTP 400). Structured `job_state_history` audit trail logging each status mutation with reason, timestamp, and actor. Added frontend Edit modal, cancellation confirmation dialog with reason prompt, locked indicator for protected jobs, and visual state transition audit trail in the job detail inspection modal.
- **Phase 09 – Technician Registration API**: Completed. Implemented technician registration and fleet configuration APIs (`POST /technicians`, `POST /api/v1/technicians`, `GET /technicians`, `GET /api/v1/technicians`, `GET /technicians/{id}`, `GET /api/v1/technicians/{id}`). Enforces strict validation for skills, equipment, eligible zones, home coordinates, working shifts (`start < end`), unavailable periods, and overtime limits. Prevents duplicate technician IDs (HTTP 409 Conflict), supports auto-generated sequential IDs (`Txx`), and enables fleet filtering by zone and skill. Seeded 20 technicians remain preserved and verified.
- **Phase 10 – Technician Management Interface**: Completed. Built enterprise technician management interface (`TechniciansPage.tsx`) connected to live backend APIs (`/api/v1/technicians`). Features real-time fleet overview KPI metrics (fleet total, overtime-ready, multi-zone certified, scheduled leaves), multi-faceted search (ID, name, skills, equipment), dynamic filtering by operational zone, certified skill, and overtime policy. Integrated slide-over technician detail inspection modal with working shift schedules and planned unavailable intervals, complete technician registration modal with coordinate & skill tags selection, and technician editing modal (`PATCH /api/v1/technicians/{id}`). All 26 frontend unit/integration tests passing.
- **Phase 11 – Job and Technician Validation Engine**: Completed. Developed reusable, modular scheduling eligibility validation service (`backend/app/services/eligibility_service.py`) and API endpoint (`POST /api/v1/scheduling/validate-eligibility`). Formulates independent validators for multi-skill matching, equipment tooling verification, geographical zone eligibility, shift working hours with overtime allowances/limits, and collisions with pre-scheduled technician unavailable periods. Returns unified structured eligibility reports aggregating multiple simultaneous constraint failures with specific rejection messages. Tested thoroughly with 9 independent unit & API tests (60 total backend tests passing).
- **Phase 12 – Module A Completion and Testing**: Completed. Comprehensive stabilization, integration, and regression testing across all Module A components. Validated full lifecycle Job CRUD, Technician CRUD, state machine permitted/illegal transitions matrix, terminal state immutability, duplicate ID / idempotency conflict handling (HTTP 409), constraint rejections for zero/negative durations, corrupted time windows (`end <= start` or window < duration), mismatched SLA deadlines, missing skills, missing locations, and unavailabilities. 60 backend tests (`pytest`) and 26 frontend tests (`vitest`) passing with 100% clean build verification. Zero regressions detected. Seed dataset of 20 technicians, 108 jobs, and 7 assignments preserved.
- **Phase 13 – Scheduling Engine Foundation**: Completed. Created dedicated, independent scheduling package (`backend/app/scheduling/`) completely decoupled from API routes and frontend code. Defined robust Pydantic v2 input and output schemas (`SchedulingRunConfig`, `SchedulingInput`, `SchedulingResult`, `AssignedJobPlan`, `AssignmentSummary`). Implemented unique, chronological scheduling run IDs (`RUN-YYYYMMDD-HHMMSS-<hex>`). Integrated authoritative simulation clock (`2026-11-02T10:00:00+05:30`) and 48-hour planning horizon loading from database metadata. Implemented input loading for pending jobs (100 jobs sorted by priority), eligible technicians (20 roster), and existing assignments (7 locked/in-progress assignments strictly preserved). Exposed API routes (`GET /api/v1/scheduling/clock`, `GET /api/v1/scheduling/inputs`, `POST /api/v1/scheduling/runs/init`). Added 10 comprehensive unit and API tests with 70 total backend tests and 26 frontend tests passing cleanly without modifying any database assignments.
- **Phase 14 – Technician Skill Matching & Candidate Filtering**: Completed. Implemented deterministic skill-based candidate filtering engine (`backend/app/scheduling/skills.py`). Retrieves required skills for every job and certified skills for every technician. Enforces multi-skill matching where technicians must possess all mandatory skills (e.g. `JOB-026` requiring `electrical` and `cctv` matches `T09`). Accurately detects and explains missing skills with clear structured rejection reasons (`Technician lacks required skill(s)... holds:...`). Explicitly flags unsupported specialized requirements such as `high_voltage` (`JOB-014`), rendering jobs strictly unassignable (0 eligible candidates) to prevent invalid assignments. Handles multi-skill jobs with zero matching technicians (`JOB-057` requiring `elevator`, `electrical`, `hvac`). Integrated into `SchedulingService` and exposed via API endpoints (`GET /api/v1/scheduling/candidates/skills`, `POST /api/v1/scheduling/candidates/skills/filter`). Added 12 rigorous unit and API tests with all 82 backend tests and 26 frontend tests passing cleanly. Existing assignments and scheduling features remain completely unaffected.
- **Phase 15 – Equipment Matching Algorithm**: Completed. Extended candidate filtering to equipment requirements with dedicated algorithm module (`backend/app/scheduling/equipment.py`). Evaluates onboard technician kits against mandatory job tooling, supporting multiple required items and detecting inventory deficiencies (e.g. `crane` for `JOB-013`). Combines skill and equipment matching into unified qualification checks (`QualificationMatchResult`, `JobCandidateEvaluation`) while rigorously distinguishing skill failures from equipment failures. Accurately tracks candidates possessing matching skills but lacking required equipment (e.g. for `JOB-001`, `T08`, `T15`, and `T19` possess `networking` but lack `fiber_splicer`, leaving only `T04` and `T13` eligible). Exposed API routes (`GET /api/v1/scheduling/candidates`, `POST /api/v1/scheduling/candidates/filter`). Added 12 comprehensive unit and API tests with all 94 backend tests and 26 frontend tests passing cleanly. Pre-existing assignments remain strictly protected.
- **Phase 16 – Geographical and Travel Eligibility**: Completed. Implemented deterministic geographical eligibility and transit calculation module (`backend/app/scheduling/geo.py`). Built mathematical Haversine distance calculator ($R = 6371.0 \text{ km}$) and transit time estimator using the 30 km/h velocity specification (`(distance_km / 30.0) * 60`). Added coordinate validation rejecting non-numeric, NaN, infinite, and out-of-range coordinates. Computes first-job travel originating from technician home base coordinates (e.g. `T13` to `JOB-001`: 5.76 km, 11.52 mins) and inter-job travel between consecutive service locations (e.g. `JOB-001` to `JOB-002`: 1.09 km, 2.18 mins). Enforced hard zone eligibility against operational zones (`Z1`–`Z6`) and home territories with clear rejection rationales. Exposed API endpoints (`POST /api/v1/scheduling/travel/estimate`, `GET /api/v1/scheduling/travel/home-to-job`, `GET /api/v1/scheduling/travel/inter-job`, `GET /api/v1/scheduling/geo-eligibility`). Added 13 comprehensive unit and API tests with all 107 backend tests and 26 frontend tests passing cleanly. Zero external paid map APIs utilized.
- **Phase 17 – Shift and Availability Validation**: Completed. Developed robust multi-shift, multi-date availability and constraint engine (`backend/app/scheduling/availability.py`). Enforces hard shift boundaries across the 48-hour planning horizon, strictly controls overtime work permitted only when explicitly configured (`overtime.allowed == True`) up to defined limits (`max_minutes_per_shift`) and assesses associated objective penalties ($1.5 \times \text{overtime\_minutes}$). Detects collisions against scheduled technician unavailable intervals (leaves, breaks, training) while allowing valid abutting boundaries. Enforces authoritative simulation reference clock (`as_of: 2026-11-02T10:00:00+05:30`), rejecting retroactive dispatch attempts before the simulation clock. Integrated into `SchedulingService` and exposed via API endpoints (`POST /api/v1/scheduling/availability/evaluate`, `GET /api/v1/scheduling/availability/technician/{id}/job/{id}`). Added 11 unit and API tests with all 118 backend tests and 26 frontend tests passing cleanly. Pre-existing assignments remain strictly preserved.
- **Phase 18 – Job Time-Window Validation**: Completed. Implemented hard job time-window and SLA constraint validation engine (`backend/app/scheduling/time_windows.py`). Reads `time_window_start`, `time_window_end`, `duration_minutes`, and `sla_deadline`. Enforces hard start boundary (`proposed_start >= time_window_start`) and completion boundary (`completion_time <= time_window_end`). Verifies complete service duration integrity. Incorporates required technician transit travel time, verifying that origin departure plus travel duration arrives in time for service start. Rejects expired windows and retroactive scheduling against the authoritative simulation reference clock (`as_of: 2026-11-02T10:00:00+05:30`). Rigorously distinguishes hard time-window rejections from soft SLA lateness (when service finishes within the hard window but after `sla_deadline`, `is_eligible` remains `True` while reporting SLA delay metrics and penalties). Computes feasible scheduling intervals `[earliest_feasible_start, latest_feasible_start]`. Exposed API endpoints (`POST /api/v1/scheduling/time-windows/validate`, `GET /api/v1/scheduling/time-windows/job/{id}`, `GET /api/v1/scheduling/time-windows/job/{id}/feasible`). Added 11 unit and API tests with all 129 backend tests and 26 frontend tests passing cleanly. Seed dataset of 20 technicians, 108 jobs, and 7 assignments preserved.
- **Phase 19 – Scheduling Conflict Detection**: Completed. Developed scheduling conflict detection and buffer validation engine (`backend/app/scheduling/conflicts.py`). Implemented exact direct interval overlap detection preventing double booking (`DOUBLE_BOOKING_OVERLAP`). Enforced strict protection for active in-progress assignments (`IN_PROGRESS_ASSIGNMENT_COLLISION`) and completed historical assignments (`COMPLETED_ASSIGNMENT_COLLISION`). Included deterministic travel-time buffers between consecutive jobs (`calculate_travel_minutes` @ 30 km/h) detecting both preceding buffer deficits (`TRAVEL_BUFFER_CONFLICT_PRECEDING`) and succeeding buffer deficits (`TRAVEL_BUFFER_CONFLICT_SUCCEEDING`). Verified adjacent abutting schedules with zero-travel or exact-travel boundaries without false positives. Supported multi-date itinerary management across the 48-hour planning horizon. Enforced shift working hours and authorized overtime caps (`SHIFT_BOUNDARY_EXCEEDED`). Exposed API endpoints (`POST /api/v1/scheduling/conflicts/check`, `GET /api/v1/scheduling/conflicts/technician/{id}/job/{id}`). Added 11 unit and API tests with all 140 backend tests and 26 frontend tests passing cleanly. Seed dataset of 20 technicians, 108 jobs, and 7 assignments preserved.
- **Phase 20 – Initial Assignment Algorithm**: Completed. Implemented the first working automatic deterministic scheduling algorithm (`backend/app/scheduling/algorithm.py`). Features multi-criteria job prioritization (Priority 1 Urgent > 2 High > 3 Medium > 4 Low, constrained-difficulty ordering prioritizing jobs with rare skill/tool combinations, tight deadlines, and deterministic tie-breaking on job ID). Evaluates candidate technicians across multi-skills, onboard equipment, and operational zones. Finds feasible insertion slots across technician working shifts and multi-date horizons, enforcing simulation clock bounds, hard time windows, and transit buffers. Employs a multi-objective cost ranking function balancing transit efficiency, idle wait time, authorized overtime, SLA timeliness, and fleet workload balance (active technicians utilized = 20/20, preventing work concentration on T01). Dynamically updates in-memory itineraries so subsequent jobs respect newly created assignments without collisions. 100% reproducible results verified. Exposed API endpoint (`POST /api/v1/scheduling/runs/initial`). Added 6 unit & dataset integration tests with all 147 backend tests and 26 frontend tests passing cleanly. Seed dataset preserved.
- **Phase 21 – Feasibility Classification and Explanations**: Completed. Implemented comprehensive feasibility classification and diagnostic explanation engine (`backend/app/scheduling/feasibility.py`). Classifies unassigned and pending jobs into three distinct operational tiers: `feasible` (can be scheduled without violating hard constraints), `currently_infeasible` (structurally capable with qualified technicians, but blocked by temporary capacity: shift boundaries, schedule congestion, or travel buffers), and `permanently_impossible` (structural capability failure: unsupported skills, missing equipment, uncovered zones, or missing multi-skill combinations). Accurately detects and explains missing skills, missing equipment, uncovered operational zones (specifically explaining `JOB-017` in Zone `Z6` where fleet coverage is 0), unsupported specialized skills (specifically explaining `JOB-014` requiring `high_voltage`), missing multi-skill combinations (`JOB-057`), and unavailable fleet equipment (`JOB-013` requiring `crane`). Rigorously distinguishes soft SLA lateness from hard infeasibility. Returns granular per-technician rejection reasons and actionable operational recommendations for each tier. Exposed API endpoints (`GET /api/v1/scheduling/feasibility/job/{id}`, `GET /api/v1/scheduling/feasibility/fleet`, `POST /api/v1/scheduling/feasibility/evaluate`). Added 9 comprehensive unit and integration tests with all 156 backend tests and 26 frontend tests passing cleanly. Seed dataset preserved.
- **Phase 22 – Scheduling API and Frontend Integration**: Completed. Connected the scheduling engine through production REST APIs and fully integrated the frontend interface (`frontend/src/pages/SchedulePage.tsx`). Implemented `POST /schedule/generate` (and `/api/v1/schedule/generate`) with automatic schedule generation and safe persistence, updating newly dispatched jobs in PostgreSQL while strictly preserving the 7 pre-existing assignments. Implemented `GET /schedule/current` providing the operational schedule with assigned jobs and unassigned feasibility diagnostics. Implemented `GET /jobs/{job_id}/assignment` returning dispatch details for assigned jobs or diagnostic feasibility reports for unassigned jobs. Implemented `GET /technicians/{technician_id}/schedule` delivering sequential route timelines with Haversine transit buffers (@ 30 km/h) and distances from technician home locations. Implemented `POST /schedule/reset` restoring baseline schedules without altering locked assignments. Frontend features "Generate Schedule" action button, "Reset Schedule", KPI cards, Assigned Jobs list, Unassigned Jobs view with actionable explanations, and interactive Technician Route Timelines. Added comprehensive API integration tests (`backend/tests/test_schedule_api_integration.py`) and UI test suite (`frontend/src/pages/SchedulePage.test.tsx`). 161 backend tests and 31 frontend tests passing (100% green). Pre-existing assignments preserved.
- **Phase 23 – Objective Function and Scoring Engine**: Completed. Implemented configurable, deterministic schedule objective function and scoring engine (`backend/app/scheduling/scoring.py`). Formulates aggregate objective cost $J(S) = C_{\text{sla}} + C_{\text{travel}} + C_{\text{unassigned}} + C_{\text{overtime}} + C_{\text{churn}}$ with fully configurable weights (`ObjectiveWeightsConfig`). Evaluates separable components for soft SLA target lateness, route transit times (@ 30 km/h Haversine), unassigned jobs stratified across priority tiers (P1 Urgent to P4 Low), authorized overtime, and schedule churn/disruptions against baseline assignments. Rigorously enforces hard constraint independence: schedules violating double booking, skills, equipment, zones, shift overtime caps, or hard customer windows are strictly flagged as `is_feasible = False` with itemized violations, ensuring hard constraints can never be overridden by an objective score. Documented system units and mathematical assumptions. Exposed API endpoints (`GET /schedule/score`, `POST /schedule/score`). Added 8 comprehensive unit tests (`backend/tests/test_scheduling_scoring.py`) with all 169 backend tests and 31 frontend tests passing cleanly (100% green). Seed dataset preserved.
- **Phase 24 – Priority-Aware Optimisation**: Completed. Implemented priority-aware job ordering, technician scarcity estimation, and deterministic conflict arbitration engine (`backend/app/scheduling/priority.py`). Documents and enforces a strict 7-tier tie-breaking and ordering hierarchy: Tier 1 Operational Priority (P1 Urgent > P2 High > P3 Medium > P4 Low); Tier 2 Technician Scarcity (jobs with fewer qualified technicians holding certified skills, tooling, and zone coverage are prioritized to avoid bottleneck technician exhaustion); Tier 3 Time Window Tightness (`duration_minutes / window_minutes` ratio, tighter windows prioritized); Tier 4 Imminent Soft SLA Deadline; Tier 5 Hard Time Window End; Tier 6 Time Window Start; and Tier 7 Alphanumeric Job ID deterministic tie-breaker. Evaluated candidate assignments with principled comparison (`compare_candidate_assignments`) eliminating arbitrary dispatch decisions. Validated on actual conflict pairs from the dataset: `JOB-004` vs `JOB-083` (decided by `PRIORITY_LEVEL`), `JOB-093` vs `JOB-004` (decided by `TECHNICIAN_SCARCITY`), `JOB-055` vs `JOB-011` (decided by `WINDOW_TIGHTNESS`), `JOB-011` vs `JOB-039` (decided by `SLA_DEADLINE`), and `JOB-011` vs `JOB-032` / `JOB-048` vs `JOB-093` (decided by `DETERMINISTIC_ID`). Exposed REST API endpoints (`GET /jobs/{id}/priority-profile`, `POST /schedule/priority/resolve`, `GET /schedule/priority/ordered`). Added 9 comprehensive unit and dataset integration tests (`backend/tests/test_scheduling_priority.py`) with all 178 backend tests and 31 frontend tests passing cleanly (100% green). Seed dataset preserved.
- **Phase 25 – Travel-Time Optimisation**: Completed. Implemented travel-time optimization and geographical route refinement engine (`backend/app/scheduling/travel_opt.py`). Calculates consistent leg-by-leg transit metrics for each technician including home-to-first-job departure and consecutive inter-job transit (@ 30 km/h Haversine). Detects and tracks zone switching across distinct operational zones. Evaluates geographical assignment alternatives using intra-technician 2-opt route re-sequencing per shift date to cluster jobs geographically, batch same-zone visits (e.g. clustering Zone Z4 jobs for T12, reducing 1 zone switch and saving 16.49 minutes of transit travel), and eliminate unnecessary travel without violating any customer time windows, shift bounds, or leave schedules. Strictly verifies zero hard constraint violations (`validate_schedule_hard_constraints`), preserving 100% feasibility and protecting all 7 baseline/locked assignments. Measures exact fleet transit improvements (initial 889.09m down to 842.36m, saving 46.73 minutes of transit travel, 5.26% reduction) rather than assuming them. Every optimization decision is recorded in an explainable action log. Exposed REST API endpoints (`POST /schedule/optimize/travel`, `GET /schedule/travel-metrics`). Added 7 comprehensive unit and dataset integration tests (`backend/tests/test_scheduling_travel_optimization.py`) with all 185 backend tests and 31 frontend tests passing cleanly (100% green). Seed dataset preserved.
- **Phase 26 – SLA Optimisation**: Completed. Implemented SLA optimization, deadline-aware scheduling, and latency mitigation engine (`backend/app/scheduling/sla_opt.py`). Calculates exact expected completion times, SLA lateness, and configurable lateness penalties ($C_{\text{sla}} = \sum \text{lateness\_minutes} \times w_{\text{sla}}$). Identifies at-risk jobs with approaching deadlines using configurable slack buffer thresholds (default $\le$ 30 minutes). Rigorously distinguishes customer hard time windows from soft SLA deadlines: verified that the already-breached but assignable job (`JOB-016`: "AC down - already past SLA", soft SLA deadline `09:30` prior to simulation clock `10:00`) is successfully assigned to `T02` (completing at `11:02:27`, 92.5 minutes late relative to soft SLA, but safely within customer hard window ending at `13:00`), proving soft SLA breaches do not block assignment when otherwise feasible while hard windows remain strictly protected. Formulates deterministic arbitration for competing SLA deadlines (`resolve_competing_sla_deadlines`: earlier SLA deadline > tighter remaining slack buffer > operational priority tier > deterministic ID tie-breaker). Implemented SLA schedule optimization pass advancing starts where idle buffers allow while strictly preserving customer hard windows, shifts, and zero hard constraint violations. Generates comprehensive fleet-wide SLA performance metrics (evaluated 108 jobs: 69 on-time [78.4%], 17 at-risk [19.3%], 2 breached [2.3%], 1 already breached [JOB-016]). Exposed REST API endpoints (`GET /jobs/{job_id}/sla`, `GET /schedule/sla-metrics`, `POST /schedule/sla/resolve`, `POST /schedule/optimize/sla`). Added 8 comprehensive unit and dataset integration tests (`backend/tests/test_scheduling_sla_optimization.py`) with all 193 backend tests and 31 frontend tests passing cleanly (100% green). Seed dataset preserved.
- **Phase 27 – Schedule Stability Optimisation**: Completed. Implemented schedule stability, assignment preservation, and churn minimization engine (`backend/app/scheduling/stability.py`). Identifies and strictly protects completed work (`JOB-101`, `JOB-102`, `JOB-104`, `JOB-106`) and in-progress work (`JOB-103`, `JOB-105`, `JOB-107`), flagging any illegal mutation with explicit violations and setting stability score to 0.0. Assesses measurable penalties for modifying future scheduled work ($w_{\text{reassign}} = 250.0$, $w_{\text{shift\_per\_hour}} = 30.0$, $w_{\text{unassign}} = 500.0$). Builds comprehensive diffs comparing old and new assignments (`compare_schedules`) classifying modifications into `UNCHANGED`, `TIME_SHIFTED`, `REASSIGNED`, `DROPPED_TO_UNASSIGNED`, and `NEWLY_ASSIGNED`. Features minimal-churn recalculation (`recalculate_stable_schedule`) that locks unaffected technicians and valid assignments in place, restricting adjustments strictly to affected downstream work while satisfying all hard constraints (`is_feasible = True`). Generates fleet-wide assignment-stability metrics (stability score $> 90\%$, unchanged percentage $> 94\%$). Exposed REST API endpoints (`GET /schedule/stability`, `POST /schedule/stability/compare`, `POST /schedule/stability/recalculate`). Added 4 comprehensive unit and regression tests (`backend/tests/test_scheduling_stability.py`) with all 197 backend tests and 31 frontend tests passing cleanly (100% green). Seed dataset preserved.
