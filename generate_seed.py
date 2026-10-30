#!/usr/bin/env python3
"""
DispatchGrid seed data generator (deterministic, stdlib only).

Usage:
    python generate_seed.py                       # writes JSON files to ./data
    python generate_seed.py --out data --sqlite seed.db   # also loads a SQLite DB

Outputs (in --out):
    meta.json                 scheduling clock, zones, skills, conventions
    technicians.json          20 technicians
    jobs.json                 108 jobs (100 pending + 4 completed + 3 in_progress + 1 cancelled)
    existing_assignments.json assignments that already exist at "as_of"
    disruptions.json          disruption + reliability test scenarios

The same seed always produces the same data.
"""
import argparse
import json
import math
import random
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

SEED = 2026
IST = timezone(timedelta(hours=5, minutes=30))
DAY1 = datetime(2026, 11, 2, tzinfo=IST)   # Monday
DAY2 = DAY1 + timedelta(days=1)             # Tuesday
AS_OF = DAY1.replace(hour=10)               # "now" for the scheduling engine
TRAVEL_SPEED_KMH = 30

PRIORITY_LABEL = {1: "urgent", 2: "high", 3: "medium", 4: "low"}


def at(day, hhmm):
    h, m = map(int, hhmm.split(":"))
    return day.replace(hour=h, minute=m, second=0, microsecond=0)


def iso(dt):
    return dt.isoformat()


# --------------------------------------------------------------------------
# Zones, skills, equipment
# --------------------------------------------------------------------------
ZONES = {
    "Z1": ("Central", 12.3052, 76.6552),
    "Z2": ("North", 12.3550, 76.6400),
    "Z3": ("South", 12.2500, 76.6450),
    "Z4": ("East", 12.3000, 76.7200),
    "Z5": ("West", 12.3000, 76.5700),
    "Z6": ("Outskirts", 12.4500, 76.8500),  # no technician is eligible here
}
ADJACENT = {
    "Z1": ["Z2", "Z3", "Z4", "Z5"],
    "Z2": ["Z1", "Z4", "Z5"],
    "Z3": ["Z1", "Z4", "Z5"],
    "Z4": ["Z1", "Z2", "Z3"],
    "Z5": ["Z1", "Z2", "Z3"],
    "Z6": [],
}
SKILLS = ["electrical", "plumbing", "hvac", "networking", "appliance_repair",
          "solar", "cctv", "elevator"]
SKILL_EQUIP = {
    "electrical": "multimeter", "plumbing": "pipe_wrench", "hvac": "hvac_gauge",
    "solar": "ladder", "cctv": "ladder", "elevator": "scissor_lift",
    "appliance_repair": "appliance_toolkit", "networking": None,
}
TITLES = {
    "electrical": ["Faulty wiring inspection", "Circuit breaker replacement", "Power outage in unit", "Switchboard upgrade"],
    "plumbing": ["Leaking pipe repair", "Water heater fault", "Blocked drain clearance", "Pressure pump service"],
    "hvac": ["AC not cooling", "Chiller service", "Ventilation duct cleaning", "Thermostat replacement"],
    "networking": ["Wi-Fi dead zone fix", "Router/switch configuration", "LAN cabling job", "Firewall setup"],
    "appliance_repair": ["Washing machine repair", "Refrigerator compressor check", "Oven not heating", "Dishwasher fault"],
    "solar": ["Rooftop panel installation", "Inverter fault diagnosis", "Panel cleaning and inspection", "Battery bank service"],
    "cctv": ["CCTV camera installation", "DVR/NVR fault", "Camera realignment", "Access control setup"],
    "elevator": ["Elevator annual inspection", "Door sensor fault", "Cabin vibration check"],
}
DURATIONS = {
    "electrical": [45, 60, 90, 120], "plumbing": [45, 60, 90, 120],
    "hvac": [60, 90, 120, 150], "networking": [45, 60, 90],
    "appliance_repair": [30, 45, 60, 90], "solar": [120, 150, 180, 240],
    "cctv": [60, 90, 120], "elevator": [90, 120, 180],
}
CUSTOMER_A = ["Sunrise", "Maple", "Orchid", "Heritage", "Lotus", "Cedar", "Pioneer", "Greenfield",
              "Silverline", "Royal", "Coastal", "Hillview", "Metro", "Evergreen", "Bluebird"]
