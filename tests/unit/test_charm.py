# Copyright 2024 Guillaume Belanger
# See LICENSE file for licensing details.

import unittest

import ops
import ops.testing
from charm import EupfOperatorCharm


class TestCharm(unittest.TestCase):
    def setUp(self):
        self.harness = ops.testing.Harness(EupfOperatorCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    def test_httpbin_pebble_ready(self):
        self.assertEqual(1, 1)
