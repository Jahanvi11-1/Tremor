"""
Database access layer
"""
import psycopg2


def get_connection():
    """Get database connection."""
    return psycopg2.connect("postgresql://localhost/demo")


def check_credentials(username: str, password: str) -> bool:
    """Check if credentials are valid."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT authenticate_user(%s, %s)", (username, password))
    result = cursor.fetchone()[0]
    conn.close()
    return result


def fetch_user(user_id: int) -> dict:
    """Fetch user by ID."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT get_user_profile(%s)", (user_id,))
    result = cursor.fetchone()
    conn.close()
    
    if result:
        return {"id": result[0], "name": result[1], "email": result[2]}
    return None


def save_user(user_data: dict) -> int:
    """Save user to database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO users (name, email) VALUES (%s, %s) RETURNING id",
        (user_data["name"], user_data["email"])
    )
    user_id = cursor.fetchone()[0]
    conn.commit()
    conn.close()
    return user_id
