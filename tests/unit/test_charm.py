# Copyright 2024 Guillaume Belanger
# See LICENSE file for licensing details.


from unittest.mock import MagicMock, patch

import pytest
import yaml
from charm import EupfOperatorCharm
from ops import ActiveStatus, WaitingStatus, testing

NAMESPACE = "whatever"

def read_file(path: str) -> str:
    """Read a file and returns as a string."""
    with open(path, "r") as f:
        content = f.read()
    return content


class TestCharm:
    patcher_machine = patch("charm.Machine")

    @pytest.fixture()
    def setup(self):
        self.mock_machine = MagicMock()
        self.mock_machine.pull.return_value = ""
        mock_machine = TestCharm.patcher_machine.start()
        mock_machine.return_value = self.mock_machine

    @pytest.fixture(autouse=True)
    def harness(self, setup, request):
        self.harness = testing.Harness(EupfOperatorCharm)
        self.harness.set_model_name(name=NAMESPACE)
        self.harness.set_leader(is_leader=True)
        self.harness.begin()
        yield self.harness
        self.harness.cleanup()
        request.addfinalizer(self.teardown)

    @staticmethod
    def teardown() -> None:
        patch.stopall()

    def test_given_fiveg_config_file_not_created_when_evaluate_status_then_status_is_waiting(
        self
    ):
        self.mock_machine.exists.return_value = False
        self.harness.evaluate_status()

        assert self.harness.model.unit.status == WaitingStatus("Waiting for UPF configuration file")

    def test_given_config_file_created_when_evaluate_status_then_status_is_active(self):
        self.mock_machine.exists.return_value = True
        self.harness.evaluate_status()

        assert self.harness.model.unit.status == ActiveStatus()

    def test_given_config_file_not_created_when_config_changed_then_file_created(self):
        self.mock_machine.exists.return_value = False

        self.harness.update_config()

        expected_config_file_content = read_file("tests/unit/expected_config.yaml").strip()

        _, kwargs = self.mock_machine.push.call_args
        assert kwargs["path"] == "/var/snap/eupf/common/config.yaml"
        assert yaml.safe_load(kwargs["source"]) == yaml.safe_load(expected_config_file_content)
