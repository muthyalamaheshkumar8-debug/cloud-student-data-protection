"""Encrypted records. SQLite for local/demo; Firestore for cloud records."""
import base64
import hashlib
import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from cryptography.fernet import Fernet


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')

class Store:
    def __init__(self, config):
        self.path = config['DATABASE']
        self.cipher = Fernet(base64.urlsafe_b64encode(hashlib.sha256(config['ENCRYPTION_KEY'].encode()).digest()))
        self.cloud = None
        if config.get('FIREBASE_CREDENTIALS_JSON'):
            import firebase_admin
            from firebase_admin import credentials, firestore
            self.firebase_app = firebase_admin.initialize_app(credentials.Certificate(json.loads(config['FIREBASE_CREDENTIALS_JSON'])), name='campus-'+uuid.uuid4().hex)
            self.cloud = firestore.client(app=self.firebase_app)
        with self.db() as db:
            db.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS demo_accounts (id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, password TEXT NOT NULL, workspace TEXT UNIQUE NOT NULL, expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, password TEXT NOT NULL, role TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, user_id TEXT, expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS limits (bucket TEXT PRIMARY KEY, count INTEGER NOT NULL, start REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS students (workspace TEXT NOT NULL, id TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(workspace,id));
            CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY AUTOINCREMENT, workspace TEXT NOT NULL, payload TEXT NOT NULL);
            ''')
            # Preserve existing hosted accounts while adding signup profiles.
            columns={r['name'] for r in db.execute('PRAGMA table_info(demo_accounts)')}
            if 'role' not in columns:
                db.execute("ALTER TABLE demo_accounts ADD COLUMN role TEXT NOT NULL DEFAULT 'admin'")
            if 'name' not in columns:
                db.execute("ALTER TABLE demo_accounts ADD COLUMN name TEXT NOT NULL DEFAULT ''")
            db.execute('DELETE FROM sessions WHERE expires < ?', (time.time(),))
            db.execute('DELETE FROM limits WHERE start < ?', (time.time()-3600,))

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def encode(self, record):
        return self.cipher.encrypt(json.dumps(record, separators=(',',':')).encode()).decode()

    def decode(self, value):
        return json.loads(self.cipher.decrypt(value.encode()))

    def collection(self, workspace, name):
        return self.cloud.collection('workspaces').document(workspace).collection(name)

    def records(self, workspace):
        if self.cloud and workspace == 'institution':
            return [self.decode(d.to_dict()['payload']) for d in self.collection(workspace, 'students').stream()]
        with self.db() as db:
            return [self.decode(r['payload']) for r in db.execute('SELECT payload FROM students WHERE workspace=?', (workspace,))]

    def get(self, workspace, sid):
        if self.cloud and workspace == 'institution':
            d = self.collection(workspace, 'students').document(sid).get()
            return self.decode(d.to_dict()['payload']) if d.exists else None
        with self.db() as db:
            r = db.execute('SELECT payload FROM students WHERE workspace=? AND id=?', (workspace,sid)).fetchone()
            return self.decode(r['payload']) if r else None

    def write_many(self, workspace, records, create=False):
        if self.cloud and workspace == 'institution':
            batch = self.cloud.batch()
            for r in records:
                ref = self.collection(workspace, 'students').document(r['student_id'])
                (batch.create if create else batch.set)(ref, {'payload':self.encode(r)})
            batch.commit()
        else:
            with self.db() as db:
                for r in records:
                    sql = 'INSERT INTO students VALUES (?,?,?)' if create else 'INSERT INTO students VALUES (?,?,?) ON CONFLICT(workspace,id) DO UPDATE SET payload=excluded.payload'
                    db.execute(sql, (workspace,r['student_id'],self.encode(r)))

    def audit(self, workspace, action, actor, role, target='—'):
        record = dict(action=action, actor=actor, role=role, target=target, time=now(), id=uuid.uuid4().hex[:12])
        if self.cloud and workspace == 'institution':
            self.collection(workspace,'audit').document(record['id']).create({'payload':self.encode(record),'time':record['time']})
        else:
            with self.db() as db:
                db.execute('INSERT INTO audit(workspace,payload) VALUES (?,?)', (workspace,self.encode(record)))

    def events(self, workspace):
        if self.cloud and workspace == 'institution':
            from google.cloud.firestore import Query
            return [self.decode(d.to_dict()['payload']) for d in self.collection(workspace,'audit').order_by('time', direction=Query.DESCENDING).limit(200).stream()]
        with self.db() as db:
            return [self.decode(r['payload']) for r in db.execute('SELECT payload FROM audit WHERE workspace=? ORDER BY id DESC LIMIT 200',(workspace,))]

    def limited(self, bucket, cap=10, window=60):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            r = db.execute('SELECT * FROM limits WHERE bucket=?', (bucket,)).fetchone()
            t = time.time()
            if not r or t-r['start'] >= window:
                db.execute('INSERT OR REPLACE INTO limits VALUES (?,1,?)',(bucket,t))
                return False
            db.execute('UPDATE limits SET count=count+1 WHERE bucket=?',(bucket,))
            return r['count'] >= cap

    def purge_demo(self):
        # Browser demonstration workspaces are temporary; keep one day at most.
        cutoff = datetime.fromtimestamp(time.time()-86400, timezone.utc).isoformat()
        with self.db() as db:
            expired = [r['workspace'] for r in db.execute('SELECT workspace FROM demo_accounts WHERE expires <= ?',(time.time(),))]
            db.execute('DELETE FROM sessions WHERE user_id IN (SELECT id FROM demo_accounts WHERE expires <= ?)',(time.time(),))
            db.execute('DELETE FROM demo_accounts WHERE expires <= ?',(time.time(),))
            for row in db.execute("SELECT workspace,payload FROM audit WHERE workspace LIKE 'demo-%'"):
                if self.decode(row['payload'])['time'] < cutoff:
                    expired.append(row['workspace'])
            for workspace in set(expired):
                db.execute('DELETE FROM students WHERE workspace=?',(workspace,))
                db.execute('DELETE FROM audit WHERE workspace=?',(workspace,))
