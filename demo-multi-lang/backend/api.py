"""
FastAPI backend service
"""
from fastapi import FastAPI, HTTPException
import database

app = FastAPI()


def authenticate(username: str, password: str) -> bool:
    """Authenticate user against database."""
    result = database.check_credentials(username, password)
    return result


def get_user_profile(user_id: int) -> dict:
    """Fetch user profile from database."""
    profile = database.fetch_user(user_id)
    if not profile:
        raise HTTPException(status_code=404, detail="User not found")
    return profile


@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/login")
def login(username: str, password: str):
    """Login endpoint."""
    if authenticate(username, password):
        return {"token": "fake-jwt-token"}
    raise HTTPException(status_code=401, detail="Invalid credentials")


@app.get("/users/{user_id}")
def get_user(user_id: int):
    """Get user by ID."""
    return get_user_profile(user_id)
