"""Verify campus enrollment and account visibility on a supplied deployment.

Creates four temporary fictional accounts; never prints credentials or campus codes.
"""
import secrets
import sys
import requests

base=sys.argv[1].rstrip('/')
assert requests.get(base+'/api/health',timeout=30).json()['version']=='2.2.0'

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
        self.post('/api/demo/signup',{**self.credentials,**({'campus_code':code} if code else {})},201)
    def login(self):self.post('/api/demo/login',self.credentials)

admin=Client('admin','Verification Admin');admin.signup();admin.login()
code=admin.get('/api/accounts')['campus_code']
student=Client('student','Verification Student');student.signup(code)
directory=admin.get('/api/accounts')['accounts']
assert len(directory)==2
row=next(a for a in directory if a['email']==student.credentials['email'])
assert row['presence']=='Offline' and row['student_id']
assert not any('password' in key for account in directory for key in account)
student.login()
assert next(a for a in admin.get('/api/accounts')['accounts'] if a['id']==row['id'])['presence']=='Online'
records=student.get('/api/students')['students']
assert len(records)==1 and records[0]['account_id']==row['id'] and records[0]['academic_pending']
assert student.session.get(base+'/api/accounts',timeout=30).status_code==403
student.post('/api/logout',{})
assert next(a for a in admin.get('/api/accounts')['accounts'] if a['id']==row['id'])['presence']=='Offline'
other=Client('admin','Other Verification Admin');other.signup();other.login()
assert len(other.get('/api/accounts')['accounts'])==1
assert not any(r.get('account_id')==row['id'] for r in other.get('/api/students')['students'])
existing=Client('student','Existing Verification Student');existing.signup();existing.login()
existing.post('/api/campus/join',{'campus_code':code})
assert len(existing.get('/api/students')['students'])==1
assert len(admin.get('/api/accounts')['accounts'])==3
for client in (existing,other,admin):client.post('/api/logout',{})
print('Live campus checks passed: new and existing enrollment, scoped Admin visibility, account-linked records, Online/Offline status, and role restrictions.')
