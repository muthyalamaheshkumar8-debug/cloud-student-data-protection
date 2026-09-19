def validate_student(data):
    required = ['student_id', 'name', 'email', 'department']
    for field in required:
        if field not in data:
            return False, f"{field} required"
    if not (0 <= data.get('cgpa', 0) <= 10):
        return False, "CGPA must be 0-10"
    return True, None