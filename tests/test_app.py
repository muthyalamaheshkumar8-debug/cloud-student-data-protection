import csv
import io
import sys
from pathlib import Path
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from app import create_app
from services.auth_service import create_user

@pytest.fixture
def app(tmp_path):
    return create_app({'TESTING':True,'SECRET_KEY':'s'*48,'ENCRYPTION_KEY':'e'*48,'DATABASE':str(tmp_path/'test.db'),'DEMO_MODE':True,'SESSION_COOKIE_SECURE':False,'FIREBASE_CREDENTIALS_JSON':None})

@pytest.fixture
def client(app): return app.test_client()

def post(client,path,data=None,method='post'):
    csrf=client.get('/api/session').json['csrf']
    return getattr(client,method)(path,json=data or {},headers={'X-CSRF-Token':csrf})

def demo(client,role='admin'): return post(client,'/api/demo',{'role':role})

def sample(sid='NEW-1',**kwargs):
    return {'student_id':sid,'name':'Sample Student','email':'sample@example.test','department':'Computer Science','cgpa':8.2,'year':2,'consent':True,'retention_date':'2028-06-30',**kwargs}

def test_health_and_page(client):
    assert client.get('/api/health').json['status']=='ok'
    page=client.get('/')
    assert page.status_code==200 and b'CampusGuard' in page.data
    assert "frame-ancestors 'none'" in page.headers['Content-Security-Policy']

def test_unauthorized_and_csrf(client):
    assert client.get('/api/students').status_code==401
    assert client.post('/api/demo',json={'role':'admin'}).status_code==403
    assert post(client,'/api/demo',{'role':'bogus'}).status_code==400

def test_demo_isolation(app):
    a,b=app.test_client(),app.test_client();demo(a);demo(b)
    assert post(a,'/api/students',sample()).status_code==201
    assert a.get('/api/students/NEW-1').status_code==200
    assert b.get('/api/students/NEW-1').status_code==404

def test_student_cannot_access_others_or_mutate(client):
    demo(client,'student')
    rows=client.get('/api/students').json['students']
    assert len(rows)==1 and rows[0]['email']=='student.demo@example.test'
    assert client.get('/api/students/STU-2026002').status_code==404
    assert post(client,'/api/students',sample()).status_code==403
    assert client.get('/api/audit').status_code==403
    assert client.get('/api/export').status_code==403

def test_staff_masking_and_permissions(client):
    demo(client,'staff')
    row=client.get('/api/students/STU-2026001').json
    assert row['email_masked'] and row['email']!='student.demo@example.test'
    assert post(client,'/api/students/STU-2026001',{'name':'Updated','email':row['email']},'put').status_code==200
    assert post(client,'/api/students/STU-2026001',{'email':'other@example.test'},'put').status_code==403
    assert post(client,'/api/students/STU-2026001',method='delete').status_code==403
    assert client.get('/api/export').status_code==403

def test_crud_archive_restore_and_logs(client):
    demo(client)
    assert post(client,'/api/students',sample()).status_code==201
    assert post(client,'/api/students',sample()).status_code==409
    assert post(client,'/api/students/NEW-1',{'cgpa':9.0},'put').json['cgpa']==9
    assert post(client,'/api/students/NEW-1',method='delete').status_code==200
    assert not any(r['student_id']=='NEW-1' for r in client.get('/api/students').json['students'])
    assert len(client.get('/api/students?archived=true').json['students'])==1
    assert post(client,'/api/students/NEW-1/restore').status_code==200
    assert any(r['student_id']=='NEW-1' for r in client.get('/api/students').json['students'])
    actions=[e['action'] for e in client.get('/api/audit').json['events']]
    assert 'Student archived' in actions and 'Student restored' in actions

@pytest.mark.parametrize('kwargs',[{'cgpa':'bad'},{'cgpa':11},{'cgpa':True},{'year':2.5},{'consent':'true'},{'department':'Unknown'},{'retention_date':'wrong'},{'email':'invalid'},{'student_id':'../evil'}])
def test_validation(client,kwargs):
    demo(client)
    assert post(client,'/api/students',sample(**kwargs)).status_code==400

