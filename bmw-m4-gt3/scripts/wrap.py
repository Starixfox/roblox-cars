# Runs the script given after "--" and writes all output to a .log next to it.
import sys, runpy, traceback, os

args = sys.argv[sys.argv.index("--") + 1:]
script = args[0]
# only short plain-word args (like "high") go into the log name, never paths
words = [a for a in args[1:] if a.isidentifier() and len(a) <= 12]
suffix = ("_" + "_".join(words)) if words else ""
log_path = os.path.splitext(script)[0] + suffix + ".log"
log = open(log_path, "w", buffering=1)
sys.stdout = log
sys.stderr = log
sys.argv = [script] + args[1:]
try:
    runpy.run_path(script, run_name="__main__")
    print("DONE")
except Exception:
    traceback.print_exc()
    print("FAILED")
log.close()
