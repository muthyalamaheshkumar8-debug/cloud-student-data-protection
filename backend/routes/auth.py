import re
import secrets
import sqlite3
import time
import uuid
from werkzeug.security import generate_password_hash, check_password_hash
from flask import Blueprint, current_app, g, jsonify, request, session
from services.auth_service import store, create_user, authenticate_user, begin_session, actor
from services.store import now
from utils.validation import validate_student

bp=Blueprint('auth',__name__)

def payload():
    data=request.get_json(silent=True)
    if not isinstance(data,dict): raise ValueError('A JSON object is required')
    return data

def public_user():
    if not g.user: return None
    return {**{k:g.user.get(k,'') for k in ['email','role','name']},'campus_member':bool(g.user.get('campus_member'))}

@bp.get('/api/session')
def state():
    if not session.get('csrf'): session['csrf']=secrets.token_urlsafe(32)
    with store().db() as db:
        local_login=bool(db.execute('SELECT 1 FROM users LIMIT 1').fetchone())
    institution_login=bool((store().cloud and current_app.config.get('FIREBASE_WEB_API_KEY')) or local_login)
    return jsonify(user=public_user(),csrf=session['csrf'],demo=bool(session.get('demo')),demo_available=current_app.config['DEMO_MODE'],institution_login=institution_login,storage='Firestore' if store().cloud else 'SQLite',session_minutes=30,campus_enrollment=bool(session.get('demo_account')))

@bp.post('/api/login')
def login():
    d=payload()
    email=d.get('email','')
    password=d.get('password','')
    if not isinstance(email,str) or not isinstance(password,str) or len(email)>160 or len(password)>256: raise ValueError('Invalid credentials')
    user=authenticate_user(email.strip().lower(),password)
    if not user:
        message='Invalid email or password.'
        if store().cloud: message+=' Cloud accounts must have a verified email.'
        return jsonify(error=message),401
    begin_session(user)
    store().audit(g.workspace,'Signed in',actor(),g.user['role'])
    return jsonify(user=public_user(),csrf=session['csrf'])

@bp.post('/api/register')
def register():
    # Email equality controls student access, so unverified self-signup is unsafe.
    return jsonify(error='Accounts must be provisioned by your institution administrator.'),403

@bp.post('/api/logout')
def logout():
    if g.user:
        store().audit(g.workspace,'Signed out',actor(),g.user['role'])
    with store().db() as db:
        db.execute('DELETE FROM sessions WHERE id=?',(session.get('sid'),))
    session.clear()
    return jsonify(message='Signed out')

@bp.post('/api/demo')
def demo():
    if not current_app.config['DEMO_MODE']: return jsonify(error='Sample access is disabled'),404
    role=payload().get('role','admin')
    if role not in ['admin','staff','student']: raise ValueError('Invalid demo role')
    store().purge_demo()
    workspace='demo-'+uuid.uuid4().hex
    user={'id':uuid.uuid4().hex,'email':'student.demo@example.test' if role=='student' else role+'.demo@example.test','role':role}
    begin_session(user,workspace,True)
    seed_demo(workspace)
    store().audit(workspace,'Sample workspace created',actor(),role)
    return jsonify(user=public_user(),csrf=session['csrf'])

def seed_demo(workspace,student_email='student.demo@example.test',student_name=None):
    names=['Aarav Sharma','Diya Rao','Kabir Patel','Ananya Reddy','Rohan Das','Meera Shah','Arjun Kumar','Isha Singh','Dev Malhotra','Sara Joseph','Vivaan Nair','Nisha Verma']
    departments=['Computer Science','Electronics','Mechanical','Civil','Business']
    if student_name: names[0]=student_name
    students=[]
    for i,name in enumerate(names):
        students.append(dict(student_id=f'STU-{2026001+i}',name=name,email=student_email if i==0 else name.lower().replace(' ','.')+'@example.test',department=departments[i%5],cgpa=round(6.5+(i%6)*.55,2),year=i%4+1,status='Graduated' if i==8 else 'Active',consent=i not in [2,6],retention_date='2025-12-31' if i==4 else '2028-06-30',created_at=now(),updated_at=now(),archived=False))
    store().write_many(workspace,students,create=True)


def demo_credentials():
    d=payload()
    email=d.get('email','')
    password=d.get('password','')
    if not isinstance(email,str) or len(email)>160 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email.strip()):
        raise ValueError('Enter a valid email address')
    if not isinstance(password,str) or not 6<=len(password)<=256:
        raise ValueError('Use a password with 6–256 characters')
    return email.strip().lower(),password

