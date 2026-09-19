from dotenv import load_dotenv
import os

load_dotenv()

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret')
    FIREBASE_CRED_PATH = os.getenv('FIREBASE_CRED_PATH', 'serviceAccountKey.json')