"""Run the interface against Gunicorn with a disposable database using jsdom.
This checks DOM behavior and API integration, not visual/browser rendering.
"""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import urllib.request

root=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as temporary:
    env=dict(os.environ,APP_ENV='development',DEMO_MODE='true',DATA_DIR=temporary)
    env.pop('FIREBASE_CREDENTIALS_JSON',None)
    process=subprocess.Popen([sys.executable,'-m','gunicorn','--no-control-socket','--bind','127.0.0.1:5005','--workers','1','--threads','4','app:app'],cwd=root/'backend',env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
    try:
        for attempt in range(30):
            try:
                urllib.request.urlopen('http://127.0.0.1:5005/api/health',timeout=1)
                break
            except Exception:
                time.sleep(.1)
        else:
            raise RuntimeError('Gunicorn did not start')
        script=sys.argv[1] if len(sys.argv)>1 else 'ui_integration.cjs'
        result=subprocess.run(['node',str(root/'tests'/script)],cwd=root)
        sys.exit(result.returncode)
    finally:
        process.terminate()
        process.wait(timeout=10)