@bp.post('/api/demo/signup')
def demo_signup():
    if not current_app.config['DEMO_MODE']: return jsonify(error='Sample access is disabled'),404
    email,password=demo_credentials()
    d=payload()
    role=d.get('role','student')
    if role not in ['student','staff','admin']: raise ValueError('Choose Student, Staff, or Admin')
    name=d.get('name','')
    if not isinstance(name,str) or len(name.strip())>100: raise ValueError('Use a name with up to 100 characters')
    name=name.strip()
    if 'confirm_password' in d and d['confirm_password'] != password:
        raise ValueError('Passwords do not match')
    code=d.get('campus_code','')
    if not isinstance(code,str) or len(code)>40: raise ValueError('Enter a valid campus code')
    code=code.strip().upper()
    if code and role!='student': raise ValueError('Campus codes are for Student enrollment. Create your own workspace for Staff or Admin access.')
    store().purge_demo()
    uid=uuid.uuid4().hex
    workspace='demo-'+uuid.uuid4().hex
    campus_workspace=''
    created=time.time()
    expires=created+86400
    record=None
    try:
        with store().db() as db:
            if code:
                campus=db.execute("SELECT c.* FROM campuses c JOIN demo_accounts o ON o.id=c.owner_id WHERE c.join_code=? AND c.expires>? AND o.expires>? AND o.role='admin'",(code,created,created)).fetchone()
                if not campus: raise ValueError('Campus code not found or expired. Ask your Admin for the current code.')
                campus_workspace=campus['workspace']
                expires=min(expires,campus['expires'])
                record=validate_student(dict(student_id='REG-'+uid[:20],name=name or 'Registered Student',email=email,department=d.get('department','Computer Science'),year=d.get('year',1)))
                record.update(account_id=uid,academic_pending=True,created_at=now(),updated_at=now(),archived=False)
            db.execute('INSERT INTO demo_accounts (id,email,password,workspace,expires,role,name,campus_workspace,created_at,last_seen) VALUES (?,?,?,?,?,?,?,?,?,?)',(uid,email,generate_password_hash(password),workspace,expires,role,name,campus_workspace,created,0))
            if role=='admin':
                db.execute('INSERT INTO campuses VALUES (?,?,?,?)',(workspace,uid,'CG-'+secrets.token_hex(8).upper(),expires))
            if record:
                db.execute('INSERT INTO students VALUES (?,?,?)',(campus_workspace,record['student_id'],store().encode(record)))
    except sqlite3.IntegrityError:
        return jsonify(error='An account already uses this email. Choose Sign in.'),409
    try:
        if not campus_workspace:
            seed_demo(workspace,student_email=email if role=='student' else 'student.demo@example.test',student_name=name if role=='student' else None)
        store().audit(campus_workspace or workspace,'Student enrolled' if campus_workspace else 'Account created','user-'+uid[:8],role)
    except Exception:
        with store().db() as db:
            db.execute('DELETE FROM demo_accounts WHERE id=?',(uid,))
            db.execute('DELETE FROM students WHERE workspace=?',(workspace,))
            db.execute('DELETE FROM audit WHERE workspace=?',(workspace,))
            db.execute('DELETE FROM campuses WHERE owner_id=?',(uid,))
            if record: db.execute('DELETE FROM students WHERE workspace=? AND id=?',(campus_workspace,record['student_id']))
        raise
    label={'student':'Student','staff':'Staff','admin':'Admin'}[role]
    return jsonify(message=f'{label} account created successfully. Sign in to open your workspace.',role=role,name=name),201

@bp.post('/api/demo/login')
def demo_login():
    if not current_app.config['DEMO_MODE']: return jsonify(error='Sample access is disabled'),404
    email,password=demo_credentials()
    store().purge_demo()
    with store().db() as db:
        row=db.execute('SELECT * FROM demo_accounts WHERE email=? AND expires>?',(email,time.time())).fetchone()
    ok=check_password_hash(row['password'] if row else current_app.extensions['dummy_password'],password)
    if not row or not ok: return jsonify(error='Invalid email or password. Create an account first. If your temporary account expired or the host restarted, create it again.'),401
    begin_session({'id':row['id'],'email':row['email'],'role':row['role'],'name':row['name'],'campus_member':bool(row['campus_workspace'])},row['campus_workspace'] or row['workspace'],True)
    with store().db() as db: db.execute('UPDATE demo_accounts SET last_seen=? WHERE id=?',(time.time(),row['id']))
    session['demo_account']=True
    store().audit(g.workspace,'Signed in',actor(),g.user['role'])
    return jsonify(user=public_user(),csrf=session['csrf'])
