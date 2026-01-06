from typer.testing import CliRunner

from insomnia_run.main import app


runner = CliRunner()


def test_version_flag():
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert "insomnia-run" in result.stdout
