import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

# Database configuration
DATABASE_URL = os.getenv('DATABASE_URL', 'mysql+pymysql://root:@localhost/scholarshipapp')

# Create engine
engine = create_engine(
    DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    echo=False  # Set to True for SQL debugging
)


def test_connection():
    try:
        with engine.connect() as conn:
            conn.execute(text('SELECT 1'))
            print("Database connection successful")
            return True
    except Exception as e:
        print(f"Database connection failed: {e}")
        return False


if __name__ == '__main__':
    test_connection()
