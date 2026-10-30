import argparse
import sys
from pathlib import Path

# Ensure app package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.db.session import SessionLocal
from app.services.dataset_loader import DatasetLoaderService


def run_seed(data_dir: str = None) -> int:
    db = SessionLocal()
    try:
        print("=" * 60)
        print("   DISPATCHGRID HACKATHON DATASET SEED LOADER")
        print("=" * 60)
        loader = DatasetLoaderService(db, data_dir=data_dir)
        print(f"Loading authoritative dataset from: {loader.data_dir.resolve()}...")
        
        stats = loader.load_all()

        print("\n--- IMPORT STATISTICS ---")
        print(f"Zones Imported:               {stats.zones_imported}")
        print(f"Technicians Imported:         {stats.technicians_imported} (Target: 20)")
        print(f"Service Jobs Imported:        {stats.jobs_imported} (Target: 108)")
        print(f"Existing Assignments Loaded: {stats.existing_assignments_imported} (Target: 7)")
        print(f"Disruption Scenarios Loaded:  {stats.disruptions_imported} (Target: 12)")
        print(f"Metadata Keys Synchronized:   {stats.metadata_keys_imported}")
        print(f"Records Skipped / Updated:    {stats.records_skipped_or_updated}")
        print(f"Simulation Reference Clock:   {stats.simulation_clock}")

        if stats.errors:
            print("\nErrors encountered:")
            for err in stats.errors:
                print(f"  [ERROR] {err}")
            return 1

        print("=" * 60)
        print("DATASET INTEGRATION & SEEDING COMPLETED SUCCESSFULLY!")
        print("=" * 60)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed DispatchGrid PostgreSQL database from authoritative dataset.")
    parser.add_argument("--data-dir", type=str, default=None, help="Directory containing dataset JSON files (default: ./data)")
    args = parser.parse_args()
    
    sys.exit(run_seed(data_dir=args.data_dir))
