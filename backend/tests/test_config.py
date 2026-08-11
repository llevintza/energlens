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

    def test_ci_postgres_service_matches_scripts_db_env(self):
        env = _read_db_env()
        text = (REPO_ROOT / ".github/workflows/backend-ci.yml").read_text()
        assert f"POSTGRES_USER: {env['PGUSER']}" in text
        assert f"POSTGRES_PASSWORD: {env['PGPASSWORD']}" in text
        assert f"/{env['PGDATABASE_TEST']}" in text

    def test_test_database_is_not_the_app_database(self):
        # The suite drops every table in PGDATABASE_TEST on each run.
        env = _read_db_env()
        assert env["PGDATABASE_TEST"] != env["PGDATABASE"]
