'use strict';
const $=s=>document.querySelector(s);
const icon=name=>`<svg class="icon" aria-hidden="true"><use href="#i-${name}"/></svg>`;
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const roles={admin:'Administrator',staff:'Staff member',student:'Student'};
const signupRoles={student:'Student',staff:'Staff',admin:'Admin'};
const roleHelp={student:'View your own student record and privacy status.',staff:'Add and edit students. Emails stay masked; export and archive are restricted.',admin:'Manage students, export data, archive records, and review activity.'};
const titles={accounts:['YOUR CAMPUS COMMUNITY','Registered accounts','Every Student and Staff account enrolled in your campus, with updates every five seconds.'],overview:['WORKSPACE AT A GLANCE','Overview','A clear view of your student records and privacy priorities.'],students:['ORGANIZED. ACCESSIBLE. PROTECTED.','Student directory','Manage student information with clear access and privacy controls.'],privacy:['PRIVACY BY DESIGN','Privacy center','Review consent, retention dates, and the protections behind your records.'],audit:['AN ACCOUNTABLE WORKSPACE','Activity log','Follow record changes, exports, and access events in your workspace.'],archive:['KEEP CONTROL OF YOUR RECORDS','Archive','Review archived records and restore them when needed.']};
let state={user:null,csrf:'',page:'overview',rows:[],archived:[],events:[],overview:null,filter:'',department:'',status:'',tablePage:1,editId:null,archiveId:null,importRows:[],demo:false};
let toastTimer,liveTimer,liveBusy=false,loadVersion=0,authMode='institution';
state.accounts=[];state.campusCode=null;state.inviteCodes=null;state.accountFilter='';state.accountRole='';state.samplePreview=false;
function setAuthMode(mode){
 authMode=mode; $('#login-error').textContent=''; $('#login-success').textContent=''; $('#login-success').hidden=true;$('#signup-invites').hidden=true;$('#signup-invites').innerHTML='';
 const form=$('#login-form'),signup=mode==='demo-signup';
 form.elements.password.value='';form.elements.confirm_password.value='';form.elements.campus_code.value='';
 form.elements.password.type='password';form.elements.confirm_password.type='password';$('#show-password').checked=false;
 $('#signup-fields').hidden=!signup;$('#confirm-password-field').hidden=!signup;
 $('#demo-entry').hidden=signup||$('#auth-modes').hidden;
 form.elements.name.disabled=!signup;form.elements.name.required=signup;
 form.elements.confirm_password.disabled=!signup;form.elements.confirm_password.required=signup;
 form.querySelectorAll('[name=role]').forEach(el=>el.disabled=!signup);
 $('#login-form').elements.password.autocomplete=mode==='demo-signup'?'new-password':'current-password';
 $('#login-form').elements.password.minLength=mode==='institution'?1:6;
 $('#auth-submit').textContent=mode==='demo-signup'?'Create account':'Sign in';
 $('#login-description').textContent=mode==='demo-signup'?'Choose your role and create your private sample workspace.':mode==='demo-login'?'Sign in with the email and password you used when creating your account.':'Sign in with your institution account.';
 updateSignupRole();
 document.querySelectorAll('[data-auth-mode]').forEach(el=>el.setAttribute('aria-pressed',String(el.dataset.authMode===mode)));
}
function updateSignupRole(){
 const form=$('#login-form'),role=form.elements.role.value||'student',enrollment=role!=='admin',signup=authMode==='demo-signup';
 $('#campus-code-field').hidden=!enrollment;form.elements.campus_code.disabled=!signup||!enrollment;form.elements.campus_code.required=signup&&enrollment;
 $('#campus-code-label').textContent=signupRoles[role]+' campus code';form.elements.campus_code.placeholder=role==='staff'?'CG-STF-…':'CG-STU-…';
 $('#campus-code-help').textContent='Ask your Admin for the '+signupRoles[role]+' code. '+(role==='staff'?'This joins their campus with Staff record-management access.':'This joins their campus and links your Student record.')+' Your name, email, and activity status become visible to that Admin.';
 $('#signup-role-help').textContent=roleHelp[role];
 if(signup){$('#auth-submit').textContent='Create '+signupRoles[role]+' account';$('#login-description').textContent=enrollment?'Enter your Admin’s '+signupRoles[role]+' campus code to create your account.':'Create your Admin account to generate separate Student and Staff campus codes.';}
}
$('#login-form').addEventListener('change',event=>{if(event.target.name==='role')updateSignupRole();});
$('#show-password').addEventListener('change',event=>{const type=event.target.checked?'text':'password';$('#login-form').elements.password.type=type;$('#login-form').elements.confirm_password.type=type;});
function toast(message,error=false){const el=$('#toast');el.textContent=message;el.hidden=false;el.classList.toggle('failure',error);clearTimeout(toastTimer);toastTimer=setTimeout(()=>el.hidden=true,4500);}
async function api(path,options={}){
 const headers={...options.headers};
 if(options.body){headers['Content-Type']='application/json';}
 if(options.method && options.method!=='GET'){headers['X-CSRF-Token']=state.csrf;}
 const response=await fetch(path,{credentials:'same-origin',...options,headers});
 const data=await response.json();
 if(!response.ok){if(response.status===401&&state.user){state.user=null;showLogin();}throw Error(data.error||'Request failed');}
 return data;
}
function showLogin(){clearInterval(liveTimer);++loadVersion;$('#live-status').textContent='Signed out'; $('#loading').hidden=true;$('#workspace').hidden=true;$('#login-screen').hidden=false;document.querySelectorAll('dialog[open]').forEach(d=>d.close());}
async function enterWorkspace(){
 const session=await api('/api/session'); Object.assign(state,{user:session.user,csrf:session.csrf,demo:session.demo,storage:session.storage,canJoin:session.campus_enrollment});
 $('#demo-entry').hidden=!session.demo_available;
 $('#auth-modes').hidden=!session.demo_available;
 $('#institution-mode').hidden=!session.institution_login;
 $('#auth-help').hidden=!session.demo_available;
 setAuthMode(session.demo_available&&!session.institution_login?'demo-login':'institution');
 if(!session.user){showLogin();return;}
 state.accounts=[];state.campusCode=null;state.inviteCodes=null;state.accountFilter='';state.accountRole='';$('#accounts-count').textContent='';$('#page-body').innerHTML='<div class="page-loading">Loading workspace…</div>';
 $('#loading').hidden=true;$('#login-screen').hidden=true;$('#workspace').hidden=false;
 $('#welcome-strip').textContent=(state.user.name?'Welcome, '+state.user.name+'. ':'Welcome. ')+roles[state.user.role]+' workspace — '+roleHelp[state.user.role];
 $('#account-role').textContent=roles[state.user.role];$('#account-email').textContent=state.user.email;$('#account-avatar').textContent=state.user.role.slice(0,1).toUpperCase();
 $('#demo-banner').hidden=!state.demo;$('#demo-notice').hidden=!state.demo;$('#workspace-type').textContent=state.demo?'Temporary sample workspace':'Institution workspace';
 document.querySelectorAll('.admin-only').forEach(el=>el.hidden=state.user.role!=='admin');
 state.page='overview';state.filter='';state.department='';state.status='';state.tablePage=1;
 await refresh();startLiveUpdates();
}
async function refresh(live=false){
 const version=++loadVersion,page=state.page;
 if(page==='accounts'){
  const result=await api('/api/accounts');if(version!==loadVersion||page!==state.page)return;
  state.accounts=result.accounts;state.campusCode=result.campus_code;state.inviteCodes=result.invite_codes;state.samplePreview=result.sample_preview;
  $('#accounts-count').textContent=state.accounts.filter(a=>a.role!=='admin').length;
  if(!live||!$('#accounts-table'))render();else{renderAccountsTable();renderAccountMetrics();}
 }else{
  const [records,overview]=await Promise.all([api('/api/students'),api('/api/overview')]);
  if(version!==loadVersion||page!==state.page)return;
  const before=JSON.stringify([state.rows,state.overview]);
  state.rows=records.students;state.overview=overview;
  if(page==='archive')state.archived=(await api('/api/students?archived=true')).students;
  if(page==='audit')state.events=(await api('/api/audit')).events;
  if(version!==loadVersion||page!==state.page)return;
  $('#nav-count').textContent=state.rows.length;
  if(!live||before!==JSON.stringify([state.rows,state.overview])||['archive','audit'].includes(page)){
   const focused=document.activeElement,id=focused?.id,selection=focused?.selectionStart;
   render();const replacement=id&&document.getElementById(id);
   if(live&&replacement){replacement.focus();if(typeof selection==='number')replacement.setSelectionRange?.(selection,selection);}
  }
 }
 $('#last-sync').textContent='Updated '+new Intl.DateTimeFormat(undefined,{hour:'2-digit',minute:'2-digit',second:'2-digit'}).format(new Date());
 $('#live-status').textContent='Live · updates every 5s';$('#live-status').classList.remove('offline');if($('#accounts-live-badge')){$('#accounts-live-badge').textContent='Live · 5s';$('#accounts-live-badge').className='badge green';}
}
async function liveTick(){
 if(liveBusy||!state.user||document.hidden||document.querySelector('dialog[open]'))return;
 liveBusy=true;
 try{await refresh(true);}catch(e){if(state.user){$('#live-status').textContent='Connection lost · retrying';$('#live-status').classList.add('offline');if($('#accounts-live-badge')){$('#accounts-live-badge').textContent='Reconnecting';$('#accounts-live-badge').className='badge amber';}}}
 finally{liveBusy=false;}
}
function startLiveUpdates(){clearInterval(liveTimer);liveTimer=setInterval(liveTick,5000);}
document.addEventListener('visibilitychange',()=>{if(!document.hidden)liveTick();});
async function navigate(page){
 if(!titles[page]||(['accounts','audit','archive'].includes(page)&&state.user.role!=='admin'))return;
 state.page=page;state.filter='';state.department='';state.status='';state.tablePage=1;
 $('#sidebar').classList.remove('open');$('#menu-toggle').setAttribute('aria-expanded','false');renderHeading();$('#page-body').innerHTML='<div class="page-loading">Loading workspace…</div>';
 try{await refresh();}catch(e){$('#page-body').innerHTML=`<div class="empty"><h3>Unable to load this view</h3><p>${esc(e.message)}</p><button class="btn" data-action="refresh">Try again</button></div>`;}
}
function renderHeading(){
 const [eyebrow,title,description]=titles[state.page];$('#page-eyebrow').textContent=eyebrow;$('#page-title').textContent=title;$('#page-description').textContent=description;$('#breadcrumb-page').textContent=title;
 document.querySelectorAll('[data-page]').forEach(el=>{el.classList.toggle('active',el.dataset.page===state.page);if(el.dataset.page===state.page)el.setAttribute('aria-current','page');else el.removeAttribute('aria-current');});
 let actions='';
 if(['overview','students'].includes(state.page)){
  if(['student','staff'].includes(state.user.role)&&state.canJoin&&!state.user.campus_member)actions+=`<button class="btn primary" data-action="join-campus">${icon('users')}Join Admin campus</button>`;
  if(state.user.role==='admin')actions+=`<button class="btn" data-action="export">${icon('download')}Export</button>`;
  if(state.user.role!=='student')actions+=`<button class="btn primary" data-action="add">${icon('plus')}Add student</button>`;
 }else actions=`<button class="btn" data-action="refresh">${icon('clock')}Refresh</button>`;
 $('#page-actions').innerHTML=actions;
}
function render(){renderHeading();if(state.page==='overview')renderOverview();if(['students','archive'].includes(state.page))renderDirectory();if(state.page==='privacy')renderPrivacy();if(state.page==='audit')renderAudit();if(state.page==='accounts')renderAccounts();}
function dateLabel(value){return value?new Date(value).toLocaleString():'Not recorded';}
function renderAccountMetrics(){
 const students=state.accounts.filter(a=>a.role==='student'),staff=state.accounts.filter(a=>a.role==='staff'),online=state.accounts.filter(a=>a.role!=='admin'&&a.presence==='Online');
 $('#account-metrics').innerHTML=metric('Registered students',students.length,'Students enrolled in your campus','users','highlight')+metric('Registered staff',staff.length,'Staff enrolled in your campus','shield')+metric('Online now',online.length,'Students and staff active within 20 seconds','check')+metric('Auto update','5 sec','No page refresh needed','clock');
}
function inviteCards(codes,signup=false){
 return `<div class="campus-invite"><div><h2>${signup?'Your campus codes are ready':'Invite Students and Staff'}</h2><p>Share each code with its matching role. Students use the Student code; staff use the Staff code.</p></div><div class="campus-invite-codes">${['student','staff'].map(role=>`<article class="invite-code-card"><h3>${signupRoles[role]} campus code</h3><p>${role==='student'?'Joins with access to their own record.':'Grants Staff access to manage campus records.'}</p><div class="campus-code-wrap"><code id="${signup?'signup-'+role+'-code':role==='student'?'campus-code':'staff-campus-code'}">${esc(codes[role])}</code><button type="button" class="btn primary" data-action="copy-campus" data-role="${role}">Copy ${signupRoles[role]} code</button></div></article>`).join('')}</div></div>`;
}
function renderAccounts(){
 const invite=state.inviteCodes?inviteCards(state.inviteCodes):`<div class="notice-card">${state.samplePreview?'Create an Admin account to get separate Student and Staff campus codes. Sign in to monitor registrations. This preview does not expose other accounts.':'Your institution provisions accounts through its administrator.'}</div>`;
 $('#page-body').innerHTML=`${invite}<section id="account-metrics" class="metrics" aria-label="Account statistics"></section><section class="panel"><div class="toolbar"><div class="search-wrap">${icon('search')}<input id="accounts-search" aria-label="Search registered accounts" placeholder="Search name or email…" value="${esc(state.accountFilter)}"></div><select id="accounts-role-filter" aria-label="Filter accounts by role"><option value="">All roles</option>${['student','admin','staff'].map(r=>`<option value="${r}" ${state.accountRole===r?'selected':''}>${esc(roles[r])}</option>`).join('')}</select><span id="accounts-live-badge" class="badge green">Live · 5s</span></div><div id="accounts-table"></div><div class="panel-foot">${icon('lock')}Only your campus Admin can view this directory. Online indicates recent activity; Idle indicates an open session without recent activity.</div></section>`;
 renderAccountMetrics();renderAccountsTable();
}
function renderAccountsTable(){
 const query=state.accountFilter.toLowerCase();
 const rows=state.accounts.filter(a=>(!state.accountRole||a.role===state.accountRole)&&[a.name,a.email].some(v=>v.toLowerCase().includes(query)));
 $('#accounts-table').innerHTML=rows.length?`<div class="table-wrap"><table><thead><tr><th>Account</th><th>Role</th><th>Presence</th><th>Student ID</th><th>Registered</th><th>Last active</th></tr></thead><tbody>${rows.map(a=>`<tr><td><div class="student-name">${esc(a.name)}</div><div class="email-small">${esc(a.email)}</div></td><td><span class="badge">${esc(roles[a.role]||a.role)}</span></td><td><span class="presence ${a.presence.toLowerCase()}"><span class="status-dot"></span>${esc(a.presence)}</span></td><td>${esc(a.student_id||'—')}</td><td>${esc(dateLabel(a.created_at))}</td><td>${esc(dateLabel(a.last_seen))}</td></tr>`).join('')}</tbody></table></div>`:`<div class="empty">${icon('users')}<h3>No matching accounts</h3><p>Students and staff appear automatically after signing up with their matching campus code.</p></div>`;
}
function metric(label,value,note,type,highlight='') {return `<article class="metric ${highlight}"><div class="metric-head"><span>${label}</span><span class="metric-icon">${icon(type)}</span></div><div class="metric-value">${esc(value)}</div><div class="metric-foot">${icon(highlight==='warning'?'info':'check')}<span>${esc(note)}</span></div></article>`;}
function renderOverview(){
 const o=state.overview,pct=o.total?Math.round(o.consent/o.total*100):0;
 const max=Math.max(1,...o.departments.map(d=>d.count));
 const chart=o.departments.map((d,i)=>{const x=34+i*95,h=d.count/max*130;return `<rect class="bar ${i===0?'primary':''}" x="${x}" y="${155-h}" width="49" height="${h}" rx="5"/><text x="${x+24.5}" y="${145-h}" text-anchor="middle">${d.count}</text>`;}).join('');
 $('#page-body').innerHTML=`<section class="metrics" aria-label="Workspace statistics">${metric('Student records',o.total,'In the active directory','users','highlight')}${metric('Consent captured',o.consent,`${pct}% of active records`,'shield')}${metric('Average CGPA',o.graded_count===0?'—':o.average_cgpa.toFixed(2),'Reviewed academic records · out of 10','grid')}${metric('Needs review',o.review_count,'Consent or retention follow-up','info',o.review_count?'warning':'')}</section>
 <div class="overview-grid"><section class="panel"><div class="panel-head"><div><h2>Students by department</h2><p>Distribution of reviewed academic records</p></div><span class="badge">${o.total} students</span></div><div class="panel-body"><svg class="chart" viewBox="0 0 500 175" role="img" aria-label="${esc(o.departments.map(d=>`${d.name}: ${d.count}`).join(', '))}"><path class="gridline" d="M10 30h480M10 90h480M10 155h480"/>${chart}</svg><div class="chart-labels"><span>Computer<br>Science</span><span>Electronics</span><span>Mechanical</span><span>Civil</span><span>Business</span></div><div class="chart-key"><span class="key-dot"></span>Active student records</div></div></section>
 <section class="panel"><div class="panel-head"><div><h2>Privacy status</h2><p>Small checks. Meaningful protection.</p></div>${icon('shield')}</div><div class="panel-body"><div class="protection-progress"><div class="score-ring"><svg viewBox="0 0 80 80" aria-hidden="true"><circle cx="40" cy="40" r="33"/><circle class="score-value" cx="40" cy="40" r="33" stroke-dasharray="${207.35*pct/100} 207.35"/></svg><strong>${pct}%</strong></div><div><h3>Consent coverage</h3><p>${o.consent} of ${o.total} students have recorded consent</p></div></div><div class="check-list"><div class="check-item"><span class="check-icon">${icon('check')}</span>Stored record encryption<span class="badge green">Enabled</span></div><div class="check-item"><span class="check-icon">${icon('check')}</span>Role-based permissions<span class="badge green">Enforced</span></div><div class="check-item ${o.review_count?'warning':''}"><span class="check-icon">${icon(o.review_count?'info':'check')}</span>Consent & retention<span class="badge ${o.review_count?'amber':'green'}">${o.review_count?'Review '+o.review_count:'Up to date'}</span></div></div></div><div class="panel-foot">${icon('arrow')}<button class="text-btn" data-action="privacy">Open privacy center</button></div></section></div>
 <section class="panel"><div class="panel-head"><div><h2>${state.user.role==='student'?'Your student record':'Recently updated students'}</h2><p>Student information available to your role</p></div><button class="text-btn" data-action="directory">View directory ${icon('arrow')}</button></div><div class="table-wrap">${studentTable([...state.rows].sort((a,b)=>b.updated_at.localeCompare(a.updated_at)).slice(0,5),false)}</div><div class="panel-foot">${icon('lock')}Student emails are masked for staff. Students can only view their own records.</div></section>`;
}
function studentTable(rows,actions=true){
 if(!rows.length)return `<div class="empty">${icon('users')}<h3>No student records here</h3><p>${state.user.role==='student'?'Your administrator can link a record to your account email.':'Add a student or adjust your filters to get started.'}</p></div>`;
 return `<table><thead><tr><th>Student</th><th>Department</th><th>Year</th><th>CGPA</th><th>Status</th><th>Privacy</th>${actions&&state.user.role!=='student'?'<th>Actions</th>':''}</tr></thead><tbody>${rows.map(r=>`<tr><td><div class="student-cell"><span class="student-avatar">${esc(r.name.split(/\s+/).map(n=>n[0]).slice(0,2).join(''))}</span><div><div class="student-name">${esc(r.name)}</div><div class="student-id">${esc(r.student_id)}</div>${actions?`<div class="email-small">${esc(r.email)}</div>`:''}</div></div></td><td>${r.academic_pending?'Pending review':esc(r.department)}</td><td>${r.academic_pending?'—':'Year '+r.year}</td><td class="cgpa">${r.academic_pending?'—':r.cgpa.toFixed(2)}</td><td><span class="table-status ${r.status!=='Active'?'neutral':''}"><span class="status-dot"></span>${esc(r.status)}</span></td><td><span class="badge ${r.issues.length?'amber':'green'}">${r.issues.length?'Needs review':'Up to date'}</span></td>${actions&&state.user.role!=='student'?`<td><div class="table-actions">${state.page==='archive'?`<button data-action="restore" data-id="${esc(r.student_id)}">Restore</button>`:`<button data-action="edit" data-id="${esc(r.student_id)}">Edit</button>${state.user.role==='admin'?`<button class="archive-action" data-action="archive" data-id="${esc(r.student_id)}">Archive</button>`:''}`}</div></td>`:''}</tr>`).join('')}</tbody></table>`;
}
function filteredRows(){const source=state.page==='archive'?state.archived:state.rows;const query=state.filter.toLowerCase();return source.filter(r=>(!query||[r.name,r.student_id,r.email].some(s=>s.toLowerCase().includes(query)))&&(!state.department||r.department===state.department)&&(!state.status||r.status===state.status));}
function renderDirectory(){
 $('#page-body').innerHTML=`<section class="panel"><div class="toolbar"><div class="search-wrap">${icon('search')}<input id="directory-search" aria-label="Search students" placeholder="Search name, student ID, or email…" value="${esc(state.filter)}"></div><select id="department-filter" aria-label="Filter by department"><option value="">All departments</option>${['Computer Science','Electronics','Mechanical','Civil','Business'].map(d=>`<option ${state.department===d?'selected':''}>${esc(d)}</option>`).join('')}</select><select id="status-filter" aria-label="Filter by status"><option value="">All statuses</option>${['Active','Graduated','On leave'].map(d=>`<option ${state.status===d?'selected':''}>${d}</option>`).join('')}</select>${state.page==='students'&&state.user.role!=='student'?`<button class="btn" data-action="import">${icon('upload')}Import CSV</button>`:''}</div><div id="directory-table"></div></section>`;
 renderDirectoryTable();
}
function renderDirectoryTable(){
 const rows=filteredRows(),pages=Math.max(1,Math.ceil(rows.length/8));state.tablePage=Math.min(state.tablePage,pages);const start=(state.tablePage-1)*8;
 $('#directory-table').innerHTML=`<div class="table-wrap">${studentTable(rows.slice(start,start+8))}</div><div class="table-bottom"><span>${rows.length?`${start+1}–${Math.min(start+8,rows.length)} of ${rows.length} students`:'0 students'}</span><div class="pager"><button class="btn" data-action="previous" ${state.tablePage===1?'disabled':''}>Previous</button><span>${state.tablePage} / ${pages}</span><button class="btn" data-action="next" ${state.tablePage===pages?'disabled':''}>Next</button></div></div>`;
}
function renderPrivacy(){
 const o=state.overview;
 $('#page-body').innerHTML=`<section class="metrics">${metric('Consent captured',o.consent,`${o.total-o.consent} students need follow-up`,'check','highlight')}${metric('Needs review',o.review_count,'Unique records with privacy flags','info',o.review_count?'warning':'')}${metric('Archived records',o.archived,'Restorable by administrators','archive')}${metric('Session timeout','30 min','Expires after inactivity','clock')}</section><div class="privacy-grid"><section class="panel"><div class="panel-head"><div><h2>Privacy follow-up</h2><p>Rule-based checks across visible records</p></div><span class="badge ${o.review_count?'amber':'green'}">${o.review_count} flagged</span></div><div class="panel-body"><div class="review-list">${o.issues.length?o.issues.map(r=>`<div class="review-item"><div><strong>${esc(r.name)} <span class="muted">· ${esc(r.student_id)}</span></strong><p>${esc(r.issues.join(' · '))}</p></div>${state.user.role!=='student'?`<button class="text-btn" data-action="edit" data-id="${esc(r.student_id)}">Review ${icon('arrow')}</button>`:''}</div>`).join(''):`<div class="empty">${icon('check')}<h3>Everything is up to date</h3><p>Your visible records have consent and future retention dates.</p></div>`}</div></div><div class="panel-foot">${icon('info')}Flags support review; they do not certify legal compliance.</div></section><section class="panel"><div class="panel-head"><div><h2>Workspace protections</h2><p>Controls implemented in this project</p></div>${icon('lock')}</div><div class="privacy-list">${[['lock','Encrypted student records','Stored student payloads and audit entries use authenticated encryption.','Enabled'],['users','Role-based access','Admins manage the workspace, staff manage records with masked emails, and students view their own record.','Enforced'],['shield','Secure sessions','Server-tracked sessions, CSRF checks, request limits and password verification.','Enabled'],['clock','Accountable changes','Record changes, imports, exports, sign-ins and denied role access are logged.','Tracked']].map(([i,h,p,b])=>`<div class="privacy-row">${icon(i)}<div><h3>${h}</h3><p>${p}</p></div><span class="badge green">${b}</span></div>`).join('')}</div></section></div><section class="panel role-table"><div class="panel-head"><div><h2>Access at a glance</h2><p>Your current role: ${esc(roles[state.user.role])}</p></div></div><div class="table-wrap"><table><thead><tr><th>Permission</th><th>Administrator</th><th>Staff</th><th>Student</th></tr></thead><tbody><tr><td>View students</td><td>All records</td><td>All · masked emails</td><td>Own record only</td></tr><tr><td>Add / edit / import</td><td>Allowed</td><td>Allowed · email edit restricted</td><td>Unavailable</td></tr><tr><td>Export / archive / restore</td><td>Allowed</td><td>Unavailable</td><td>Unavailable</td></tr><tr><td>View activity log</td><td>Allowed</td><td>Unavailable</td><td>Unavailable</td></tr></tbody></table></div></section><div class="notice-card">${state.demo?'This is an isolated demonstration using fictional student records. Data is temporary and is removed after one day.':'Retention dates prompt a review. Archiving is reversible and does not permanently erase personal data. Set your institution’s deletion and retention policy before using real records.'} Storage: ${esc(state.storage)}.</div>`;
}
function renderAudit(){
 $('#page-body').innerHTML=`<section class="panel"><div class="panel-head"><div><h2>Workspace activity</h2><p>Latest 200 events · pseudonymous actor identifiers</p></div><div class="search-wrap audit-filter">${icon('search')}<input id="audit-search" placeholder="Filter events…" aria-label="Filter activity"></div></div><div id="audit-table"></div></section><div class="notice-card">Activity entries are read-only through the application. They track who performed an action without storing emails, passwords, or full student records in the log.</div>`;
 renderAuditTable('');
}
function renderAuditTable(query){const rows=state.events.filter(r=>[r.action,r.actor,r.role,r.target].some(v=>v.toLowerCase().includes(query.toLowerCase())));$('#audit-table').innerHTML=rows.length?`<div class="table-wrap"><table><thead><tr><th>Event</th><th>Actor</th><th>Role</th><th>Record / scope</th><th>Time</th></tr></thead><tbody>${rows.map(r=>`<tr><td class="student-name">${esc(r.action)}</td><td>${esc(r.actor)}</td><td><span class="badge">${esc(roles[r.role]||r.role)}</span></td><td>${esc(r.target)}</td><td>${esc(new Date(r.time).toLocaleString())}</td></tr>`).join('')}</tbody></table></div>`:'<div class="empty"><h3>No matching events</h3><p>Workspace actions appear here as they occur.</p></div>';}
function openRecord(id=null){
 state.editId=id;const form=$('#record-form');form.reset();$('#record-error').textContent='';
 const row=id?state.rows.find(r=>r.student_id===id):null;
 $('#record-heading').textContent=id?'Edit student':'Add student';
 for(const name of ['student_id','name','email','department','year','cgpa','status','retention_date']){form.elements[name].disabled=false;if(row)form.elements[name].value=row[name]??'';}
 form.elements.student_id.readOnly=!!id;form.elements.email.disabled=!!id&&state.user.role==='staff';form.elements.email.type=form.elements.email.disabled?'text':'email';form.elements.consent.checked=!!row?.consent;
 $('#record-dialog').showModal();
}
function csvDownload(text,filename){const blob=new Blob([text],{type:'text/csv;charset=utf-8'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=filename;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
function parseCSV(text){
 const records=[];let row=[],cell='',quoted=false;
 text=text.replace(/^\uFEFF/,'');
 for(let i=0;i<text.length;i++){let c=text[i];if(c==='"'){if(quoted&&text[i+1]==='"'){cell+='"';i++;}else if(quoted){quoted=false;}else if(cell===''){quoted=true;}else throw Error('Unexpected quote in CSV');}else if(c===','&&!quoted){row.push(cell);cell='';}else if((c==='\n'||c==='\r')&&!quoted){if(c==='\r'&&text[i+1]==='\n')i++;row.push(cell);if(row.some(v=>v.trim()))records.push(row);row=[];cell='';}else cell+=c;}
 if(quoted)throw Error('CSV has an unclosed quote');if(cell||row.length){row.push(cell);if(row.some(v=>v.trim()))records.push(row);}
 if(records.length<2)throw Error('The CSV needs a header row and at least one student');
 const headers=records.shift().map(h=>h.trim().toLowerCase());
 if(new Set(headers).size!==headers.length)throw Error('Duplicate CSV column headers');
 if(!['student_id','name','email','department'].every(h=>headers.includes(h)))throw Error('Missing required columns: student_id, name, email, department');
 if(records.length>100)throw Error('Import up to 100 students at a time');
 return records.map((cells,i)=>{if(cells.length!==headers.length)throw Error(`Row ${i+2} has the wrong number of columns`);const data=Object.fromEntries(headers.map((h,j)=>[h,cells[j].trim()]));if(data.consent&&!['true','false','yes','no','1','0'].includes(data.consent.toLowerCase()))throw Error(`Row ${i+2}: consent must be true or false`);data.consent=['true','yes','1'].includes((data.consent||'').toLowerCase());data.cgpa=data.cgpa?Number(data.cgpa):0;data.year=data.year?Number(data.year):1;if(!Number.isFinite(data.cgpa)||!Number.isFinite(data.year))throw Error(`Row ${i+2}: CGPA and year must be numbers`);data.status=data.status||'Active';return data;});
}
async function busy(button,work){button.disabled=true;try{await work();}finally{button.disabled=false;}}
document.addEventListener('click',async event=>{
 const authModeButton=event.target.closest('[data-auth-mode]');if(authModeButton){setAuthMode(authModeButton.dataset.authMode);return;}
 const close=event.target.closest('[data-close]');if(close){document.getElementById(close.dataset.close).close();return;}
 const nav=event.target.closest('[data-page]');if(nav){await navigate(nav.dataset.page);return;}
 const demo=event.target.closest('[data-demo]');if(demo){$('#login-error').textContent='';await busy(demo,async()=>{try{await api('/api/demo',{method:'POST',body:JSON.stringify({role:demo.dataset.demo})});await enterWorkspace();}catch(e){$('#login-error').textContent=e.message;}});return;}
 const button=event.target.closest('[data-action]');if(!button)return;const {action,id}=button.dataset;
 try{
  if(action==='join-campus'){$('#join-campus-form').reset();$('#join-campus-error').textContent='';$('#join-code-label').textContent=signupRoles[state.user.role]+' campus code';$('#join-campus-form').elements.campus_code.placeholder=state.user.role==='staff'?'CG-STF-…':'CG-STU-…';$('#join-campus-help').textContent=state.user.role==='staff'?'Use the Staff code supplied by your Admin to manage their campus records. Your name, email, and recent activity become visible to that Admin.':'Use the Student code supplied by your Admin. Your name, email, and activity become visible to that Admin; academic details await review.';$('#join-campus-dialog').showModal();}
  if(action==='add')openRecord();
  if(action==='edit')openRecord(id);
  if(action==='archive'){state.archiveId=id;$('#confirm-error').textContent='';$('#confirm-dialog').showModal();}
  if(action==='restore')await busy(button,async()=>{await api('/api/students/'+encodeURIComponent(id)+'/restore',{method:'POST',body:'{}'});await refresh();toast('Student restored to the directory');});
  if(action==='export'){$('#export-masked').checked=true;$('#export-error').textContent='';$('#export-dialog').showModal();}
  if(action==='import'){state.importRows=[];$('#csv-file').value='';$('#import-error').textContent='';$('#import-preview').innerHTML='';$('#confirm-import').disabled=true;$('#import-dialog').showModal();}
  if(action==='directory')await navigate('students');if(action==='privacy')await navigate('privacy');
  if(action==='refresh')await busy(button,()=>refresh());
  if(action==='copy-campus'){const code=button.closest('.invite-code-card').querySelector('code').textContent;try{await navigator.clipboard.writeText(code);toast(signupRoles[button.dataset.role]+' code copied.');}catch(e){toast('Select the '+signupRoles[button.dataset.role]+' code and copy it.');}}
  if(action==='previous'){state.tablePage--;renderDirectoryTable();}if(action==='next'){state.tablePage++;renderDirectoryTable();}
 }catch(e){toast(e.message,true);}
});
document.addEventListener('input',event=>{if(event.target.id==='accounts-search'){state.accountFilter=event.target.value;renderAccountsTable();}if(event.target.id==='directory-search'){state.filter=event.target.value;state.tablePage=1;renderDirectoryTable();}if(event.target.id==='audit-search')renderAuditTable(event.target.value);});
document.addEventListener('change',event=>{if(event.target.id==='accounts-role-filter'){state.accountRole=event.target.value;renderAccountsTable();}if(event.target.id==='department-filter'){state.department=event.target.value;state.tablePage=1;renderDirectoryTable();}if(event.target.id==='status-filter'){state.status=event.target.value;state.tablePage=1;renderDirectoryTable();}});
$('#login-form').addEventListener('submit',async event=>{event.preventDefault();const form=event.target;$('#login-error').textContent='';$('#login-success').hidden=true;await busy(form.querySelector('[type=submit]'),async()=>{try{const mode=authMode;if(mode==='demo-signup'&&form.elements.password.value!==form.elements.confirm_password.value)throw Error('Passwords do not match');if(mode==='demo-signup'&&form.elements.role.value!=='admin'&&!form.elements.campus_code.value.trim())throw Error('Enter the '+signupRoles[form.elements.role.value]+' campus code provided by your Admin');const path=mode==='demo-signup'?'/api/demo/signup':mode==='demo-login'?'/api/demo/login':'/api/login';const result=await api(path,{method:'POST',body:JSON.stringify(Object.fromEntries(new FormData(form)))});if(mode==='demo-signup'){setAuthMode('demo-login');$('#login-success').textContent=result.message;$('#login-success').hidden=false;if(result.invite_codes){$('#signup-invites').innerHTML=inviteCards(result.invite_codes,true);$('#signup-invites').hidden=false;}toast(signupRoles[result.role]+' account created successfully.');form.elements.password.focus();}else{form.reset();await enterWorkspace();toast('Signed in successfully as '+roles[state.user.role]+'.');}}catch(e){$('#login-error').textContent=e.message;}});});
$('#join-campus-form').addEventListener('submit',async event=>{event.preventDefault();$('#join-campus-error').textContent='';await busy(event.target.querySelector('[type=submit]'),async()=>{try{const result=await api('/api/campus/join',{method:'POST',body:JSON.stringify(Object.fromEntries(new FormData(event.target)))});$('#join-campus-dialog').close();await enterWorkspace();toast(result.message);}catch(e){$('#join-campus-error').textContent=e.message;}});});
$('#record-form').addEventListener('submit',async event=>{event.preventDefault();const form=event.target;$('#record-error').textContent='';await busy(form.querySelector('[type=submit]'),async()=>{try{const data=Object.fromEntries(new FormData(form));data.consent=form.elements.consent.checked;data.cgpa=Number(data.cgpa);data.year=Number(data.year);if(state.editId&&state.user.role==='staff')data.email=state.rows.find(r=>r.student_id===state.editId).email;await api('/api/students'+(state.editId?'/'+encodeURIComponent(state.editId):''),{method:state.editId?'PUT':'POST',body:JSON.stringify(data)});$('#record-dialog').close();await refresh();toast(state.editId?'Student updated':'Student added');}catch(e){$('#record-error').textContent=e.message;}});});
$('#confirm-archive').addEventListener('click',async event=>busy(event.target,async()=>{try{await api('/api/students/'+encodeURIComponent(state.archiveId),{method:'DELETE'});$('#confirm-dialog').close();await refresh();toast('Record archived. You can restore it anytime.');}catch(e){$('#confirm-error').textContent=e.message;}}));
$('#signout').addEventListener('click',async event=>busy(event.currentTarget,async()=>{try{await api('/api/logout',{method:'POST',body:'{}'});state.user=null;await enterWorkspace();toast('You have signed out');}catch(e){toast(e.message,true);}}));
$('#menu-toggle').addEventListener('click',()=>$('#menu-toggle').setAttribute('aria-expanded',String($('#sidebar').classList.toggle('open'))));
$('#download-template').addEventListener('click',()=>csvDownload('student_id,name,email,department,year,cgpa,status,consent,retention_date\nSTU-SAMPLE,Sample Student,sample@example.test,Computer Science,1,8.0,Active,true,2028-06-30\n','student-import-template.csv'));
$('#csv-file').addEventListener('change',async event=>{state.importRows=[];$('#confirm-import').disabled=true;$('#import-preview').innerHTML='';$('#import-error').textContent='';try{const file=event.target.files[0];if(!file)return;if(file.size>512*1024)throw Error('Choose a CSV smaller than 512 KB');state.importRows=parseCSV(await file.text());$('#import-preview').innerHTML=`<div class="preview-note">${state.importRows.length} records ready for server validation.</div><div class="table-wrap"><table><thead><tr><th>Student ID</th><th>Name</th><th>Department</th></tr></thead><tbody>${state.importRows.slice(0,5).map(r=>`<tr><td>${esc(r.student_id)}</td><td>${esc(r.name)}</td><td>${esc(r.department)}</td></tr>`).join('')}</tbody></table></div>`;$('#confirm-import').disabled=false;}catch(e){$('#import-error').textContent=e.message;}});
$('#confirm-import').addEventListener('click',async event=>busy(event.target,async()=>{try{const r=await api('/api/import',{method:'POST',body:JSON.stringify({students:state.importRows})});$('#import-dialog').close();await refresh();toast(`${r.imported} students imported`);}catch(e){$('#import-error').textContent=e.message;}}));
$('#confirm-export').addEventListener('click',async event=>busy(event.target,async()=>{try{const r=await fetch('/api/export?masked='+$('#export-masked').checked,{credentials:'same-origin'});if(!r.ok){const d=await r.json();throw Error(d.error);}csvDownload(await r.text(),'campusguard-students.csv');$('#export-dialog').close();toast('CSV downloaded. Export recorded in activity log.');}catch(e){$('#export-error').textContent=e.message;}}));
(async()=>{try{await enterWorkspace();}catch(e){showLogin();$('#login-error').textContent='Unable to connect: '+e.message;}})();
