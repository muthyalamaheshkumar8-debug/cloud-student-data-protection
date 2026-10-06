import os
import secrets
from pathlib import Path
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

def settings():
    production = os.getenv('APP_ENV') == 'production'
    demo = os.getenv('DEMO_MODE', 'true').lower() == 'true'
    root = Path(os.getenv('DATA_DIR', str(Path(__file__).parent / '.data')))
    root.mkdir(parents=True, exist_ok=True)
    def key(name):
        value = os.getenv(name)
        if value:
            if len(value) < 32:
                raise RuntimeError(f'{name} must contain at least 32 characters')
            return value
        if production:
            raise RuntimeError(f'{name} is required in production')
        path = root / name.lower()
        if not path.exists():
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'w') as f:
                f.write(secrets.token_urlsafe(48))
        return path.read_text().strip()
    if production and not demo and not os.getenv('FIREBASE_CREDENTIALS_JSON') and os.getenv('PERSISTENT_STORAGE') != 'true':
        raise RuntimeError('Real data requires Firestore or a persistent DATA_DIR')
    return dict(SECRET_KEY=key('SECRET_KEY'), ENCRYPTION_KEY=key('ENCRYPTION_KEY'),
                DATABASE=str(root/'campus.db'), DEMO_MODE=demo,
                FIREBASE_CREDENTIALS_JSON=os.getenv('FIREBASE_CREDENTIALS_JSON'),
                FIREBASE_WEB_API_KEY=os.getenv('FIREBASE_WEB_API_KEY'),
                SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SECURE=production,
                SESSION_COOKIE_SAMESITE='Lax', PERMANENT_SESSION_LIFETIME=timedelta(minutes=30),
                MAX_CONTENT_LENGTH=512*1024)
