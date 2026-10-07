import time
from test_app import app,client,post,sample,demo

def new_account(app,email,role='student',code=''):
    client=app.test_client()
    client.environ_base['REMOTE_ADDR']=email
    credentials=dict(email=email,password='AccountPassword123!',role=role,name='Sample '+role.title(),campus_code=code)
    response=post(client,'/api/demo/signup',credentials)
    assert response.status_code==201,response.json
    assert post(client,'/api/demo/login',credentials).status_code==200
    return client,credentials

def legacy_account(app,email,role='student'):
    """Fixture for an account created before campus codes became required."""
    import uuid
    from werkzeug.security import generate_password_hash
    from routes.auth import seed_demo
    uid=uuid.uuid4().hex;workspace='demo-'+uuid.uuid4().hex
    credentials=dict(email=email,password='LegacyPassword123!',role=role,name='Legacy '+role.title())
    with app.app_context():
        store=app.extensions['store']
        with store.db() as db:
            db.execute('INSERT INTO demo_accounts (id,email,password,workspace,expires,role,name,created_at) VALUES (?,?,?,?,?,?,?,?)',(uid,email,generate_password_hash(credentials['password']),workspace,time.time()+86400,role,credentials['name'],time.time()))
        seed_demo(workspace,student_email=email if role=='student' else 'student.demo@example.test',student_name=credentials['name'] if role=='student' else None)
    client=app.test_client();client.environ_base['REMOTE_ADDR']=email
    assert post(client,'/api/demo/login',credentials).status_code==200
    return client,credentials

def test_admin_sees_all_enrolled_accounts_and_students(app):
    owner,_=new_account(app,'owner@example.test','admin')
    code=owner.get('/api/accounts').json['campus_code']
    assert code.startswith('CG-')
    first,_=new_account(app,'first@example.test',code=code)
    second,_=new_account(app,'second@example.test',code=code)
    directory=owner.get('/api/accounts').json
    assert len(directory['accounts'])==3
    students=[a for a in directory['accounts'] if a['role']=='student']
    assert {a['email'] for a in students}=={'first@example.test','second@example.test'}
    assert all(a['student_id'] and a['created_at'] and a['last_seen'] for a in students)
    assert all(a['presence']=='Online' for a in students)
    assert len(owner.get('/api/students').json['students'])==14
    assert len(first.get('/api/students').json['students'])==1
    assert len(second.get('/api/students').json['students'])==1
    other_id=next(a['student_id'] for a in students if a['email']=='second@example.test')
    assert first.get('/api/students/'+other_id).status_code==404
    assert not any('password' in a for a in directory['accounts'])

def test_other_admins_and_personal_accounts_are_not_exposed(app):
    owner,_=new_account(app,'owner@example.test','admin')
    code=owner.get('/api/accounts').json['campus_code']
    student,_=new_account(app,'student@example.test',code=code)
    other,_=new_account(app,'other@example.test','admin')
    legacy_account(app,'private@example.test')
    rows=other.get('/api/accounts?workspace='+code).json['accounts']
    assert [r['email'] for r in rows]==['other@example.test']
    assert len(other.get('/api/students').json['students'])==12
    for role in ['student','staff']:
        user,_=legacy_account(app,role+'-private@example.test',role)
        assert user.get('/api/accounts').status_code==403
    assert student.get('/api/accounts').status_code==403

def test_invite_cannot_grant_staff_or_admin_privileges(app):
    owner,_=new_account(app,'owner@example.test','admin')
    code=owner.get('/api/accounts').json['campus_code']
    for role in ['staff','admin']:
        visitor=app.test_client()
        assert post(visitor,'/api/demo/signup',dict(email=role+'@example.test',password='AccountPassword123!',role=role,campus_code=code)).status_code==400
    visitor=app.test_client()
    assert post(visitor,'/api/demo/signup',dict(email='student@example.test',password='AccountPassword123!',campus_code='CG-INVALID')).status_code==400
    assert len(owner.get('/api/accounts').json['accounts'])==1