CUSTOMER_B = ["Apartments", "Clinic", "Bakery", "Textiles", "Residency", "Hotel", "School",
              "Logistics", "Mall", "Offices", "Hospital", "Showroom", "Foods", "Labs", "Villas"]
STREETS = ["MG Road", "Temple Street", "Lake View Road", "Station Road", "Ring Road",
           "Market Street", "Palace Road", "Garden Lane", "Industrial Estate Road"]


# --------------------------------------------------------------------------
# Technicians
# --------------------------------------------------------------------------
def shifts(d1=None, d2=None):
    out = []
    for day, s in ((DAY1, d1), (DAY2, d2)):
        if s:
            out.append({"date": day.date().isoformat(),
                        "start": iso(at(day, s[0])), "end": iso(at(day, s[1]))})
    return out


def unav(day, s, e, reason):
    return {"start": iso(at(day, s)), "end": iso(at(day, e)), "reason": reason}


def tech(tid, name, home, zones, skills, d1, d2, ot_max, unavailable=None, extra_equip=()):
    equip = {SKILL_EQUIP[s] for s in skills if SKILL_EQUIP[s]} | set(extra_equip)
    _, lat, lng = ZONES[home]
    return {
        "id": tid, "name": name, "home_zone_id": home,
        "home_location": {"lat": round(lat, 5), "lng": round(lng, 5)},
        "eligible_zones": zones, "skills": skills, "equipment": sorted(equip),
        "shifts": shifts(d1, d2),
        "unavailable_periods": unavailable or [],
        "overtime": {"allowed": ot_max > 0, "max_minutes_per_shift": ot_max},
    }


def build_technicians():
    S9, S8, S10 = ("09:00", "18:00"), ("08:00", "16:00"), ("10:00", "19:00")
    return [
        tech("T01", "Arjun Rao", "Z1", ["Z1", "Z2"], ["electrical", "solar"], S9, S9, 60),
        tech("T02", "Meera Nair", "Z1", ["Z1", "Z4"], ["hvac", "appliance_repair"], S9, S9, 0,
             [unav(DAY1, "14:00", "18:00", "training")]),
        tech("T03", "Karthik Gowda", "Z2", ["Z2", "Z1"], ["plumbing"], S8, S8, 60),
        tech("T04", "Divya Shetty", "Z2", ["Z2", "Z1", "Z5"], ["networking", "cctv"], S9, S9, 0,
             extra_equip=["fiber_splicer"]),
        tech("T05", "Suresh Kumar", "Z3", ["Z3", "Z1"], ["electrical"], S8, S8, 120,
             [unav(DAY2, "09:00", "13:00", "personal_leave")]),
        tech("T06", "Anita Desai", "Z3", ["Z3", "Z5"], ["plumbing", "appliance_repair"], S9, S9, 0),
        tech("T07", "Rahul Patil", "Z4", ["Z4", "Z1"], ["hvac"], S9, S9, 60,
             [unav(DAY1, "12:00", "14:00", "vehicle_service")]),
        tech("T08", "Priya Menon", "Z4", ["Z4", "Z2"], ["networking"], ("08:00", "17:00"), ("08:00", "17:00"), 0),
        tech("T09", "Imran Khan", "Z5", ["Z5", "Z1"], ["electrical", "cctv"], S9, None, 60),
        tech("T10", "Lakshmi Iyer", "Z5", ["Z5", "Z3"], ["solar", "electrical"], S9, S9, 0),
        tech("T11", "Vikram Singh", "Z1", ["Z1", "Z2", "Z3", "Z4", "Z5"], ["elevator", "electrical"], S9, S9, 120),
        tech("T12", "Naveen Reddy", "Z4", ["Z4", "Z1", "Z2"], ["elevator", "hvac"], S10, S10, 60),
        tech("T13", "Sanjana Hegde", "Z1", ["Z1", "Z3"], ["cctv", "networking"], S9, S9, 0,
             [unav(DAY2, "15:00", "18:00", "training")], extra_equip=["fiber_splicer"]),
        tech("T14", "Deepak Joshi", "Z2", ["Z2", "Z4"], ["hvac", "plumbing"], ("08:00", "17:00"), ("08:00", "17:00"), 60),
        tech("T15", "Farah Sheikh", "Z3", ["Z3", "Z1"], ["networking", "solar"], S9, None, 0),
        tech("T16", "Gopal Krishna", "Z5", ["Z5", "Z1", "Z3"], ["plumbing", "hvac"], None, S9, 60),
        tech("T17", "Harini Pillai", "Z4", ["Z4", "Z1", "Z2"], ["electrical", "appliance_repair"], S8, S8, 0),
        tech("T18", "Manoj Bhat", "Z1", ["Z1"], ["plumbing", "electrical"], ("12:00", "18:00"), ("12:00", "18:00"), 0),
        tech("T19", "Nisha Verma", "Z5", ["Z5", "Z3", "Z1"], ["appliance_repair", "networking"],
             ("13:00", "21:00"), ("13:00", "21:00"), 60),
        tech("T20", "Omkar Jadhav", "Z3", ["Z3", "Z4"], ["solar", "cctv", "hvac"], S9, S9, 120,
             [unav(DAY1, "09:00", "11:00", "vehicle_service")]),
    ]


