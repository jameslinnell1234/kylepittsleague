#copy records HTML source code into recordbook.html files each week on Tuesdays
#copy first page of waiver adds into transactions_2025.html file each week on Wednesdays (delete all existing first) 
#DONT FORGET TO CHANGE RAMS AND CHARGERS
#copy trades from trades.json to waiver_transactions.json

import sys
import subprocess
from pathlib import Path

# Path to the directory where your scripts live
tools_dir = Path(__file__).resolve().parent

# List the scripts in that directory
scripts = ["export_records.py","h2h_builder.py","transactions_from_html.py"]

for script in scripts:
    print(f"Running {script} from {tools_dir} ...")
    subprocess.run([sys.executable, script], check=True, cwd=tools_dir)
    print(f"Finished {script}\n")