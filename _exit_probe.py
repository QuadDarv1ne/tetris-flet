import subprocess, sys, datetime
p = subprocess.run([sys.executable, "tetris_flet.py"],
                   capture_output=True, text=True)
with open("exit_info.txt", "w", encoding="utf-8") as f:
    f.write(f"time={datetime.datetime.now()}\n")
    f.write(f"returncode={p.returncode}\n")
    f.write(f"--- stdout ---\n{p.stdout[-3000:]}\n")
    f.write(f"--- stderr ---\n{p.stderr[-3000:]}\n")