# --------------------------------------------------------------------------
# Jobs
# --------------------------------------------------------------------------
def haversine_km(a, b):
    r = 6371.0
    p1, p2 = math.radians(a["lat"]), math.radians(b["lat"])
    dphi = p2 - p1
    dl = math.radians(b["lng"] - a["lng"])
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def eligible_techs(job, techs):
    return [t["id"] for t in techs
            if job["zone_id"] in t["eligible_zones"]
            and set(job["required_skills"]) <= set(t["skills"])
            and set(job["required_equipment"]) <= set(t["equipment"])]


def make_job(rng, title, zone, skills, equip, prio, dur, ws, we, sla, tags=None):
    _, lat, lng = ZONES[zone]
    loc = {"lat": round(lat + rng.uniform(-0.018, 0.018), 5),
           "lng": round(lng + rng.uniform(-0.018, 0.018), 5)}
    loc["address"] = f"{rng.randint(1, 240)} {rng.choice(STREETS)}, {ZONES[zone][0]}, Mysuru"
    return {
        "id": None,
        "idempotency_key": None,
        "customer_name": f"{rng.choice(CUSTOMER_A)} {rng.choice(CUSTOMER_B)}",
        "title": title,
        "zone_id": zone,
        "location": loc,
        "priority": prio,
        "priority_label": PRIORITY_LABEL[prio],
        "duration_minutes": dur,
        "required_skills": list(skills),
        "required_equipment": sorted(equip),
        "time_window_start": iso(ws),
        "time_window_end": iso(we),
        "sla_deadline": iso(sla),
        "status": "pending",
        "assigned_technician_id": None,
        "scheduled_start": None,
        "scheduled_end": None,
        "created_at": iso(AS_OF - timedelta(minutes=rng.randrange(60, 2880, 15))),
        "tags": tags or [],
    }


def window(rng, day, prio, dur):
    lo, hi = (630, 930) if day is DAY1 else (540, 960)
    ws = rng.randrange(lo, hi + 1, 15)
    extra = {1: (30, 60), 2: (45, 180), 3: (90, 300), 4: (180, 420)}[prio]
    we = min(ws + dur + rng.randrange(extra[0], extra[1] + 1, 15), 19 * 60 + 30)
    if we - ws < dur + 15:
        ws = we - dur - 15
    return day + timedelta(minutes=ws), day + timedelta(minutes=we)


COMBOS = [
    (("electrical",), 14), (("plumbing",), 12), (("hvac",), 12), (("networking",), 10),
    (("appliance_repair",), 10), (("solar",), 7), (("cctv",), 8), (("elevator",), 3),
    (("electrical", "solar"), 2), (("networking", "cctv"), 3), (("hvac", "plumbing"), 2),
    (("plumbing", "appliance_repair"), 1), (("solar", "cctv"), 1), (("electrical", "cctv"), 1),
]