def test_import_atomic_validation_and_duplicate(client):
    demo(client)
    r=post(client,'/api/import',{'students':[sample('IMPORT-1'),sample('IMPORT-2',cgpa=90)]})
    assert r.status_code==400
    assert client.get('/api/students/IMPORT-1').status_code==404
    assert post(client,'/api/import',{'students':[sample('IMPORT-1'),sample('IMPORT-2')]}).json['imported']==2
    assert post(client,'/api/import',{'students':[sample('IMPORT-3'),sample('IMPORT-1')]}).status_code==409
    assert client.get('/api/students/IMPORT-3').status_code==404

def test_export_masking_formula_and_audit(client):
    demo(client)
    assert post(client,'/api/students',sample(name='=HYPERLINK("malicious")')).status_code==201
    data=client.get('/api/export').data.decode()
    rows=list(csv.DictReader(io.StringIO(data)))
    assert all(r['email']=='[redacted]' for r in rows)
    assert any(r['name'].startswith("'=HYPERLINK") for r in rows)
    assert 'sample@example.test' in client.get('/api/export?masked=false').data.decode()
    assert any('CSV exported' in e['action'] for e in client.get('/api/audit').json['events'])

def test_encryption_at_rest(app,client):
    demo(client);post(client,'/api/students',sample())
    store=app.extensions['store']
    with store.db() as db:
        raw=' '.join(r['payload'] for r in db.execute('SELECT payload FROM students'))
    assert 'Sample Student' not in raw and 'sample@example.test' not in raw and 'Computer Science' not in raw
    assert client.get('/api/students/NEW-1').json['name']=='Sample Student'

def test_password_verification_and_registration_privilege(app,client):
    with app.app_context():create_user('admin@example.test','CorrectPassword123!','admin')
    assert post(client,'/api/login',{'email':'admin@example.test','password':'wrong'}).status_code==401
    assert post(client,'/api/login',{'email':'admin@example.test','password':'CorrectPassword123!'}).status_code==200
    assert client.get('/api/session').json['user']['role']=='admin'
    assert post(client,'/api/register',{'email':'new@example.test','password':'StrongPassword123','role':'admin'}).status_code==403

def test_logout_revokes_old_cookie(app,client):
    demo(client)
    old=client.get_cookie('session').value
    assert post(client,'/api/logout').status_code==200
    replay=app.test_client();replay.set_cookie('session',old)
    assert replay.get('/api/students').status_code==401

def test_live_role_revalidation(app,client):
    with app.app_context():u=create_user('admin@example.test','CorrectPassword123!','admin')
    post(client,'/api/login',{'email':'admin@example.test','password':'CorrectPassword123!'})
    with app.extensions['store'].db() as db:db.execute('UPDATE users SET role=? WHERE id=?',('student',u['id']))
    assert post(client,'/api/students',sample()).status_code==403

def test_request_limit(client):
    results=[post(client,'/api/login',{'email':'missing@example.test','password':'wrong'}).status_code for _ in range(11)]
    assert results[-1]==429

def test_demo_disabled(app):
    app.config['DEMO_MODE']=False
    client=app.test_client()
    assert client.get('/api/session').json['demo_available'] is False
    assert demo(client).status_code==404

def test_self_signup_cannot_claim_student_email(client):
    assert post(client,'/api/register',{'email':'victim@example.test','password':'StrongPassword123'}).status_code==403

def test_production_requires_secrets(monkeypatch,tmp_path):
    from config import settings
    monkeypatch.setenv('APP_ENV','production')
    monkeypatch.setenv('DATA_DIR',str(tmp_path))
    monkeypatch.delenv('SECRET_KEY',raising=False)
    with pytest.raises(RuntimeError,match='SECRET_KEY is required'):settings()

def test_production_real_data_requires_persistence(monkeypatch,tmp_path):
    from config import settings
    monkeypatch.setenv('APP_ENV','production');monkeypatch.setenv('DEMO_MODE','false');monkeypatch.setenv('DATA_DIR',str(tmp_path))
    monkeypatch.delenv('FIREBASE_CREDENTIALS_JSON',raising=False);monkeypatch.delenv('PERSISTENT_STORAGE',raising=False)
    with pytest.raises(RuntimeError,match='persistent DATA_DIR'):settings()
