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