def regular_jobs(rng, techs, n):
    out = []
    while len(out) < n:
        zone = rng.choices(["Z1", "Z2", "Z3", "Z4", "Z5"], [30, 17, 17, 18, 18])[0]
        skills = rng.choices([c for c, _ in COMBOS], [w for _, w in COMBOS])[0]
        prio = rng.choices([1, 2, 3, 4], [8, 22, 45, 25])[0]
        dur = max(rng.choice(DURATIONS[s]) for s in skills) + (30 if len(skills) > 1 else 0)
        primary = skills[0]
        equip = set()
        if primary == "elevator":
            equip.add("scissor_lift")
        elif primary == "networking":
            if rng.random() < 0.3:
                equip.add("fiber_splicer")
        elif SKILL_EQUIP[primary] and rng.random() < 0.35:
            equip.add(SKILL_EQUIP[primary])
        day = DAY1 if rng.random() < 0.55 else DAY2
        ws, we = window(rng, day, prio, dur)
        slack = {1: (30, 90), 2: (60, 180), 3: (120, 360), 4: (240, 720)}[prio]
        sla = min(we, ws + timedelta(minutes=dur + rng.randrange(slack[0], slack[1] + 1, 15)))
        title = TITLES[primary][rng.randrange(len(TITLES[primary]))]
        if len(skills) > 1:
            title += f" + {skills[1].replace('_', ' ')}"
        job = make_job(rng, title, zone, skills, equip, prio, dur, ws, we, sla)
        if eligible_techs(job, techs):  # regular jobs are always theoretically assignable
            out.append(job)
    return out


def special_jobs(rng):
    """Hand-designed jobs: conflicts, contention, and jobs that cannot be assigned."""
    J = []

    def add(title, zone, skills, equip, prio, dur, ws, we, sla, tags):
        J.append(make_job(rng, title, zone, skills, equip, prio, dur, ws, we, sla, tags))

    # -- Two high-priority jobs competing for the same slot (3 pairs) --------------
    for _ in range(2):
        add("Elevator stuck between floors", "Z1", ["elevator"], ["scissor_lift"], 1, 90,
            at(DAY1, "12:30"), at(DAY1, "14:30"), at(DAY1, "14:15"), ["conflict_pair_A"])
    for _ in range(2):
        add("Main distribution panel tripping", "Z3", ["electrical"], ["multimeter"], 1, 60,
            at(DAY1, "15:00"), at(DAY1, "16:30"), at(DAY1, "16:15"), ["conflict_pair_B"])
    for _ in range(2):  # only T04 can serve Z2 + fiber_splicer -> one cannot fit
        add("Fibre backbone outage", "Z2", ["networking"], ["fiber_splicer"], 1, 60,
            at(DAY2, "10:00"), at(DAY2, "11:30"), at(DAY2, "11:15"), ["conflict_pair_C"])

    # -- Resource crunch: 6 HVAC jobs in the East zone, same afternoon --------------
    for p in [1, 1, 2, 2, 2, 2]:
        sla = at(DAY1, "14:30") if p == 1 else at(DAY1, "16:00")
        add("Server room AC failure" if p == 1 else "AC not cooling", "Z4", ["hvac"], ["hvac_gauge"],
            p, 60, at(DAY1, "13:00"), at(DAY1, "16:00"), sla, ["crowd_east_hvac"])

    # -- Jobs that can never (or should not) be assigned ----------------------------
    add("High-voltage substation maintenance", "Z1", ["high_voltage"], [], 1, 120,
        at(DAY1, "11:00"), at(DAY1, "17:00"), at(DAY1, "16:00"), ["unassignable_missing_skill"])
    add("Heavy panel lift with mobile crane", "Z1", ["electrical"], ["crane"], 2, 120,
        at(DAY2, "10:00"), at(DAY2, "16:00"), at(DAY2, "15:00"), ["unassignable_missing_equipment"])
    add("Remote farm pump-house wiring", "Z6", ["electrical"], [], 3, 90,
        at(DAY2, "09:00"), at(DAY2, "17:00"), at(DAY2, "16:00"), ["unassignable_no_zone_coverage"])
    add("After-hours CCTV audit", "Z1", ["cctv"], [], 4, 60,
        at(DAY1, "22:00"), at(DAY1, "23:30"), at(DAY1, "23:30"), ["unassignable_outside_all_shifts"])
    add("Full plumbing overhaul (long job)", "Z2", ["plumbing"], [], 3, 240,
        at(DAY2, "10:00"), at(DAY2, "12:00"), at(DAY2, "12:00"), ["unassignable_window_shorter_than_duration"])
    add("Elevator + electrical + HVAC retrofit", "Z1", ["elevator", "electrical", "hvac"], ["scissor_lift"], 2, 180,
        at(DAY2, "10:00"), at(DAY2, "17:00"), at(DAY2, "16:00"), ["unassignable_no_single_tech_with_all_skills"])
    add("Solar inverter outage (early slot)", "Z4", ["solar"], ["ladder"], 2, 45,
        at(DAY2, "09:00"), at(DAY2, "09:50"), at(DAY2, "09:50"), ["unassignable_cannot_reach_in_time"])
    add("AC down - already past SLA", "Z1", ["hvac"], ["hvac_gauge"], 2, 60,
        at(DAY1, "09:00"), at(DAY1, "13:00"), at(DAY1, "09:30"), ["sla_already_breached_assign_late"])
    return J


