import sys
import subprocess
from pathlib import Path

# List your independent scripts here
scripts = ["champ_rosters.py", "export_finishes.py"]

# Path to the directory where your scripts live
tools_dir = Path(__file__).resolve().parent

for script in scripts:
    print(f"Running {script} from {tools_dir} ...")
    subprocess.run([sys.executable, script], check=True, cwd=tools_dir)
    print(f"Finished {script}\n")