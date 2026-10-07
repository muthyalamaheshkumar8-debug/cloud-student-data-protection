"""Campus-scoped account visibility. Never expose passwords or unrelated signups."""
import time
from datetime import datetime, timezone
from flask import Blueprint, g, jsonify, session, request
from routes.students import require
from services.auth_service import store,actor
from services.store import now
from utils.validation import validate_student
from services.campus_service import enrollment_campus, invitation_codes

bp=Blueprint('accounts',__name__)

def timestamp(value):
    return datetime.fromtimestamp(value,timezone.utc).isoformat(timespec='seconds') if value else None

@bp.get('/api/accounts')
@require('admin')
def accounts():
    current=time.time()
    with store().db() as db:
        if session.get('demo'):
            if not session.get('demo_account'):
                return jsonify(accounts=[],campus_code=None,invite_codes=None,refresh_seconds=5,sample_preview=True)
            campus=db.execute('SELECT join_code,staff_code FROM campuses WHERE owner_id=? AND workspace=? AND expires>?',(g.user['id'],g.workspace,current)).fetchone()
            if not campus:
                return jsonify(error='This account does not administer this campus'),403
            rows=db.execute('''SELECT a.id,a.name,a.email,a.role,a.created_at,a.last_seen,
                EXISTS(SELECT 1 FROM sessions s WHERE s.user_id=a.id AND s.expires>?) AS active_session
                FROM demo_accounts a WHERE (a.id=? OR a.campus_workspace=?) AND a.expires>?
                ORDER BY a.created_at DESC,a.id''',(current,g.user['id'],g.workspace,current)).fetchall()
            code=campus['join_code']
            codes=invitation_codes(campus)
        elif store().cloud:
            return jsonify(error='Firebase accounts are provisioned in Firebase. This account directory is available for the campus signup portal and local institution accounts.'),501
        else:
            rows=db.execute('''SELECT u.id,'' AS name,u.email,u.role,0 AS created_at,
                COALESCE((SELECT MAX(s.expires)-1800 FROM sessions s WHERE s.user_id=u.id),0) AS last_seen,
                EXISTS(SELECT 1 FROM sessions s WHERE s.user_id=u.id AND s.expires>?) AS active_session
                FROM users u ORDER BY u.email''',(current,)).fetchall()
            code=None
            codes=None
    records=store().records(g.workspace)
    linked={r['account_id']:r for r in records if r.get('account_id')}
    result=[]
    for row in rows:
        active=bool(row['active_session'])
        age=current-row['last_seen'] if row['last_seen'] else float('inf')
        presence='Online' if active and age<20 else 'Idle' if active else 'Offline'
        record=linked.get(row['id'])
        result.append(dict(id=row['id'],name=row['name'] or row['email'].split('@')[0],email=row['email'],role=row['role'],created_at=timestamp(row['created_at']),last_seen=timestamp(row['last_seen']),presence=presence,student_id=record['student_id'] if record else None))
    return jsonify(accounts=result,campus_code=code,invite_codes=codes,refresh_seconds=5,sample_preview=False)

@bp.get('/api/presence')
@require()
def presence():
    # load_user records this heartbeat. It reveals no other account details.
    return jsonify(status='ok')

@bp.post('/api/campus/join')
@require('student','staff')
def join():
    if not session.get('demo_account'):
        return jsonify(error='Sign in to a Student or Staff signup account to join a campus.'),403
    data=request.get_json(silent=True)
    code=data.get('campus_code','') if isinstance(data,dict) else ''
    current=time.time()
    with store().db() as db:
        account=db.execute('SELECT * FROM demo_accounts WHERE id=? AND expires>?',(g.user['id'],current)).fetchone()
        if not account: return jsonify(error='Sign in again to join a campus.'),401
        if account['campus_workspace']: return jsonify(error='Your account already belongs to a campus.'),409
        campus=enrollment_campus(db,code,account['role'],current)
        target='—'
        if account['role']=='student':
            record=validate_student(dict(student_id='REG-'+account['id'][:20],name=account['name'] or 'Registered Student',email=account['email'],department='Computer Science'))
            record.update(account_id=account['id'],academic_pending=True,created_at=now(),updated_at=now(),archived=False)
            db.execute('INSERT INTO students VALUES (?,?,?)',(campus['workspace'],record['student_id'],store().encode(record)))
            target=record['student_id']
        db.execute('UPDATE demo_accounts SET campus_workspace=?,expires=? WHERE id=?',(campus['workspace'],min(account['expires'],campus['expires']),account['id']))
        event=dict(action=account['role'].title()+' enrolled',actor=actor(),role=account['role'],target=target,time=now(),id=account['id'][:12])
        db.execute('INSERT INTO audit(workspace,payload) VALUES (?,?)',(campus['workspace'],store().encode(event)))
    session['workspace']=campus['workspace']
    g.workspace=campus['workspace']
    g.user['campus_member']=True
    session['user']=dict(g.user)
    return jsonify(message='Joined your Admin campus successfully. Your account is now visible to the campus Admin.')