def existing_jobs(rng):
    """Completed, in-progress and cancelled jobs that exist before scheduling starts."""
    def job(title, zone, skills, equip, prio, dur, tid, start, end, status, actual_start=None):
        ws, we = at(DAY1, "08:00"), at(DAY1, "13:00")
        j = make_job(rng, title, zone, skills, equip, prio, dur, ws, we, we, ["pre_existing"])
        j["status"] = status
        j["assigned_technician_id"] = tid
        j["scheduled_start"] = iso(start) if start else None
        j["scheduled_end"] = iso(end) if end else None
        j["actual_start"] = iso(actual_start) if actual_start else None
        return j

    return [
        job("Blocked drain clearance", "Z2", ["plumbing"], [], 3, 75, "T03", at(DAY1, "08:00"), at(DAY1, "09:15"), "completed", at(DAY1, "08:00")),
        job("Thermostat replacement", "Z2", ["hvac"], [], 3, 75, "T14", at(DAY1, "08:15"), at(DAY1, "09:30"), "completed", at(DAY1, "08:15")),
        job("Circuit breaker replacement", "Z3", ["electrical"], [], 2, 60, "T05", at(DAY1, "08:00"), at(DAY1, "09:00"), "completed", at(DAY1, "08:00")),
        job("Router/switch configuration", "Z4", ["networking"], [], 3, 90, "T08", at(DAY1, "08:00"), at(DAY1, "09:30"), "completed", at(DAY1, "08:00")),
        job("Switchboard upgrade", "Z3", ["electrical"], [], 2, 120, "T05", at(DAY1, "09:30"), at(DAY1, "11:30"), "in_progress", at(DAY1, "09:30")),
        job("Chiller service", "Z4", ["hvac"], [], 2, 60, "T07", at(DAY1, "09:45"), at(DAY1, "10:45"), "in_progress", at(DAY1, "09:45")),
        job("Rooftop panel installation", "Z5", ["solar"], [], 3, 150, "T10", at(DAY1, "09:30"), at(DAY1, "12:00"), "in_progress", at(DAY1, "09:30")),
        job("Washing machine repair", "Z1", ["appliance_repair"], [], 4, 45, None, None, None, "cancelled"),
    ]


