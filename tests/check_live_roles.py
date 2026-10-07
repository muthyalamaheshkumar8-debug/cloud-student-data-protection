"""Verify all three role permissions and campus enrollment on a deployment."""
from pathlib import Path
import runpy
runpy.run_path(str(Path(__file__).with_name('check_live_campus.py')),run_name='__main__')
