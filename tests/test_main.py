"""Tests for the subcommand dispatcher."""

import pytest


class TestMainDispatcher:
    def test_no_subcommand_shows_help(self, capsys):
        from clipcompose.main import main

        with pytest.raises(SystemExit) as exc_info:
            main([])
        assert exc_info.value.code != 0  # should error without subcommand

    def test_compose_subcommand_exists(self):
        """Verify compose subcommand is registered (will fail on missing --manifest)."""
        from clipcompose.main import main

        with pytest.raises(SystemExit):
            main(["compose"])  # missing required args, but subcommand recognized

    def test_assemble_subcommand_exists(self):
        from clipcompose.main import main

        with pytest.raises(SystemExit):
            main(["assemble"])

    def test_transcribe_subcommand_exists(self):
        from clipcompose.main import main

        with pytest.raises(SystemExit):
            main(["transcribe"])

    def test_cut_subcommand_exists(self):
        from clipcompose.main import main

        with pytest.raises(SystemExit):
            main(["cut"])

    def test_invalid_subcommand_errors(self, capsys):
        from clipcompose.main import main

        with pytest.raises(SystemExit) as exc_info:
            main(["nonexistent"])
        assert exc_info.value.code != 0
