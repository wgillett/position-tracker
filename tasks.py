from invoke import task
from invoke.context import Context


@task
def lint(c: Context) -> None:
    c.run("uv run ruff check .")


@task
def fmt(c: Context) -> None:
    c.run("uv run ruff format .")


@task
def typecheck(c: Context) -> None:
    c.run("uv run mypy")


@task
def test(c: Context) -> None:
    c.run("uv run pytest")


@task(pre=[lint, typecheck, test])
def check(c: Context) -> None:
    """Run everything CI would run."""
