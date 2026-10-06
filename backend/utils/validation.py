import math
import re
from datetime import date

DEPARTMENTS = ['Computer Science', 'Electronics', 'Mechanical', 'Civil', 'Business']

def validate_student(data):
    if not isinstance(data, dict):
        raise ValueError('A student object is required')
    r = {}
    for field, limit in [('student_id',32),('name',100),('email',160),('department',50)]:
        value = data.get(field)
        if not isinstance(value,str) or not value.strip() or len(value.strip())>limit:
            raise ValueError(f'{field.replace("_"," ").capitalize()} is required (maximum {limit} characters)')
        r[field] = value.strip()
    if not re.fullmatch(r'[A-Za-z0-9_-]+',r['student_id']):
        raise ValueError('Student ID may contain letters, numbers, hyphens and underscores')
    r['email'] = r['email'].lower()
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',r['email']):
        raise ValueError('Enter a valid email address')
    if r['department'] not in DEPARTMENTS:
        raise ValueError('Choose an available department')
    try:
        if isinstance(data.get('cgpa'),bool) or isinstance(data.get('year'),bool):
            raise ValueError()
        r['cgpa']=float(data.get('cgpa',0))
        year=float(data.get('year',1))
        if not math.isfinite(r['cgpa']) or not 0<=r['cgpa']<=10 or year not in (1,2,3,4):
            raise ValueError()
        r['year']=int(year)
    except (TypeError,ValueError):
        raise ValueError('CGPA must be 0–10 and year must be 1–4') from None
    r['status']=data.get('status','Active')
    if r['status'] not in ['Active','Graduated','On leave']:
        raise ValueError('Invalid student status')
    r['consent']=data.get('consent',False)
    if not isinstance(r['consent'],bool):
        raise ValueError('Consent must be true or false')
    r['retention_date']=data.get('retention_date','')
    if r['retention_date']:
        if not isinstance(r['retention_date'],str):
            raise ValueError('Invalid retention date')
        try: date.fromisoformat(r['retention_date'])
        except ValueError: raise ValueError('Retention date must use YYYY-MM-DD') from None
    return r

def findings(record):
    issues=[]
    if not record['consent']: issues.append('Consent missing')
    if not record.get('retention_date'): issues.append('Retention date missing')
    elif record['retention_date'] < date.today().isoformat(): issues.append('Retention overdue')
    return issues