# --------------------------------------------------------------------------
# Disruption + reliability scenarios
# --------------------------------------------------------------------------
def build_disruptions(jobs, regular_ids):
    by_id = {j["id"]: j for j in jobs}
    d1 = [by_id[i] for i in regular_ids
          if datetime.fromisoformat(by_id[i]["time_window_start"]).date() == DAY1.date()
          and by_id[i]["priority"] >= 3]
    dur_job = next(j for j in d1 if j["duration_minutes"] <= 90 and j["time_window_start"] >= iso(at(DAY1, "11:30")))
    cancel_job = next(j for j in d1 if j["id"] != dur_job["id"] and j["time_window_start"] >= iso(at(DAY1, "11:30")))

    new_job = lambda key, title, zone, skills, equip, prio, dur, ws, we, sla: {
        "idempotency_key": key, "customer_name": "Walk-in Priority Client", "title": title,
        "zone_id": zone, "priority": prio, "duration_minutes": dur,
        "required_skills": skills, "required_equipment": equip,
        "time_window_start": iso(ws), "time_window_end": iso(we), "sla_deadline": iso(sla),
        "location": {"lat": ZONES[zone][1], "lng": ZONES[zone][2], "address": f"Central point, {ZONES[zone][0]}, Mysuru"},
    }
    dup_payload = new_job("dup-test-0001", "Duplicate-submission test job", "Z1", ["plumbing"], ["pipe_wrench"], 3, 60,
                          at(DAY2, "11:00"), at(DAY2, "15:00"), at(DAY2, "14:00"))
    return [
        {"id": "D01", "category": "disruption", "type": "technician_unavailable", "name": "Senior elevator technician goes down",
         "effective_at": iso(at(DAY1, "11:00")),
         "payload": {"technician_id": "T11", "unavailable_from": iso(at(DAY1, "12:00")), "unavailable_to": iso(at(DAY2, "18:00")), "reason": "vehicle_breakdown"},
         "expected_behaviour": "T11's future jobs are reassigned. Elevator work moves to T12 only; conflict_pair_A can no longer both be served on time, so one job is late or unassigned with a specific reason. In-progress work is untouched."},
        {"id": "D02", "category": "disruption", "type": "urgent_job_arrives", "name": "Urgent plumbing job arrives mid-morning",
         "effective_at": iso(at(DAY1, "11:30")),
         "payload": {"job": new_job("urgent-0002", "Burst main pipe", "Z1", ["plumbing"], ["pipe_wrench"], 1, 60,
                                   at(DAY1, "11:30"), at(DAY1, "14:00"), at(DAY1, "13:00"))},
         "expected_behaviour": "Job inserted with minimal displacement of existing assignments; report lists exactly which lower-priority jobs moved and why."},
        {"id": "D03", "category": "disruption", "type": "two_urgent_jobs_compete", "name": "Two urgent electrical jobs, same slot",
         "effective_at": iso(at(DAY1, "12:00")),
         "payload": {"jobs": [
             new_job("urgent-0003a", "Transformer fault", "Z3", ["electrical"], ["multimeter"], 1, 60, at(DAY1, "14:00"), at(DAY1, "15:30"), at(DAY1, "15:15")),
             new_job("urgent-0003b", "Panel fire hazard", "Z3", ["electrical"], ["multimeter"], 1, 60, at(DAY1, "14:00"), at(DAY1, "15:30"), at(DAY1, "15:15"))]},
         "expected_behaviour": "Both are assigned to different technicians, or the loser is explained (technician busy / travel too long). A technician is never double-booked."},
        {"id": "D04", "category": "disruption", "type": "job_duration_changed", "name": "Job takes longer than planned",
         "effective_at": iso(at(DAY1, "11:00")),
         "payload": {"job_id": dur_job["id"], "old_duration_minutes": dur_job["duration_minutes"], "new_duration_minutes": dur_job["duration_minutes"] + 90},
         "expected_behaviour": "Downstream jobs for that technician shift or move; unchanged assignments are listed as unchanged."},
        {"id": "D05", "category": "disruption", "type": "job_cancelled", "name": "Customer cancels a job",
         "effective_at": iso(at(DAY1, "11:00")),
         "payload": {"job_id": cancel_job["id"]},
         "expected_behaviour": "Slot freed; previously unassigned jobs may now be placed. Other assignments stay stable."},
        {"id": "D06", "category": "disruption", "type": "invalid_state_transition", "name": "Cancel an already completed job",
         "effective_at": iso(at(DAY1, "10:30")),
         "payload": {"job_id": "JOB-101", "target_status": "cancelled"},
         "expected_behaviour": "Rejected with a clear 4xx error (completed -> cancelled is invalid). No state change."},
        {"id": "D07", "category": "disruption", "type": "technician_finished_early", "name": "Technician finishes 40 minutes early",
         "effective_at": iso(at(DAY1, "10:50")),
         "payload": {"job_id": "JOB-105", "technician_id": "T05", "actual_end": iso(at(DAY1, "10:50"))},
         "expected_behaviour": "Job marked completed; T05 gains 40 minutes; later jobs may be pulled forward only if it reduces cost."},
        {"id": "D08", "category": "disruption", "type": "technician_finished_late", "name": "Technician overruns by one hour",
         "effective_at": iso(at(DAY1, "11:45")),
         "payload": {"job_id": "JOB-106", "technician_id": "T07", "actual_end": iso(at(DAY1, "11:45"))},
         "expected_behaviour": "T07's next jobs are shifted or reassigned, respecting his 12:00-14:00 vehicle service block."},
        {"id": "D09", "category": "disruption", "type": "technician_unavailable_during_in_progress", "name": "Technician leaves while a job is in progress",
         "effective_at": iso(at(DAY1, "10:30")),
         "payload": {"technician_id": "T10", "unavailable_from": iso(at(DAY1, "12:00")), "unavailable_to": iso(at(DAY1, "18:00")), "reason": "emergency_leave"},
         "expected_behaviour": "JOB-107 (in progress until 12:00) is protected and not reassigned. T10's later jobs are reassigned or explained."},
        {"id": "R01", "category": "reliability", "type": "duplicate_request", "name": "Same create-job request submitted twice",
         "effective_at": iso(at(DAY1, "10:00")),
         "payload": {"request": dup_payload, "repeat": 2},
         "expected_behaviour": "Same idempotency_key -> exactly one job created; second call returns the original job (not a duplicate)."},
        {"id": "R02", "category": "reliability", "type": "concurrent_scheduling", "name": "Two schedule-generation requests at once",
         "effective_at": iso(at(DAY1, "10:00")),
         "payload": {"parallel_requests": 2, "endpoint": "generate schedule"},
         "expected_behaviour": "One run commits; the other waits or is rejected. No technician ends up with overlapping or double-committed assignments."},
        {"id": "R03", "category": "reliability", "type": "interrupted_run", "name": "Scheduling run crashes midway",
         "effective_at": iso(at(DAY1, "10:00")),
         "payload": {"simulate_failure_after_assigning": 40},
         "expected_behaviour": "Run recorded as failed; previous committed schedule remains intact (all-or-nothing commit); a retry succeeds."},
    ]


