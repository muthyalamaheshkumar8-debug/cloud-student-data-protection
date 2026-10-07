from test_accounts import app, new_account, legacy_account
from test_app import post, sample


def campus(app):
    admin,_=new_account(app,'admin@example.test','admin')
    codes=admin.get('/api/accounts').json['invite_codes']
    student,_=new_account(app,'student@example.test',code=codes['student'])
    sid=student.get('/api/students').json['students'][0]['student_id']
    return admin,student,sid,codes


def test_student_submission_admin_review_and_resubmission(app):
    admin,student,sid,codes=campus(app)
    before=admin.get('/api/overview').json
    details=dict(name='Updated Student',department='Electronics',year=3,cgpa=8.75,consent=True)
    saved=post(student,'/api/students/'+sid,details,'put')
    assert saved.status_code==200 and saved.json['academic_pending'] and saved.json['student_submitted']
    assert admin.get('/api/students/'+sid).json['name']=='Updated Student'
    assert admin.get('/api/overview').json['graded_count']==before['graded_count']
    import csv,io
    exported=next(r for r in csv.DictReader(io.StringIO(admin.get('/api/export?masked=false').data.decode())) if r['student_id']==sid)
    assert exported['cgpa']=='' and exported['department']=='' and exported['year']==''
    staff,_=new_account(app,'staff@example.test','staff',codes['staff'])
    assert post(staff,'/api/students/'+sid,{'cgpa':8.9},'put').json['academic_pending']
    approved=post(admin,'/api/students/'+sid,{'cgpa':9},'put')
    assert approved.status_code==200 and approved.json['academic_pending'] is False
    assert student.get('/api/students/'+sid).json['cgpa']==9
    assert admin.get('/api/overview').json['graded_count']==before['graded_count']+1
    assert post(student,'/api/students/'+sid,{'year':4},'put').json['academic_pending']


def test_student_cannot_modify_other_records_or_protected_fields(app):
    admin,student,sid,codes=campus(app)
    other,_=new_account(app,'other@example.test',code=codes['student'])
    other_sid=other.get('/api/students').json['students'][0]['student_id']
    for target in [other_sid,'STU-2026001','missing']:
        assert post(student,'/api/students/'+target,{'name':'Attacker'},'put').status_code==404
    original=student.get('/api/students/'+sid).json
    for field,value in [('student_id','OTHER'),('email','other@example.test'),('account_id','other'),('status','Graduated'),('retention_date','2030-01-01'),('archived',False),('academic_pending',False),('student_submitted',False)]:
        assert post(student,'/api/students/'+sid,{field:value},'put').status_code==403
    assert student.get('/api/students/'+sid).json==original
    assert post(student,'/api/students/'+sid,{'cgpa':11},'put').status_code==400
    assert post(student,'/api/students/'+sid,method='delete').status_code==403
    other_admin,_=new_account(app,'outside@example.test','admin')
    assert post(other_admin,'/api/students/'+sid,{'cgpa':9},'put').status_code==404
    assert post(admin,'/api/students/'+sid,method='delete').status_code==200
    assert post(student,'/api/students/'+sid,{'name':'Cannot restore'},'put').status_code==403


def test_bound_record_remains_owned_when_admin_updates_email(app):
    admin,student,sid,_=campus(app)
    assert post(admin,'/api/students/'+sid,{'email':'updated@example.test'},'put').status_code==200
    assert post(student,'/api/students/'+sid,{'name':'Still Mine'},'put').status_code==200
    assert len(student.get('/api/students').json['students'])==1


def test_student_without_profile_can_create_only_one_own_profile(app):
    student,_=legacy_account(app,'missing@example.test')
    with app.app_context():
        store=app.extensions['store']
        with store.db() as db:db.execute("DELETE FROM students")
    details=dict(name='Own Profile',department='Business',year=2,cgpa=8.2,consent=True)
    assert post(student,'/api/students',{**details,'email':'other@example.test'}).status_code==403
    r=post(student,'/api/students',details)
    assert r.status_code==201 and r.json['email']=='missing@example.test'
    assert r.json['student_id'].startswith('REG-') and r.json['academic_pending']
    with app.extensions['store'].db() as db:
        assert r.json['account_id']==db.execute('SELECT id FROM demo_accounts WHERE email=?',('missing@example.test',)).fetchone()['id']
    assert post(student,'/api/students',details).status_code==403
    assert len(student.get('/api/students').json['students'])==1
