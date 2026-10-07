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
    new_account(app,'private@example.test')
    rows=other.get('/api/accounts?workspace='+code).json['accounts']
    assert [r['email'] for r in rows]==['other@example.test']
    assert len(other.get('/api/students').json['students'])==12
    for role in ['student','staff']:
        user,_=new_account(app,role+'-private@example.test',role)
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
    assert post(student,'/api/students/'+sid,{'cgpa':10},'put').status_code==403

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
    student,credentials=new_account(app,'student@example.test')
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
    student,_=new_account(app,'student@example.test')
    assert post(student,'/api/campus/join',{'campus_code':'CG-0000000000000000'}).status_code==400
    assert not student.get('/api/session').json['user']['campus_member']
    assert len(student.get('/api/students').json['students'])==1
