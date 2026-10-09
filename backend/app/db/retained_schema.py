"""Exclude inactive historical tables from future autogenerate drops."""

RETAINED_TABLES = frozenset({"planning_datasets", "planning_runs"})


def include_object(obj, name, type_, reflected, compare_to):
    return not (type_ == "table" and name in RETAINED_TABLES and reflected and compare_to is None)
