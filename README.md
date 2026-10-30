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
