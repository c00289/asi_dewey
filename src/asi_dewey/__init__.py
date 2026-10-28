"""ASI Dewey: a schema-driven functional-safety working-knowledge API.

The package is a FuSa API first and a set of front ends second. Everything a
front end can do goes through the same command path (see ``asi_dewey.commands``),
so a human at a CLI, a Python caller, or an AI agent all drive the same core.

Quick start::

    from asi_dewey import Brain

    with Brain("dewey.db") as brain:
        result = brain.execute("create", {"entity": "fact",
                                          "data": {"name": "Project code", "text": "PRJ-0001"}})
        print(result.to_json())
"""

from .version import SCHEMA_VERSION, __version__

__all__ = ["Brain", "PrimaryToolBusy", "SCHEMA_VERSION", "__version__"]


def __getattr__(name: str):
    # Lazy import keeps ``import asi_dewey`` cheap and avoids import cycles.
    if name == "Brain":
        from .brain import Brain

        return Brain
    if name == "PrimaryToolBusy":
        from .errors import PrimaryToolBusy

        return PrimaryToolBusy
    raise AttributeError(name)
