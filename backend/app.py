from flask import Flask
from flask_cors import CORS
from dotenv import load_dotenv
import os

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY')
CORS(app)

from routes.auth import auth_bp
from routes.students import students_bp

app.register_blueprint(auth_bp)
app.register_blueprint(students_bp)

@app.route('/api/health')
def health():
    return {"status": "ok"}

if __name__ == '__main__':
    app.run(port=5000, debug=True)