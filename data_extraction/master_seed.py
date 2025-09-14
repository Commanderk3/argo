"""
master_seed.py
Orchestrator: run in order:
1) create_schema.py (optional)
2) seed_floats.py
3) seed_sensors.py
4) seed_profiles.py
5) seed_measurements.py
6) seed_bgc_measurements.py
7) seed_trajectory.py (optional)
"""

import subprocess
import sys
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Updated script order
SCRIPTS = [
    # "create_schema.py",        # optional, can skip if schema exists
    "seed_floats.py",
    "seed_sensors.py",
    "seed_profiles.py",
    "seed_measurements.py",
    "seed_bgc_measurements.py",  # new script
    "seed_trajectory.py"        # optional, can skip
]

def run(script):
    print(f"\n--- running {script} ---")
    res = subprocess.run([sys.executable, script])
    if res.returncode != 0:
        print(f"⚠️ Script {script} exited with code {res.returncode}. Aborting master run.")
        return False
    return True

if __name__ == "__main__":
    for s in SCRIPTS:
        ok = run(s)
        if not ok:
            break
    print("✅ master_seed run finished (check logs above).")