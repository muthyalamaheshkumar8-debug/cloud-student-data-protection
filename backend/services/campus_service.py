"""Role-specific campus invitations, checked before granting shared access."""
import time

def enrollment_campus(db,code,role,current=None):
    label=role.title()
    if role not in ('student','staff'):
        raise ValueError('Admin accounts create their own campus; they cannot use an invitation code.')
    if not isinstance(code,str) or len(code)>40 or not code.strip():
        raise ValueError(f'Enter the {label} campus code provided by your Admin')
    column={'student':'join_code','staff':'staff_code'}[role]
    current=time.time() if current is None else current
    campus=db.execute(f"SELECT c.* FROM campuses c JOIN demo_accounts o ON o.id=c.owner_id WHERE c.{column}=? AND c.expires>? AND o.expires>? AND o.role='admin'",(code.strip().upper(),current,current)).fetchone()
    if not campus:
        raise ValueError(f'{label} campus code is invalid or expired. Ask your Admin for the {label} code.')
    return campus

def invitation_codes(campus):
    return dict(student=campus['join_code'],staff=campus['staff_code'])
