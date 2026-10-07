import csv
import io
import sqlite3
from google.api_core.exceptions import AlreadyExists
from functools import wraps
from flask import Blueprint, g, jsonify, request, session, Response
from services.auth_service import store, actor
from services.store import now
from utils.validation import validate_student, findings, DEPARTMENTS

bp=Blueprint('students',__name__)

def require(*roles):
    def decorator(fn):
        @wraps(fn)
        def wrapped(*args,**kwargs):
            if not g.user: return jsonify(error='Sign in to continue'),401
            if roles and g.user['role'] not in roles:
                store().audit(g.workspace,'Access denied',actor(),g.user['role'])
                return jsonify(error='Your role cannot perform this action'),403
            return fn(*args,**kwargs)
        return wrapped
    return decorator

def visible(r):
    if g.user['role']=='student' and g.user.get('campus_member'):
        return r.get('account_id')==g.user['id']
    return g.user['role']!='student' or r['email']==g.user['email']

def redact(r):
    d=dict(r)
    d['issues']=findings(r)
    # Staff can manage records, but the directory hides other people's emails.
    if g.user['role']=='staff':
        user,domain=d['email'].split('@',1)
        d['email']=user[:1]+'•••@'+domain
        d['email_masked']=True
    return d

def log(action,target='—'):
    store().audit(g.workspace,action,actor(),g.user['role'],target)

def json_payload():
    data=request.get_json(silent=True)
    if not isinstance(data,dict): raise ValueError('A JSON object is required')
    return data

@bp.get('/api/students')
@require()
def listing():
    archived=request.args.get('archived')=='true'
    rows=[redact(r) for r in store().records(g.workspace) if bool(r.get('archived'))==archived and visible(r)]
    log('Directory viewed')
    return jsonify(students=sorted(rows,key=lambda r:r['student_id']),departments=DEPARTMENTS)

@bp.get('/api/students/<sid>')
@require()
def detail(sid):
    r=store().get(g.workspace,sid)
    if not r or not visible(r): return jsonify(error='Record not found'),404
    log('Student record viewed',sid)
    return jsonify(redact(r))

@bp.post('/api/students')
@require('admin','staff')
def create():
    r=validate_student(json_payload())
    if store().get(g.workspace,r['student_id']): return jsonify(error='Student ID already exists'),409
    r.update(created_at=now(),updated_at=now(),archived=False)
    try: store().write_many(g.workspace,[r],create=True)
    except (sqlite3.IntegrityError, AlreadyExists): return jsonify(error='Student ID already exists'),409
    log('Student added',r['student_id'])
    return jsonify(redact(r)),201

@bp.put('/api/students/<sid>')
@require('admin','staff')
def update(sid):
    old=store().get(g.workspace,sid)
    if not old: return jsonify(error='Record not found'),404
    d=json_payload()
    if d.get('student_id',sid)!=sid: raise ValueError('Student ID cannot be changed')
    d['student_id']=sid
    if g.user['role']=='staff':
        # Preserve masked email, never write a mask back into the source record.
        if d.get('email') not in [old['email'],redact(old)['email'],None]:
            return jsonify(error='Only an administrator can change an existing email'),403
        d['email']=old['email']
    r=validate_student({**old,**d})
    if old.get('account_id'): r['account_id']=old['account_id']
    if old.get('academic_pending'): r['academic_pending']='cgpa' not in d and old.get('academic_pending',False)
    r.update(created_at=old['created_at'],updated_at=now(),archived=old.get('archived',False))
    store().write_many(g.workspace,[r])
    log('Student updated',sid)
    return jsonify(redact(r))

@bp.delete('/api/students/<sid>')
@require('admin')
def archive(sid):
    r=store().get(g.workspace,sid)
    if not r: return jsonify(error='Record not found'),404
    r.update(archived=True,updated_at=now())
    store().write_many(g.workspace,[r]); log('Student archived',sid)
    return jsonify(message='Record moved to archive')

@bp.post('/api/students/<sid>/restore')
@require('admin')
def restore(sid):
    r=store().get(g.workspace,sid)
    if not r: return jsonify(error='Record not found'),404
    r.update(archived=False,updated_at=now())
    store().write_many(g.workspace,[r]); log('Student restored',sid)
    return jsonify(message='Record restored')

@bp.get('/api/audit')
@require('admin')
def audit():
    return jsonify(events=store().events(g.workspace))

@bp.get('/api/overview')
@require()
def overview():
    rows=[r for r in store().records(g.workspace) if not r.get('archived') and visible(r)]
    graded=[r for r in rows if not r.get('academic_pending')]
    issues=[dict(student_id=r['student_id'],name=r['name'],issues=findings(r)) for r in rows if findings(r)]
    return jsonify(total=len(rows),graded_count=len(graded),consent=sum(bool(r['consent']) for r in rows),average_cgpa=round(sum(r['cgpa'] for r in graded)/len(graded),2) if graded else 0,review_count=len(issues),issues=issues,departments=[{'name':d,'count':sum(r['department']==d for r in graded)} for d in DEPARTMENTS],archived=sum(bool(r.get('archived')) and visible(r) for r in store().records(g.workspace)))

@bp.get('/api/export')
@require('admin')
def export():
    masked=request.args.get('masked','true')!='false'
    fields=['student_id','name','email','department','year','cgpa','status','consent','retention_date']
    out=io.StringIO(); w=csv.DictWriter(out,fieldnames=fields); w.writeheader()
    for r in store().records(g.workspace):
        if r.get('archived'): continue
        if r.get('academic_pending'): r={**r,'department':'','year':'','cgpa':''}
        r={k:r[k] for k in fields}
        if masked: r['email']='[redacted]'
        # Neutralize spreadsheet formula injection.
        r={k:("'"+v if isinstance(v,str) and v.lstrip().startswith(('=','+','-','@')) else v) for k,v in r.items()}
        w.writerow(r)
    log('Masked CSV exported' if masked else 'Full CSV exported')
    return Response(out.getvalue(),mimetype='text/csv',headers={'Content-Disposition':'attachment; filename=students.csv'})

@bp.post('/api/import')
@require('admin','staff')
def import_csv():
    d=json_payload(); rows=d.get('students')
    if not isinstance(rows,list) or not 1<=len(rows)<=100: raise ValueError('Import 1–100 students at a time')
    parsed=[validate_student(r) for r in rows]
    ids=[r['student_id'] for r in parsed]
    if len(set(ids))!=len(ids): raise ValueError('Duplicate student IDs in import')
    if any(store().get(g.workspace,sid) for sid in ids): return jsonify(error='An imported student ID already exists'),409
    for r in parsed: r.update(created_at=now(),updated_at=now(),archived=False)
    try: store().write_many(g.workspace,parsed,create=True)
    except (sqlite3.IntegrityError, AlreadyExists): return jsonify(error='An imported student ID already exists'),409
    log('CSV imported',f'{len(parsed)} records')
    return jsonify(imported=len(parsed)),201
