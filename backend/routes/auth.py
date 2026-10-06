import re
import secrets
import sqlite3
import time
import uuid
from flask import Blueprint, current_app, g, jsonify, request, session
from services.auth_service import store, create_user, authenticate_user, begin_session, actor
from services.store import now

bp=Blueprint('auth',__name__)

def payload():
    data=request.get_json(silent=True)
    if not isinstance(data,dict): raise ValueError('A JSON object is required')
    return data

def public_user():
    if not g.user: return None
    return {k:g.user[k] for k in ['email','role']}

@bp.get('/api/session')
def state():
    if not session.get('csrf'): session['csrf']=secrets.token_urlsafe(32)
    return jsonify(user=public_user(),csrf=session['csrf'],demo=bool(session.get('demo')),demo_available=current_app.config['DEMO_MODE'],storage='Firestore' if store().cloud else 'SQLite',session_minutes=30)

@bp.post('/api/login')
def login():
    d=payload()
    email=d.get('email','')
    password=d.get('password','')
    if not isinstance(email,str) or not isinstance(password,str) or len(email)>160 or len(password)>256: raise ValueError('Invalid credentials')
    user=authenticate_user(email.strip().lower(),password)
    if not user: return jsonify(error='Invalid email or password. Cloud accounts must have a verified email.'),401
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
    if not current_app.config['DEMO_MODE']: return jsonify(error='Demo is disabled'),404
    role=payload().get('role','admin')
    if role not in ['admin','staff','student']: raise ValueError('Invalid demo role')
    store().purge_demo()
    workspace='demo-'+uuid.uuid4().hex
    user={'id':uuid.uuid4().hex,'email':'student.demo@example.test' if role=='student' else role+'.demo@example.test','role':role}
    begin_session(user,workspace,True)
    names=['Aarav Sharma','Diya Rao','Kabir Patel','Ananya Reddy','Rohan Das','Meera Shah','Arjun Kumar','Isha Singh','Dev Malhotra','Sara Joseph','Vivaan Nair','Nisha Verma']
    departments=['Computer Science','Electronics','Mechanical','Civil','Business']
    students=[]
    for i,name in enumerate(names):
        students.append(dict(student_id=f'STU-{2026001+i}',name=name,email='student.demo@example.test' if i==0 else name.lower().replace(' ','.')+'@example.test',department=departments[i%5],cgpa=round(6.5+(i%6)*.55,2),year=i%4+1,status='Graduated' if i==8 else 'Active',consent=i not in [2,6],retention_date='2025-12-31' if i==4 else '2028-06-30',created_at=now(),updated_at=now(),archived=False))
    store().write_many(workspace,students,create=True)
    store().audit(workspace,'Demo workspace created',actor(),role)
    return jsonify(user=public_user(),csrf=session['csrf'])
