#!/usr/bin/env python3
# Copyright 2024 Guillaume Belanger
# See LICENSE file for licensing details.


"""Charm the eUPF service."""

import logging

import ops
import yaml
from jinja2 import Environment, FileSystemLoader
from machine import Machine
from ops import (
    ActiveStatus,
    BlockedStatus,
    CollectStatusEvent,
    WaitingStatus,
)

UPF_CONFIG_FILE_NAME = "config.yaml"
UPF_CONFIG_PATH = "/var/snap/eupf/common"
PFCP_ADDRESS = "127.0.0.1:8805"
N3_ADDRESS = "127.0.0.1"
INTERFACE_NAME = "lo"

logger = logging.getLogger(__name__)

def render_upf_config_file(
    pfcp_address: str,
    n3_address: str,
    interface_name: str,
) -> str:
    """Render the configuration file for the 5G UPF service.

    Args:
        pfcp_address: The PFCP address.
        n3_address: The N3 address.
        interface_name: The interface name.
    """
    jinja2_environment = Environment(loader=FileSystemLoader("src/templates/"))
    template = jinja2_environment.get_template(f"{UPF_CONFIG_FILE_NAME}.j2")
    content = template.render(
        pfcp_address=pfcp_address,
        n3_address=n3_address,
        interface_name=interface_name,
    )
    return content


class EupfOperatorCharm(ops.CharmBase):
    """Charm the service."""

    def __init__(self, *args):
        super().__init__(*args)
        self._machine = Machine()
        self.framework.observe(self.on.collect_unit_status, self._on_collect_status)
        self.framework.observe(self.on.config_changed, self._configure)

    def _on_collect_status(self, event: CollectStatusEvent):
        """Collect unit status."""
        if not self.unit.is_leader():
            event.add_status(BlockedStatus("Scaling is not implemented for this charm"))
            return
        if not self._upf_config_file_is_written():
            event.add_status(WaitingStatus("Waiting for UPF configuration file"))
            return
        event.add_status(ActiveStatus())


    def _configure(self, _):
        if not self.unit.is_leader():
            return
        self._generate_config_file()

    def _generate_config_file(self) -> None:
        content = render_upf_config_file(
            pfcp_address=PFCP_ADDRESS,
            n3_address=N3_ADDRESS,
            interface_name=INTERFACE_NAME,
        )
        if not self._upf_config_file_is_written() or not self._upf_config_file_content_matches(
            content=content
        ):
            self._write_upf_config_file(content=content)

    def _upf_config_file_is_written(self) -> bool:
        return self._machine.exists(path=f"{UPF_CONFIG_PATH}/{UPF_CONFIG_FILE_NAME}")

    def _upf_config_file_content_matches(self, content: str) -> bool:
        existing_content = self._machine.pull(path=f"{UPF_CONFIG_PATH}/{UPF_CONFIG_FILE_NAME}")
        try:
            return yaml.safe_load(existing_content) == yaml.safe_load(content)
        except yaml.YAMLError:
            return False

    def _write_upf_config_file(self, content: str) -> None:
        self._machine.push(path=f"{UPF_CONFIG_PATH}/{UPF_CONFIG_FILE_NAME}", source=content)
        logger.info("Pushed %s config file", UPF_CONFIG_FILE_NAME)



if __name__ == "__main__":  # pragma: nocover
    ops.main(EupfOperatorCharm)  # type: ignore
