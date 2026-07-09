"""Canonical motor start/stop example — see panelkit.examples.motor_start_stop."""

from panelkit.examples.motor_start_stop import (
    MOTOR_LOAD_A,
    build_project,
    build_project_with_harness,
)

__all__ = ["MOTOR_LOAD_A", "build_project", "build_project_with_harness"]

if __name__ == "__main__":
    project = build_project()
    print(f"built {project.name!r}: {len(project.components)} components, {len(project.nets)} nets")
