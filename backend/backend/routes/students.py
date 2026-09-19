from flask import Blueprint, request, jsonify
from services.student_service import get_all_students, get_student, create_student, update_student, delete_student

students_bp = Blueprint('students', __name__)

@students_bp.route('/api/students', methods=['GET'])
def students():
    return jsonify(get_all_students())

@students_bp.route('/api/students/<student_id>', methods=['GET'])
def student(student_id):
    return jsonify(get_student(student_id))

@students_bp.route('/api/students', methods=['POST'])
def add_student():
    return jsonify(create_student(request.get_json())), 201

@students_bp.route('/api/students/<student_id>', methods=['PUT'])
def update(student_id):
    return jsonify(update_student(student_id, request.get_json()))

@students_bp.route('/api/students/<student_id>', methods=['DELETE'])
def remove_student(student_id):
    return jsonify(delete_student(student_id))