from flask import Blueprint, request, jsonify, session
from services.auth_service import create_user, authenticate_user

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')
    role = data.get('role', 'student')  # Default to student

    user = create_user(email, password, role)
    if user:
        return jsonify(user), 201
    return jsonify({"error": "Registration failed"}), 400

@auth_bp.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    user = authenticate_user(data.get('email'), data.get('password'))
    if user:
        session['user_id'] = user['user_id']
        session['role'] = user['role']
        return jsonify({"message": "Login successful", "user": user})
    return jsonify({"error": "Invalid credentials"}), 401