def test_enrolled_student_cannot_claim_existing_email_record(app):
    owner,_=new_account(app,'owner@example.test','admin')
    code=owner.get('/api/accounts').json['campus_code']
    student,_=new_account(app,'student.demo@example.test',code=code)
    rows=student.get('/api/students').json['students']
    assert len(rows)==1 and rows[0]['student_id'].startswith('REG-')
    assert student.get('/api/students/STU-2026001').status_code==404
    sid=rows[0]['student_id']
    response=post(owner,'/api/students/'+sid,{'cgpa':8.75,'year':3,'department':'Electronics','account_id':'attacker'},'put')
    assert response.status_code==200
    updated=student.get('/api/students/'+sid).json
    assert updated['cgpa']==8.75 and updated['academic_pending'] is False
    assert updated['account_id']==rows[0]['account_id']
    submitted=post(student,'/api/students/'+sid,{'cgpa':10},'put')
    assert submitted.status_code==200 and submitted.json['academic_pending'] and submitted.json['student_submitted']

def test_online_idle_offline_changes(app):
    owner,_=new_account(app,'owner@example.test','admin')
    code=owner.get('/api/accounts').json['campus_code']
    student,credentials=new_account(app,'student@example.test',code=code)
    def status():
        return next(a for a in owner.get('/api/accounts').json['accounts'] if a['email']==credentials['email'])['presence']
    assert status()=='Online'
    with app.extensions['store'].db() as db:db.execute('UPDATE demo_accounts SET last_seen=? WHERE email=?',(time.time()-60,credentials['email']))
    assert status()=='Idle'
    assert student.get('/api/presence').status_code==200
    assert status()=='Online'
    post(student,'/api/logout')
    assert status()=='Offline'

def test_campus_expiry_and_migration(app):
    owner,_=new_account(app,'owner@example.test','admin')
    code=owner.get('/api/accounts').json['campus_code']
    student,credentials=new_account(app,'student@example.test',code=code)
    with app.extensions['store'].db() as db:
        owner_row=db.execute("SELECT * FROM demo_accounts WHERE role='admin'").fetchone()
        joined=db.execute('SELECT * FROM demo_accounts WHERE email=?',(credentials['email'],)).fetchone()
        assert joined['expires']<=owner_row['expires']
        db.execute('UPDATE campuses SET expires=0')
    assert student.get('/api/students').status_code==401
    visitor=app.test_client()
    assert post(visitor,'/api/demo/signup',dict(email='new@example.test',password='AccountPassword123!',campus_code=code)).status_code==400

def test_preview_cannot_list_real_accounts(app,client):
    new_account(app,'owner@example.test','admin')
    demo(client)
    directory=client.get('/api/accounts').json
    assert directory['sample_preview'] and directory['accounts']==[] and directory['campus_code'] is None

def test_pending_grades_are_not_counted_or_exported(app):
    owner,_=new_account(app,'owner@example.test','admin')
    baseline=owner.get('/api/overview').json['average_cgpa']
    code=owner.get('/api/accounts').json['campus_code']
    student,_=new_account(app,'student@example.test',code=code)
    assert owner.get('/api/overview').json['average_cgpa']==baseline
    import csv,io
    rows=list(csv.DictReader(io.StringIO(owner.get('/api/export?masked=false').data.decode())))
    pending=next(r for r in rows if r['email']=='student@example.test')
    assert pending['cgpa']=='' and pending['year']=='' and pending['department']==''

def test_existing_student_can_join_without_registering_again(app):
    owner,_=new_account(app,'owner@example.test','admin')
    code=owner.get('/api/accounts').json['campus_code']
    student,credentials=legacy_account(app,'student@example.test')
    assert len(owner.get('/api/accounts').json['accounts'])==1
    assert post(student,'/api/campus/join',{'campus_code':code}).status_code==200
    assert student.get('/api/session').json['user']['campus_member']
    assert len(owner.get('/api/accounts').json['accounts'])==2
    assert len(student.get('/api/students').json['students'])==1
    assert post(student,'/api/campus/join',{'campus_code':code}).status_code==409
    assert post(owner,'/api/campus/join',{'campus_code':code}).status_code==403
    post(student,'/api/logout')
    assert post(student,'/api/demo/login',credentials).status_code==200
    assert student.get('/api/session').json['user']['campus_member']
    assert len(student.get('/api/students').json['students'])==1

