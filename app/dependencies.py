"""FastAPI dependencies shared by the routers."""
from fastapi import Request


def get_hz(request: Request):
    """The Hazelcast client created at startup (see app/main.py)."""
    return request.app.state.hz
