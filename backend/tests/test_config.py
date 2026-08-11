"""Pin the database identity that has to be duplicated.

scripts/db.env is the single source of truth, but two consumers cannot read it
when they need it and so keep literal copies:

  backend/app/config.py   ships without scripts/ (render.yaml sets rootDir:
                          backend) and must do no file I/O at import time
  .github/workflows/*.yml the postgres service block is evaluated before the
                          repository is checked out

A silent disagreement between those copies and scripts/db.env is the failure
this file exists to prevent: the app quietly uses one database while the tests
and tooling use another, and nothing errors until much later.
"""

from pathlib import Path

from app.config import Settings

from tests.conftest import _read_db_env

REPO_ROOT = Path(__file__).resolve().parents[2]


def expected_dsn(database: str) -> str:
    env = _read_db_env()
    return (
        f"postgresql+asyncpg://{env['PGUSER']}:{env['PGPASSWORD']}"
        f"@{env['PGHOST']}:{env['PGPORT']}/{database}"
    )


class TestDatabaseIdentity:
    def test_settings_default_matches_scripts_db_env(self):
        # model_fields, not settings.database_url: the class default is immune
        # to .env and to conftest pointing the environment at the test database.
        default = Settings.model_fields["database_url"].default
        assert default == expected_dsn(_read_db_env()["PGDATABASE"])

    def test_env_example_matches_scripts_db_env(self):
        env = _read_db_env()
        text = (REPO_ROOT / ".env.example").read_text()
        assert f"DATABASE_URL={expected_dsn(env['PGDATABASE'])}" in text
        assert f"POSTGRES_DB={env['PGDATABASE']}" in text

    def test_docker_compose_matches_scripts_db_env(self):
        env = _read_db_env()
        text = (REPO_ROOT / "docker-compose.yml").read_text()
        assert f"POSTGRES_USER: {env['PGUSER']}" in text
        assert f"${{POSTGRES_DB:-{env['PGDATABASE']}}}" in text
        assert f"${{PGDATABASE_TEST:-{env['PGDATABASE_TEST']}}}" in text
        # Without this the advertised PGPORT override starts a container on one
        # port while scripts/db.sh waits on another, and db-up times out.
        assert f'"${{PGPORT:-{env["PGPORT"]}}}:5432"' in text

    def test_ci_postgres_service_matches_scripts_db_env(self):
        env = _read_db_env()
        text = (REPO_ROOT / ".github/workflows/backend-ci.yml").read_text()
        assert f"POSTGRES_USER: {env['PGUSER']}" in text
        assert f"POSTGRES_PASSWORD: {env['PGPASSWORD']}" in text
        # The service block, not just the DSN in the migrations step: changing
        # one and not the other is exactly the drift worth catching.
        assert f"POSTGRES_DB: {env['PGDATABASE_TEST']}" in text
        assert expected_dsn(env["PGDATABASE_TEST"]) in text

    def test_shell_scripts_source_db_env_rather_than_redefining_it(self):
        # scripts/pgdev.sh is invoked directly by README's rename-migration
        # instructions, so its database names must come from the same file the
        # make targets use, not from its own defaults.
        for name in ("db.sh", "pgdev.sh"):
            text = (REPO_ROOT / "scripts" / name).read_text()
            assert 'scripts/db.env"' in text, f"{name} does not source scripts/db.env"

    def test_the_three_databases_are_distinct(self):
        # The suite drops every table in PGDATABASE_TEST, and migrate-check
        # drops PGDATABASE_MIGRATIONS outright, on every run.
        env = _read_db_env()
        names = [env["PGDATABASE"], env["PGDATABASE_TEST"], env["PGDATABASE_MIGRATIONS"]]
        assert len(set(names)) == 3, names

    def test_pgdev_does_not_hardcode_the_role(self):
        # pgdev.sh initdb's the cluster; a literal role there would build a
        # cluster that scripts/db.sh, connecting as $PGUSER, cannot log into.
        text = (REPO_ROOT / "scripts/pgdev.sh").read_text()
        assert "-U energy" not in text