# --------------------------------------------------------------------------
# Assemble + write
# --------------------------------------------------------------------------
def build():
    rng = random.Random(SEED)
    techs = build_technicians()

    pending = special_jobs(rng) + regular_jobs(rng, techs, 80)
    rng.shuffle(pending)
    for i, j in enumerate(pending, start=1):
        j["id"] = f"JOB-{i:03d}"
        j["idempotency_key"] = f"seed-{j['id']}"
    regular_ids = [j["id"] for j in pending if not j["tags"]]

    existing = existing_jobs(rng)
    for i, j in enumerate(existing, start=101):
        j["id"] = f"JOB-{i:03d}"
        j["idempotency_key"] = f"seed-{j['id']}"

    jobs = pending + existing
    assignments = [
        {"job_id": j["id"], "technician_id": j["assigned_technician_id"], "start": j["scheduled_start"],
         "end": j["scheduled_end"], "actual_start": j.get("actual_start"), "status": j["status"]}
        for j in existing if j["assigned_technician_id"]
    ]
    meta = {
        "as_of": iso(AS_OF), "time_zone": "Asia/Kolkata (+05:30)",
        "planning_horizon": {"start": iso(DAY1), "end": iso(DAY2 + timedelta(days=1))},
        "travel_model": {"method": "haversine", "speed_kmh": TRAVEL_SPEED_KMH,
                         "note": "travel_minutes = distance_km / speed_kmh * 60; a technician's first job starts from home_location"},
        "conventions": {
            "time_window": "HARD: service must start >= window_start and end <= window_end",
            "sla_deadline": "SOFT: latest desired completion time; lateness is penalised in the objective",
            "priority": PRIORITY_LABEL, "technician_zones": "HARD: job zone must be in technician eligible_zones",
            "shifts": "HARD (overtime up to overtime.max_minutes_per_shift allowed at a penalty if overtime.allowed)",
            "unavailable_periods": "HARD: no work or overlapping service",
        },
        "zones": {k: {"name": v[0], "lat": v[1], "lng": v[2], "adjacent": ADJACENT[k]} for k, v in ZONES.items()},
        "skills": SKILLS, "unsupported_skills_in_jobs": ["high_voltage"],
        "equipment": sorted({e for e in SKILL_EQUIP.values() if e} | {"fiber_splicer"}),
    }
    return meta, techs, jobs, assignments, build_disruptions(jobs, regular_ids)


