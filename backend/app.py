import hmac
import logging
import os
import secrets
from flask import Flask, g, jsonify, render_template, request, session
from werkzeug.exceptions import HTTPException
from werkzeug.security import generate_password_hash
from config import settings
from services.store import Store
from services.auth_service import load_user, create_user
from routes.auth import bp as auth_bp
from routes.students import bp as students_bp
from routes.accounts import bp as accounts_bp


def create_app(overrides=None):
    app=Flask(__name__)
    app.config.update(settings())
    if overrides: app.config.update(overrides)
    app.extensions['store']=Store(app.config)
    app.extensions['dummy_password']=generate_password_hash(secrets.token_urlsafe(32))
    app.register_blueprint(auth_bp); app.register_blueprint(students_bp)
    app.register_blueprint(accounts_bp)

    @app.before_request
    def security():
        if request.path.startswith('/api/'):
            load_user()
            if request.method in ['POST','PUT','PATCH','DELETE']:
                supplied=request.headers.get('X-CSRF-Token','')
                expected=session.get('csrf','')
                if not supplied or not expected or not hmac.compare_digest(supplied,expected):
                    return jsonify(error='Session expired. Refresh and try again.'),403
                # No trusting spoofable forwarded headers. One production Gunicorn worker.
                bucket='auth:'+request.remote_addr if request.path in ['/api/login','/api/register','/api/demo','/api/demo/signup','/api/demo/login','/api/campus/join'] else 'write:'+session.get('sid',request.remote_addr or 'unknown')
                cap=10 if bucket.startswith('auth:') else 120
                if app.extensions['store'].limited(bucket,cap=cap):
                    return jsonify(error='Too many requests. Try again in one minute.'),429

    @app.after_request
    def headers(response):
        response.headers.update({'X-Content-Type-Options':'nosniff','X-Frame-Options':'DENY','Referrer-Policy':'same-origin','Permissions-Policy':'camera=(), microphone=(), geolocation=()',
            'Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"})
        if request.path.startswith('/api/'):
            response.headers['Cache-Control']='no-store'
        if app.config['SESSION_COOKIE_SECURE']:
            response.headers['Strict-Transport-Security']='max-age=31536000'
        return response

    @app.get('/')
    def index(): return render_template('index.html')

    @app.get('/api/health')
    def health(): return jsonify(status='ok',application='CampusGuard',version='2.2.0')

    @app.errorhandler(ValueError)
    def validation(error): return jsonify(error=str(error)),400

    @app.errorhandler(HTTPException)
    def http_error(error): return jsonify(error=error.description),error.code

    @app.errorhandler(Exception)
    def unexpected(error):
        # Avoid logging request body / credentials / decrypted data.
        logging.error('Request failed: %s',type(error).__name__)
        return jsonify(error='Unable to complete this request. Contact the administrator.'),500

    @app.cli.command('create-admin')
    def create_admin():
        import click
        if app.extensions['store'].cloud:
            raise click.ClickException('Use Firebase custom claims to provision cloud administrators')
        email=click.prompt('Administrator email').strip().lower()
        password=click.prompt('Password (12+ characters)',hide_input=True,confirmation_prompt=True)
        if len(password)<12: raise click.ClickException('Use at least 12 characters')
        from utils.validation import validate_student
        validate_student(dict(student_id='CHECK',name='Check',email=email,department='Computer Science'))
        create_user(email,password,'admin')
        click.echo('Administrator created')
    @app.cli.command('create-user')
    def create_local_user():
        import click
        from utils.validation import validate_student
        if app.extensions['store'].cloud:
            raise click.ClickException('Provision verified Firebase accounts and assign custom role claims')
        email=click.prompt('Verified institutional email').strip().lower()
        role=click.prompt('Role',type=click.Choice(['admin','staff','student']),default='student')
        password=click.prompt('Password (12+ characters)',hide_input=True,confirmation_prompt=True)
        if len(password)<12: raise click.ClickException('Use at least 12 characters')
        validate_student(dict(student_id='CHECK',name='Check',email=email,department='Computer Science'))
        create_user(email,password,role)
        click.echo('Account created; student records are matched by the verified email')
    return app

app=create_app()
if __name__=='__main__':
    app.run(host='0.0.0.0',port=int(os.getenv('PORT',5000)),debug=False)
