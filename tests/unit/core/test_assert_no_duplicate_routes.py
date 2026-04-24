"""
Unit test for _assert_no_duplicate_routes in backend/main.py.

Verifies that the duplicate-route guard fails loudly when two routers register
the same (method, path), and passes silently otherwise.
"""

import pytest
from fastapi import FastAPI, APIRouter

from backend.main import _assert_no_duplicate_routes


def test_no_duplicates_passes():
    """App with unique routes passes the check."""
    app = FastAPI()
    r1 = APIRouter()

    @r1.get("/foo")
    async def foo():
        return {"ok": True}

    @r1.get("/bar")
    async def bar():
        return {"ok": True}

    app.include_router(r1)
    _assert_no_duplicate_routes(app)  # Should not raise


def test_duplicate_raises():
    """Two routers registering the same (method, path) raises RuntimeError."""
    app = FastAPI()
    r1 = APIRouter()
    r2 = APIRouter()

    @r1.get("/collision")
    async def collision_v1():
        return {"version": 1}

    @r2.get("/collision")
    async def collision_v2():
        return {"version": 2}

    app.include_router(r1)
    app.include_router(r2)

    with pytest.raises(RuntimeError, match="Duplicate routes detected"):
        _assert_no_duplicate_routes(app)


def test_same_path_different_methods_passes():
    """Same path with different HTTP methods is not a duplicate."""
    app = FastAPI()
    r = APIRouter()

    @r.get("/resource")
    async def get_resource():
        return {"ok": True}

    @r.post("/resource")
    async def post_resource():
        return {"ok": True}

    app.include_router(r)
    _assert_no_duplicate_routes(app)  # Should not raise