def validate(techs, jobs):
    assert len(techs) >= 20 and len({t["id"] for t in techs}) == len(techs)
    pend = [j for j in jobs if j["status"] == "pending"]
    assert len(pend) >= 100 and len({j["id"] for j in jobs}) == len(jobs)
    for j in jobs:
        ws, we = datetime.fromisoformat(j["time_window_start"]), datetime.fromisoformat(j["time_window_end"])
        assert ws < we and datetime.fromisoformat(j["sla_deadline"]) <= we
    unassignable = [j["id"] for j in pend if not eligible_techs(j, techs)]
    return pend, unassignable


SCHEMA = """
CREATE TABLE zones (id TEXT PRIMARY KEY, name TEXT, lat REAL, lng REAL);
CREATE TABLE technicians (id TEXT PRIMARY KEY, name TEXT, home_zone_id TEXT, home_lat REAL, home_lng REAL,
  eligible_zones TEXT, skills TEXT, equipment TEXT, shifts TEXT, unavailable_periods TEXT,
  overtime_allowed INTEGER, max_overtime_minutes INTEGER);
CREATE TABLE jobs (id TEXT PRIMARY KEY, idempotency_key TEXT UNIQUE, customer_name TEXT, title TEXT, zone_id TEXT,
  lat REAL, lng REAL, address TEXT, priority INTEGER, duration_minutes INTEGER, required_skills TEXT,
  required_equipment TEXT, time_window_start TEXT, time_window_end TEXT, sla_deadline TEXT, status TEXT,
  assigned_technician_id TEXT, scheduled_start TEXT, scheduled_end TEXT, created_at TEXT, tags TEXT);
"""


def load_sqlite(path, meta, techs, jobs):
    p = Path(path)
    if p.exists():
        p.unlink()
    con = sqlite3.connect(p)
    con.executescript(SCHEMA)
    js = json.dumps
    con.executemany("INSERT INTO zones VALUES (?,?,?,?)", [(k, v["name"], v["lat"], v["lng"]) for k, v in meta["zones"].items()])
    con.executemany("INSERT INTO technicians VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", [
        (t["id"], t["name"], t["home_zone_id"], t["home_location"]["lat"], t["home_location"]["lng"],
         js(t["eligible_zones"]), js(t["skills"]), js(t["equipment"]), js(t["shifts"]),
         js(t["unavailable_periods"]), int(t["overtime"]["allowed"]), t["overtime"]["max_minutes_per_shift"]) for t in techs])
    con.executemany("INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", [
        (j["id"], j["idempotency_key"], j["customer_name"], j["title"], j["zone_id"], j["location"]["lat"],
         j["location"]["lng"], j["location"]["address"], j["priority"], j["duration_minutes"],
         js(j["required_skills"]), js(j["required_equipment"]), j["time_window_start"], j["time_window_end"],
         j["sla_deadline"], j["status"], j["assigned_technician_id"], j["scheduled_start"], j["scheduled_end"],
         j["created_at"], js(j["tags"])) for j in jobs])
    con.commit()
    con.close()


def main():
    ap = argparse.ArgumentParser(description="Generate DispatchGrid seed data")
    ap.add_argument("--out", default="data", help="output directory (default: ./data)")
    ap.add_argument("--sqlite", help="optional path of a SQLite DB to create and load")
    args = ap.parse_args()

    meta, techs, jobs, assignments, disruptions = build()
    pend, unassignable = validate(techs, jobs)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for name, data in [("meta", meta), ("technicians", techs), ("jobs", jobs),
                       ("existing_assignments", assignments), ("disruptions", disruptions)]:
        (out / f"{name}.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    if args.sqlite:
        load_sqlite(args.sqlite, meta, techs, jobs)

    print(f"technicians: {len(techs)} | jobs: {len(jobs)} (pending {len(pend)}) | "
          f"assignments: {len(assignments)} | disruption/reliability scenarios: {len(disruptions)}")
    print(f"pending jobs with zero eligible technicians (static check): {len(unassignable)}")
    print(f"written to: {out.resolve()}")


if __name__ == "__main__":
    main()
