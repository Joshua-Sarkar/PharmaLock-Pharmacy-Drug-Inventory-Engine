import os
import subprocess
import sys

if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    target_dir = os.path.join(here, "pharmalock")
    script = os.path.join(target_dir, "smoke_test.py")
    ret = subprocess.call([sys.executable, script], cwd=target_dir)
    sys.exit(ret)
