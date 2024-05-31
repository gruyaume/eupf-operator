#!/usr/bin/env python3
# Copyright 2024 Guillaume Belanger
# See LICENSE file for licensing details.


"""Charm the eUPF service."""

import logging

import ops
import yaml
from charm_config import CharmConfig, CharmConfigInvalidError
from charms.grafana_agent.v0.cos_agent import COSAgentProvider
from charms.operator_libs_linux.v2.snap import SnapCache, SnapError, SnapState
from charms.sdcore_upf_k8s.v0.fiveg_n4 import N4Provides
from jinja2 import Environment, FileSystemLoader
from machine import Machine
from ops import (
    ActiveStatus,
    BlockedStatus,
    CollectStatusEvent,
    WaitingStatus,
)

EUPF_SNAP_NAME = "eupf"
EUPF_SNAP_CHANNEL = "edge"
EUPF_CONFIG_FILE_NAME = "config.yaml"
EUPF_CONFIG_PATH = "/var/snap/eupf/common"
PFCP_ADDRESS = "127.0.0.1:8805"
PFCP_IP = "127.0.0.1"
PFCP_PORT = 8805
N3_ADDRESS = "127.0.0.1"
INTERFACE_NAME = "lo"
PROMETHEUS_PORT = 9090


logger = logging.getLogger(__name__)

def render_upf_config_file(
    pfcp_address: str,
    n3_address: str,
    interface_name: str,
    metrics_port: int,
) -> str:
    """Render the configuration file for the 5G UPF service.

    Args:
        pfcp_address: The PFCP address.
        n3_address: The N3 address.
        interface_name: The interface name.
        metrics_port: The port for the metrics.
    """
    jinja2_environment = Environment(loader=FileSystemLoader("src/templates/"))
    template = jinja2_environment.get_template(f"{EUPF_CONFIG_FILE_NAME}.j2")
    content = template.render(
        pfcp_address=pfcp_address,
        n3_address=n3_address,
        interface_name=interface_name,
        metrics_port=metrics_port,
    )
    return content


class EupfOperatorCharm(ops.CharmBase):
    """Charm the service."""

    def __init__(self, *args):
        super().__init__(*args)
        self.framework.observe(self.on.collect_unit_status, self._on_collect_status)
        self._machine = Machine()
        self._cos_agent = COSAgentProvider(
            self,
            scrape_configs=[
                {
                    "static_configs": [{"targets": [f"*:{PROMETHEUS_PORT}"]}],
                }
            ],
        )
        try:
            self._charm_config: CharmConfig = CharmConfig.from_charm(charm=self)
        except CharmConfigInvalidError:
            return
        self.fiveg_n4_provider = N4Provides(charm=self, relation_name="fiveg_n4")
        self.framework.observe(self.on.config_changed, self._configure)

    def _on_collect_status(self, event: CollectStatusEvent):
        """Collect unit status.

        The event handler runs after every juju event and sets the unit status.
        """
        if not self.unit.is_leader():
            event.add_status(BlockedStatus("Scaling is not implemented for this charm"))
            return
        if not self._upf_config_file_is_written():
            event.add_status(WaitingStatus("Waiting for UPF configuration file"))
            return
        event.add_status(ActiveStatus())


    def _configure(self, _):
        """Configure the eUPF Operator.

        This event handler is the charm's central hook. It is triggered by any event
        that affects the charm's state.

        It install the eUPF snap and generate the configuration file.
        """
        if not self.unit.is_leader():
            return
        self._install_eupf_snap()
        self._generate_config_file()
        self._start_eupf_service()

    def _install_eupf_snap(self) -> None:
        if self._eupf_snap_installed():
            return
        try:
            snap_cache = SnapCache()
            upf_snap = snap_cache[EUPF_SNAP_NAME]
            upf_snap.ensure(
                SnapState.Latest,
                channel=EUPF_SNAP_CHANNEL,
            )
            upf_snap.hold()
            logger.info("eUPF snap installed")
        except SnapError as e:
            logger.error("An exception occurred when installing the eUPF snap. Reason: %s", str(e))
            raise e

    def _eupf_snap_installed(self) -> bool:
        snap_cache = SnapCache()
        upf_snap = snap_cache[EUPF_SNAP_NAME]
        return upf_snap.state == SnapState.Latest

    def _generate_config_file(self) -> None:
        content = render_upf_config_file(
            pfcp_address=PFCP_ADDRESS,
            n3_address=N3_ADDRESS,
            interface_name=INTERFACE_NAME,
            metrics_port=PROMETHEUS_PORT,
        )
        if not self._upf_config_file_is_written() or not self._upf_config_file_content_matches(
            content=content
        ):
            self._write_upf_config_file(content=content)

    def _upf_config_file_is_written(self) -> bool:
        return self._machine.exists(path=f"{EUPF_CONFIG_PATH}/{EUPF_CONFIG_FILE_NAME}")

    def _upf_config_file_content_matches(self, content: str) -> bool:
        existing_content = self._machine.pull(path=f"{EUPF_CONFIG_PATH}/{EUPF_CONFIG_FILE_NAME}")
        try:
            return yaml.safe_load(existing_content) == yaml.safe_load(content)
        except yaml.YAMLError:
            return False

    def _write_upf_config_file(self, content: str) -> None:
        self._machine.push(path=f"{EUPF_CONFIG_PATH}/{EUPF_CONFIG_FILE_NAME}", source=content)
        logger.info("Pushed %s config file", EUPF_CONFIG_FILE_NAME)

    def _start_eupf_service(self) -> None:
        if self._eupf_service_started():
            return
        snap_cache = SnapCache()
        eupf_snap = snap_cache[EUPF_SNAP_NAME]
        eupf_snap.start(services=["eupf"])
        logger.info("eUPF service started")

    def _eupf_service_started(self) -> bool:
        snap_cache = SnapCache()
        eupf_snap = snap_cache[EUPF_SNAP_NAME]
        upf_services = eupf_snap.services
        return upf_services["eupf"]["active"]

    def _update_fiveg_n4_relation_data(self) -> None:
        """Publish UPF hostname and the N4 port in the `fiveg_n4` relation data bag."""
        fiveg_n4_relations = self.model.relations.get("fiveg_n4")
        if not fiveg_n4_relations:
            logger.info("No `fiveg_n4` relations found.")
            return
        for fiveg_n4_relation in fiveg_n4_relations:
            self.fiveg_n4_provider.publish_upf_n4_information(
                relation_id=fiveg_n4_relation.id,
                upf_hostname=self._get_n4_upf_hostname(),
                upf_n4_port=PFCP_PORT,
            )

    def _get_n4_upf_hostname(self) -> str:
        """Return the UPF hostname to be exposed over the `fiveg_n4` relation.

        If a configuration is provided, it is returned. If that is
        not available, returns the IP address of the core interface.

        Returns:
            str: Hostname of the UPF
        """
        if configured_hostname := self._charm_config.external_upf_hostname:
            return configured_hostname
        else:
            return self._charm_config.core_ip


if __name__ == "__main__":  # pragma: nocover
    ops.main(EupfOperatorCharm)  # type: ignore
