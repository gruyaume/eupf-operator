#!/usr/bin/env python3
# Copyright 2024 Guillaume Belanger
# See LICENSE file for licensing details.


"""Charm the service.

Refer to the following tutorial that will help you
develop a new k8s charm using the Operator Framework:

https://juju.is/docs/sdk/create-a-minimal-kubernetes-charm
"""

import logging

import ops

logger = logging.getLogger(__name__)


class EupfOperatorCharm(ops.CharmBase):
    """Charm the service."""

    def __init__(self, *args):
        super().__init__(*args)
        self.framework.observe(self.on.config_changed, self._on_config_changed)


    def _on_config_changed(self, event: ops.ConfigChangedEvent):
        self.unit.status = ops.ActiveStatus()



if __name__ == "__main__":  # pragma: nocover
    ops.main(EupfOperatorCharm)  # type: ignore