def test_failed_join_leaves_existing_account_unchanged(app):
    student,_=legacy_account(app,'student@example.test')
    assert post(student,'/api/campus/join',{'campus_code':'CG-0000000000000000'}).status_code==400
    assert not student.get('/api/session').json['user']['campus_member']
    assert len(student.get('/api/students').json['students'])==1


def test_signup_requires_the_correct_role_code(app):
    owner,_=new_account(app,'owner@example.test','admin')
    codes=owner.get('/api/accounts').json['invite_codes']
    assert codes['student'].startswith('CG-STU-') and codes['staff'].startswith('CG-STF-')
    assert codes['student']!=codes['staff']
    for role in ['student','staff']:
        visitor=app.test_client();visitor.environ_base['REMOTE_ADDR']=role
        credentials=dict(email=role+'@example.test',password='RequiredPassword123!',role=role)
        for bad in ['',codes['staff' if role=='student' else 'student'],'CG-INVALID']:
            r=post(visitor,'/api/demo/signup',{**credentials,'campus_code':bad})
            assert r.status_code==400 and role.title() in r.json['error']
        with app.extensions['store'].db() as db:assert db.execute('SELECT 1 FROM demo_accounts WHERE email=?',(credentials['email'],)).fetchone() is None
    assert len(owner.get('/api/accounts').json['accounts'])==1


def test_staff_code_enrolls_staff_without_creating_a_student_record(app):
    owner,_=new_account(app,'owner@example.test','admin')
    codes=owner.get('/api/accounts').json['invite_codes']
    staff,credentials=new_account(app,'staff@example.test','staff',codes['staff'].lower())
    student,_=new_account(app,'student@example.test',code=codes['student'])
    directory=owner.get('/api/accounts').json['accounts']
    row=next(a for a in directory if a['role']=='staff')
    assert row['student_id'] is None and row['presence']=='Online'
    assert len(directory)==3 and len(owner.get('/api/students').json['students'])==13
    rows=staff.get('/api/students').json['students']
    assert len(rows)==13 and all(r['email_masked'] for r in rows)
    assert staff.get('/api/accounts').status_code==403
    assert staff.get('/api/export').status_code==403
    assert staff.get('/api/audit').status_code==403
    assert post(staff,'/api/students',sample('STAFF-ADDED')).status_code==201
    assert post(staff,'/api/students/STAFF-ADDED',method='delete').status_code==403
    assert len(student.get('/api/students').json['students'])==1
    post(staff,'/api/logout')
    assert post(staff,'/api/demo/login',{**credentials,'role':'admin'}).json['user']['role']=='staff'
    other,_=new_account(app,'other-admin@example.test','admin')
    assert len(other.get('/api/accounts').json['accounts'])==1
    assert other.get('/api/students/STAFF-ADDED').status_code==404


def test_existing_staff_requires_staff_code_to_join(app):
    owner,_=new_account(app,'owner@example.test','admin')
    codes=owner.get('/api/accounts').json['invite_codes']
    staff,_=legacy_account(app,'old-staff@example.test','staff')
    assert post(staff,'/api/campus/join',{'campus_code':codes['student']}).status_code==400
    assert not staff.get('/api/session').json['user']['campus_member']
    assert post(staff,'/api/campus/join',{'campus_code':codes['staff']}).status_code==200
    assert staff.get('/api/session').json['user']['campus_member']
    assert len(owner.get('/api/students').json['students'])==12
    assert len(owner.get('/api/accounts').json['accounts'])==2
    assert post(staff,'/api/campus/join',{'campus_code':codes['staff']}).status_code==409


def test_legacy_student_code_migration_preserves_membership_and_codes(app):
    from services.store import Store
    owner,_=new_account(app,'owner@example.test','admin')
    store=app.extensions['store']
    with store.db() as db:
        db.execute("UPDATE campuses SET join_code='CG-1111111111111111',staff_code=''")
    Store(app.config)
    codes=owner.get('/api/accounts').json['invite_codes']
    assert codes['student']=='CG-1111111111111111' and codes['staff'].startswith('CG-STF-')
    new_account(app,'legacy-student@example.test',code=codes['student'])
    Store(app.config)
    assert owner.get('/api/accounts').json['invite_codes']==codes
    assert len(owner.get('/api/accounts').json['accounts'])==2
