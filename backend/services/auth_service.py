import hashlib
import secrets
import time
import uuid
import requests
from flask import current_app, g, session
from werkzeug.security import generate_password_hash, check_password_hash

ROLES=('admin','staff','student')

def store():
    return current_app.extensions['store']

def create_user(email, password, role='student'):
    if role not in ROLES: raise ValueError('Invalid role')
    uid=uuid.uuid4().hex
    with store().db() as db:
        db.execute('INSERT INTO users VALUES (?,?,?,?)',(uid,email,generate_password_hash(password),role))
    return {'id':uid,'email':email,'role':role}

def authenticate_user(email, password):
    if store().cloud:
        key=current_app.config.get('FIREBASE_WEB_API_KEY')
        if not key: raise ValueError('Firebase sign-in is not configured')
        try:
            r=requests.post('https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword',params={'key':key},json={'email':email,'password':password,'returnSecureToken':True},timeout=10)
            if r.status_code!=200: return None
            from firebase_admin import auth
            claims=auth.verify_id_token(r.json()['idToken'],check_revoked=True,app=store().firebase_app)
            if not claims.get('email_verified'): return None
            role=claims.get('role','student')
            return {'id':claims['uid'],'email':claims['email'],'role':role if role in ROLES else 'student','auth_time':claims['auth_time']}
        except (requests.RequestException,ValueError): return None
    with store().db() as db:
        row=db.execute('SELECT * FROM users WHERE email=?',(email,)).fetchone()
    # Equal-cost hashing also when the account does not exist.
    dummy=current_app.extensions['dummy_password']
    ok=check_password_hash(row['password'] if row else dummy,password)
    return {'id':row['id'],'email':row['email'],'role':row['role']} if row and ok else None

def begin_session(user, workspace='institution', demo=False):
    old=session.get('sid')
    session.clear()
    sid=secrets.token_urlsafe(32)
    with store().db() as db:
        if old: db.execute('DELETE FROM sessions WHERE id=?',(old,))
        db.execute('INSERT INTO sessions VALUES (?,?,?)',(sid,user['id'],time.time()+1800))
    session.update(sid=sid,uid=user['id'],workspace=workspace,demo=demo,
                   csrf=secrets.token_urlsafe(32),user=user, auth_time=user.get('auth_time',time.time()))
    session.permanent=True
    g.user=user
    g.workspace=workspace

def load_user():
    g.user=None
    g.workspace=session.get('workspace','institution')
    sid=session.get('sid')
    if not sid: return
    with store().db() as db:
        row=db.execute('SELECT * FROM sessions WHERE id=? AND expires>?',(sid,time.time())).fetchone()
        if not row:
            session.clear()
            return
        db.execute('UPDATE sessions SET expires=? WHERE id=?',(time.time()+1800,sid))
        local=db.execute('SELECT id,email,role FROM users WHERE id=?',(row['user_id'],)).fetchone()
    if session.get('demo'):
        if not current_app.config['DEMO_MODE']:
            session.clear()
            return
        if session.get('demo_account'):
            with store().db() as db:
                account=db.execute('SELECT id,email,workspace FROM demo_accounts WHERE id=? AND expires>?',(row['user_id'],time.time())).fetchone()
            if not account or account['workspace'] != g.workspace:
                session.clear()
                return
            g.user={'id':account['id'],'email':account['email'],'role':'admin'}
        else:
            g.user=session.get('user')
    elif store().cloud:
        from firebase_admin import auth
        try:
            u=auth.get_user(row['user_id'],app=store().firebase_app)
            if u.disabled or not u.email_verified or u.tokens_valid_after_timestamp/1000 > session.get('auth_time',0):
                session.clear()
                return
            role=(u.custom_claims or {}).get('role','student')
            g.user={'id':u.uid,'email':u.email,'role':role if role in ROLES else 'student'}
        except auth.UserNotFoundError:
            session.clear()
    elif local:
        g.user=dict(local)
    if not g.user: session.clear()

def actor():
    # Pseudonymous audit identity; no emails/passwords in activity records.
    return 'user-'+hashlib.sha256(g.user['id'].encode()).hexdigest()[:8]
