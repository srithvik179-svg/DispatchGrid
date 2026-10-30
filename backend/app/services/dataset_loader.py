import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.models.zone import Zone
from app.models.technician import Technician
from app.models.job import Job
from app.models.assignment import Assignment
from app.models.disruption import DisruptionScenario
from app.models.system import SystemMetadata
from app.schemas.dataset import (
    TechnicianSchema,
    JobSchema,
    ExistingAssignmentSchema,
    DisruptionScenarioSchema,
    ImportStats,
)

logger = logging.getLogger(__name__)


class DatasetLoaderService:
    def __init__(self, db: Session, data_dir: Optional[str] = None):
        self.db = db
        # Resolve data_dir relative to current working directory or repository root
        if data_dir:
            self.data_dir = Path(data_dir)
        else:
            # Try ./data or ../data
            p1 = Path("data")
            p2 = Path(__file__).resolve().parent.parent.parent.parent / "data"
            self.data_dir = p1 if p1.exists() else p2

    def load_all(self) -> ImportStats:
        """Loads and validates all dataset components idempotently."""
        stats = ImportStats(simulation_clock="2026-11-02T10:00:00+05:30")
        
        if not self.data_dir.exists():
            stats.errors.append(f"Data directory not found at {self.data_dir}")
            return stats

        # 1. Load metadata and zones
        self._load_meta(stats)

        # 2. Load technicians
        self._load_technicians(stats)

        # 3. Load jobs
        self._load_jobs(stats)

        # 4. Load existing assignments
        self._load_existing_assignments(stats)

        # 5. Load disruptions
        self._load_disruptions(stats)

        self.db.commit()
        return stats

    def _load_meta(self, stats: ImportStats) -> None:
        meta_file = self.data_dir / "meta.json"
        if not meta_file.exists():
            stats.errors.append("meta.json file missing")
            return

        try:
            with open(meta_file, "r", encoding="utf-8") as f:
                meta = json.load(f)

            # Extract simulation clock
            as_of = meta.get("as_of", "2026-11-02T10:00:00+05:30")
            stats.simulation_clock = as_of

            # Upsert SystemMetadata
            meta_entries = {
                "as_of": (as_of, "Authoritative simulation clock timestamp"),
                "time_zone": (meta.get("time_zone", "Asia/Kolkata (+05:30)"), "Operating time zone"),
                "planning_horizon": (json.dumps(meta.get("planning_horizon", {})), "Planning horizon boundaries"),
                "travel_model": (json.dumps(meta.get("travel_model", {})), "Transit speed and calculation rules"),
                "skills": (json.dumps(meta.get("skills", [])), "Supported certified skills list"),
                "unsupported_skills": (json.dumps(meta.get("unsupported_skills_in_jobs", [])), "Unsupported test skills"),
                "equipment": (json.dumps(meta.get("equipment", [])), "Supported equipment list"),
                "conventions": (json.dumps(meta.get("conventions", {})), "Hard and soft operational rules"),
            }

            for key, (val, desc) in meta_entries.items():
                record = self.db.query(SystemMetadata).filter_by(key=key).first()
                if not record:
                    record = SystemMetadata(key=key, value=val, description=desc)
                    self.db.add(record)
                else:
                    record.value = val
                    record.description = desc
                stats.metadata_keys_imported += 1

            # Import Zones
            zones = meta.get("zones", {})
            for zid, zdata in zones.items():
                zone = self.db.query(Zone).filter_by(id=zid).first()
                if not zone:
                    zone = Zone(
                        id=zid,
                        name=zdata.get("name", zid),
                        lat=float(zdata.get("lat", 0.0)),
                        lng=float(zdata.get("lng", 0.0)),
                        adjacent_zones=zdata.get("adjacent", []),
                    )
                    self.db.add(zone)
                else:
                    zone.name = zdata.get("name", zid)
                    zone.lat = float(zdata.get("lat", 0.0))
                    zone.lng = float(zdata.get("lng", 0.0))
                    zone.adjacent_zones = zdata.get("adjacent", [])
                stats.zones_imported += 1

            self.db.flush()
        except Exception as e:
            stats.errors.append(f"Failed to load meta.json: {str(e)}")

    def _load_technicians(self, stats: ImportStats) -> None:
        tech_file = self.data_dir / "technicians.json"
        if not tech_file.exists():
            stats.errors.append("technicians.json file missing")
            return

        try:
            with open(tech_file, "r", encoding="utf-8") as f:
                technicians_data = json.load(f)

            for item in technicians_data:
                try:
                    # Validate schema
                    t_val = TechnicianSchema(**item)
                    shifts_json = [s.model_dump(mode="json") for s in t_val.shifts]

                    tech = self.db.query(Technician).filter_by(id=t_val.id).first()
                    if not tech:
                        tech = Technician(
                            id=t_val.id,
                            name=t_val.name,
                            home_zone_id=t_val.home_zone_id,
                            home_lat=t_val.home_location.lat,
                            home_lng=t_val.home_location.lng,
                            eligible_zones=t_val.eligible_zones,
                            skills=t_val.skills,
                            equipment=t_val.equipment,
                            shifts=shifts_json,
                            unavailable_periods=t_val.unavailable_periods,
                            overtime_allowed=t_val.overtime.allowed,
                            max_overtime_minutes=t_val.overtime.max_minutes_per_shift,
                        )
                        self.db.add(tech)
                    else:
                        tech.name = t_val.name
                        tech.home_zone_id = t_val.home_zone_id
                        tech.home_lat = t_val.home_location.lat
                        tech.home_lng = t_val.home_location.lng
                        tech.eligible_zones = t_val.eligible_zones
                        tech.skills = t_val.skills
                        tech.equipment = t_val.equipment
                        tech.shifts = shifts_json
                        tech.unavailable_periods = t_val.unavailable_periods
                        tech.overtime_allowed = t_val.overtime.allowed
                        tech.max_overtime_minutes = t_val.overtime.max_minutes_per_shift
                        stats.records_skipped_or_updated += 1
                    stats.technicians_imported += 1
                except ValidationError as ve:
                    stats.errors.append(f"Invalid technician {item.get('id', 'unknown')}: {ve.errors()}")
                except Exception as e:
                    stats.errors.append(f"Error importing technician {item.get('id')}: {str(e)}")

            self.db.flush()
        except Exception as e:
            stats.errors.append(f"Failed to read technicians.json: {str(e)}")

    def _load_jobs(self, stats: ImportStats) -> None:
        jobs_file = self.data_dir / "jobs.json"
        if not jobs_file.exists():
            stats.errors.append("jobs.json file missing")
            return

        try:
            with open(jobs_file, "r", encoding="utf-8") as f:
                jobs_data = json.load(f)

            for item in jobs_data:
                try:
                    j_val = JobSchema(**item)
                    job = self.db.query(Job).filter_by(id=j_val.id).first()
                    if not job:
                        job = Job(
                            id=j_val.id,
                            idempotency_key=j_val.idempotency_key,
                            customer_name=j_val.customer_name,
                            title=j_val.title,
                            zone_id=j_val.zone_id,
                            lat=j_val.location.lat,
                            lng=j_val.location.lng,
                            address=j_val.location.address or "",
                            priority=j_val.priority,
                            priority_label=j_val.priority_label,
                            duration_minutes=j_val.duration_minutes,
                            required_skills=j_val.required_skills,
                            required_equipment=j_val.required_equipment,
                            time_window_start=j_val.time_window_start,
                            time_window_end=j_val.time_window_end,
                            sla_deadline=j_val.sla_deadline,
                            status=j_val.status,
                            assigned_technician_id=j_val.assigned_technician_id,
                            scheduled_start=j_val.scheduled_start,
                            scheduled_end=j_val.scheduled_end,
                            created_at=j_val.created_at,
                            tags=j_val.tags,
                        )
                        self.db.add(job)
                    else:
                        job.idempotency_key = j_val.idempotency_key
                        job.customer_name = j_val.customer_name
                        job.title = j_val.title
                        job.zone_id = j_val.zone_id
                        job.lat = j_val.location.lat
                        job.lng = j_val.location.lng
                        job.address = j_val.location.address or ""
                        job.priority = j_val.priority
                        job.priority_label = j_val.priority_label
                        job.duration_minutes = j_val.duration_minutes
                        job.required_skills = j_val.required_skills
                        job.required_equipment = j_val.required_equipment
                        job.time_window_start = j_val.time_window_start
                        job.time_window_end = j_val.time_window_end
                        job.sla_deadline = j_val.sla_deadline
                        job.status = j_val.status
                        job.assigned_technician_id = j_val.assigned_technician_id
                        job.scheduled_start = j_val.scheduled_start
                        job.scheduled_end = j_val.scheduled_end
                        job.created_at = j_val.created_at
                        job.tags = j_val.tags
                        stats.records_skipped_or_updated += 1
                    stats.jobs_imported += 1
                except ValidationError as ve:
                    stats.errors.append(f"Invalid job {item.get('id', 'unknown')}: {ve.errors()}")
                except Exception as e:
                    stats.errors.append(f"Error importing job {item.get('id')}: {str(e)}")

            self.db.flush()
        except Exception as e:
            stats.errors.append(f"Failed to read jobs.json: {str(e)}")

    def _load_existing_assignments(self, stats: ImportStats) -> None:
        assign_file = self.data_dir / "existing_assignments.json"
        if not assign_file.exists():
            stats.errors.append("existing_assignments.json file missing")
            return

        try:
            with open(assign_file, "r", encoding="utf-8") as f:
                assign_data = json.load(f)

            for item in assign_data:
                try:
                    a_val = ExistingAssignmentSchema(**item)
                    assignment = (
                        self.db.query(Assignment)
                        .filter_by(job_id=a_val.job_id, technician_id=a_val.technician_id)
                        .first()
                    )
                    if not assignment:
                        assignment = Assignment(
                            job_id=a_val.job_id,
                            technician_id=a_val.technician_id,
                            start_time=a_val.start,
                            end_time=a_val.end,
                            actual_start=a_val.actual_start,
                            status=a_val.status,
                            is_existing=True,
                        )
                        self.db.add(assignment)
                    else:
                        assignment.start_time = a_val.start
                        assignment.end_time = a_val.end
                        assignment.actual_start = a_val.actual_start
                        assignment.status = a_val.status
                        assignment.is_existing = True
                        stats.records_skipped_or_updated += 1

                    # Update associated Job's assigned technician and scheduled times
                    job = self.db.query(Job).filter_by(id=a_val.job_id).first()
                    if job:
                        job.assigned_technician_id = a_val.technician_id
                        job.scheduled_start = a_val.start
                        job.scheduled_end = a_val.end
                        job.status = a_val.status

                    stats.existing_assignments_imported += 1
                except ValidationError as ve:
                    stats.errors.append(f"Invalid assignment for job {item.get('job_id')}: {ve.errors()}")
                except Exception as e:
                    stats.errors.append(f"Error importing assignment for job {item.get('job_id')}: {str(e)}")

            self.db.flush()
        except Exception as e:
            stats.errors.append(f"Failed to read existing_assignments.json: {str(e)}")

    def _load_disruptions(self, stats: ImportStats) -> None:
        disruptions_file = self.data_dir / "disruptions.json"
        if not disruptions_file.exists():
            stats.errors.append("disruptions.json file missing")
            return

        try:
            with open(disruptions_file, "r", encoding="utf-8") as f:
                disruptions_data = json.load(f)

            for item in disruptions_data:
                try:
                    d_val = DisruptionScenarioSchema(**item)
                    disruption = self.db.query(DisruptionScenario).filter_by(id=d_val.id).first()
                    if not disruption:
                        disruption = DisruptionScenario(
                            id=d_val.id,
                            category=d_val.category,
                            type=d_val.type,
                            name=d_val.name,
                            effective_at=d_val.effective_at,
                            payload=d_val.payload,
                            expected_behaviour=d_val.expected_behaviour,
                        )
                        self.db.add(disruption)
                    else:
                        disruption.category = d_val.category
                        disruption.type = d_val.type
                        disruption.name = d_val.name
                        disruption.effective_at = d_val.effective_at
                        disruption.payload = d_val.payload
                        disruption.expected_behaviour = d_val.expected_behaviour
                        stats.records_skipped_or_updated += 1
                    stats.disruptions_imported += 1
                except ValidationError as ve:
                    stats.errors.append(f"Invalid disruption {item.get('id')}: {ve.errors()}")
                except Exception as e:
                    stats.errors.append(f"Error importing disruption {item.get('id')}: {str(e)}")

            self.db.flush()
        except Exception as e:
            stats.errors.append(f"Failed to read disruptions.json: {str(e)}")
