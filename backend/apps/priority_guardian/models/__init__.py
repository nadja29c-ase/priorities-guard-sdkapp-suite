"""
Priority Guardian models package.

Contains:
- Request/response Pydantic models (requests.py)
- SQLAlchemy database models imported from db_models.py
"""

# Import db_models to register with SQLAlchemy Base
from backend.apps.priority_guardian import db_models  # noqa: F401
