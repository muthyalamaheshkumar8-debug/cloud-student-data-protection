"""Verify isolated account signup and saved role permissions on a supplied deployment."""
import secrets
import sys
import requests

base=sys.argv[1].rstrip('/')
assert requests.get(base+'/api/health',timeout=30).json()['version']=='2.2.0'
for role in ['student','staff','admin']:
    client=requests.Session()
    csrf=client.get(base+'/api/session',timeout=30).json()['csrf']
    credentials={'email':role+'-'+secrets.token_hex(6)+'@example.test','password':secrets.token_urlsafe(20),'name':'Sample '+role.title(),'role':role}
    def post(path,data):
        global csrf
        response=client.post(base+path,json=data,headers={'X-CSRF-Token':csrf},timeout=30)
        if response.ok and 'csrf' in response.json():csrf=response.json()['csrf']
        return response
    result=post('/api/demo/signup',credentials)
    assert result.status_code==201,(role,result.status_code,result.text)
    assert result.json()['message'].startswith(role.title()+' account created successfully')
    login=post('/api/demo/login',{**credentials,'role':'admin'})
    assert login.status_code==200 and login.json()['user']['role']==role
    rows=client.get(base+'/api/students',timeout=30).json()['students']
    assert len(rows)==(1 if role=='student' else 12)
    if role=='student':assert rows[0]['email']==credentials['email']
    if role=='staff':assert all(row.get('email_masked') for row in rows)
    assert client.get(base+'/api/audit',timeout=30).status_code==(200 if role=='admin' else 403)
    assert client.get(base+'/api/export',timeout=30).status_code==(200 if role=='admin' else 403)
    assert post('/api/logout',{}).ok
    print(role.title()+': signup success, saved role, visibility, export/audit permissions, and logout verified.')
print('Live CampusGuard 2.2.0 role checks passed.')
