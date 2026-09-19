from firebase_admin import auth
from backend.config import Config

def create_user(email, password, role):
    try:
        # Create Firebase Auth user
        user = auth.create_user(email=email, password=password)
        # Note: In real app, store role in Firestore, not here
        return {"user_id": user.uid, "email": user.email, "role": role}
    except Exception as e:
        print(f"Auth Error: {e}")
        return None

def authenticate_user(email, password):
    try:
        user = auth.get_user_by_email(email)
        # In real app, verify password via auth
        return {"user_id": user.uid, "email": user.email, "role": "student"}
    except Exception:
        return None