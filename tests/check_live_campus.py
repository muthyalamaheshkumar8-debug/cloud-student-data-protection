"""Verify campus enrollment and account visibility on a supplied deployment.

Creates four temporary fictional accounts; never prints credentials or campus codes.
"""
import secrets
import sys
import requests

base=sys.argv[1].rstrip('/')
assert requests.get(base+'/api/health',timeout=30).json()['version']=='2.3.0'

class Client:
    def __init__(self,role,name):
        self.session=requests.Session()
        self.csrf=self.get('/api/session')['csrf']
        self.credentials=dict(email=role+'-'+secrets.token_hex(6)+'@example.test',password=secrets.token_urlsafe(20),role=role,name=name)
    def get(self,path):
        response=self.session.get(base+path,timeout=30)
        assert response.ok,(path,response.status_code,response.text)
        return response.json()
    def post(self,path,data,expected=200):
        response=self.session.post(base+path,json=data,headers={'X-CSRF-Token':self.csrf},timeout=30)
        assert response.status_code==expected,(path,response.status_code,response.text)
        result=response.json()
        if 'csrf' in result:self.csrf=result['csrf']
        return result
    def signup(self,code=None):
        return self.post('/api/demo/signup',{**self.credentials,**({'campus_code':code} if code else {})},201)
    def login(self):self.post('/api/demo/login',self.credentials)

admin=Client('admin','Verification Admin');created=admin.signup()
codes=created['invite_codes']
assert codes['student'].startswith('CG-STU-') and codes['staff'].startswith('CG-STF-') and codes['student']!=codes['staff']
assert admin.get('/api/session')['user'] is None
admin.login()
assert admin.get('/api/accounts')['invite_codes']==codes
student=Client('student','Verification Student')
student.post('/api/demo/signup',{**student.credentials,'campus_code':codes['staff']},400)
student.signup(codes['student'])
directory=admin.get('/api/accounts')['accounts']
assert len(directory)==2
row=next(a for a in directory if a['email']==student.credentials['email'])
assert row['presence']=='Offline' and row['student_id']
assert not any('password' in key for account in directory for key in account)
student.login()
assert next(a for a in admin.get('/api/accounts')['accounts'] if a['id']==row['id'])['presence']=='Online'
records=student.get('/api/students')['students']
assert len(records)==1 and records[0]['account_id']==row['id'] and records[0]['academic_pending']
for path in ['/api/accounts','/api/audit','/api/export']:
    assert student.session.get(base+path,timeout=30).status_code==403
student.post('/api/logout',{})
assert next(a for a in admin.get('/api/accounts')['accounts'] if a['id']==row['id'])['presence']=='Offline'
staff=Client('staff','Verification Staff')
staff.post('/api/demo/signup',staff.credentials,400)
staff.signup(codes['staff']);staff.login()
assert staff.get('/api/session')['user']['role']=='staff'
assert all(r['email_masked'] for r in staff.get('/api/students')['students'])
assert len(staff.get('/api/students')['students'])==13
for path in ['/api/accounts','/api/audit','/api/export']:
    assert staff.session.get(base+path,timeout=30).status_code==403
assert len(admin.get('/api/accounts')['accounts'])==3
assert next(a for a in admin.get('/api/accounts')['accounts'] if a['role']=='staff')['student_id'] is None
other=Client('admin','Other Verification Admin');other.signup();other.login()
assert len(other.get('/api/accounts')['accounts'])==1
assert not any(r.get('account_id')==row['id'] for r in other.get('/api/students')['students'])
for client in (staff,other,admin):client.post('/api/logout',{})
print('Live CampusGuard 2.3 checks passed: immediate distinct invitation codes, required matching Student/Staff codes, scoped Admin visibility, account-linked records, Online/Offline status, Staff masking, and role restrictions.')
