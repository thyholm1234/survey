"""Arkitekturregler, der beskytter mod stille, tidsafhængige fejl."""
from fastapi.routing import APIRoute

from app.db import get_db
from app.main import create_app


def _walk(dep):
    yield dep
    for sub in dep.dependencies:
        yield from _walk(sub)


def test_get_db_always_exits_before_response_is_sent():
    """Commit skal ske, FØR svaret når klienten (FastAPI >= 0.118: scope='function')."""
    bad = []
    for route in create_app().routes:
        if isinstance(route, APIRoute):
            for d in _walk(route.dependant):
                if d.call is get_db and d.scope != "function":
                    bad.append(f"{route.methods} {route.path}")
    assert not bad, f"get_db uden scope='function': {bad}"
