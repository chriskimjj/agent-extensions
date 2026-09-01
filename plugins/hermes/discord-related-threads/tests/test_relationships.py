from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
import uuid
from pathlib import Path


PLUGIN_SOURCE = Path(__file__).resolve().parents[1] / "__init__.py"


class RelationshipBaselineTest(unittest.TestCase):
    def setUp(self) -> None:
        self._old_home = os.environ.get("HERMES_HOME")
        self._test_home = tempfile.TemporaryDirectory(
            prefix="discord-related-threads-test-",
        )
        os.environ["HERMES_HOME"] = self._test_home.name

        module_name = f"discord_related_threads_test_{uuid.uuid4().hex}"
        spec = importlib.util.spec_from_file_location(module_name, PLUGIN_SOURCE)
        if spec is None or spec.loader is None:
            self.fail("could not load plugin source")
        self.plugin = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.plugin)
        self.plugin._init_db()

    def tearDown(self) -> None:
        if self._old_home is None:
            os.environ.pop("HERMES_HOME", None)
        else:
            os.environ["HERMES_HOME"] = self._old_home
        self._test_home.cleanup()

    def test_link_list_and_unlink_are_bidirectional(self) -> None:
        created = self.plugin.link_threads(
            "test-guild",
            "thread-a",
            "thread-b",
            "depends-on",
            "baseline",
        )
        self.assertTrue(created["success"])

        forward = self.plugin.list_relations("test-guild", "thread-a")
        reverse = self.plugin.list_relations("test-guild", "thread-b")
        self.assertEqual(forward["relations"][0]["related_thread_id"], "thread-b")
        self.assertEqual(reverse["relations"][0]["related_thread_id"], "thread-a")

        removed = self.plugin.unlink_threads("test-guild", "thread-a", "thread-b")
        self.assertTrue(removed["success"])
        self.assertEqual(
            self.plugin.list_relations("test-guild", "thread-a")["relations"],
            [],
        )
        self.assertEqual(
            self.plugin.list_relations("test-guild", "thread-b")["relations"],
            [],
        )

    def test_registration_uses_stock_lifecycle_and_only_minimal_host_hooks(self) -> None:
        class FakeContext:
            def __init__(self) -> None:
                self.tools = []
                self.hooks = {}
                self.platform_handlers = {}
                self.unload_callbacks = []

            def register_tool(self, **kwargs) -> None:
                self.tools.append(kwargs["name"])

            def register_hook(self, name, callback) -> None:
                self.hooks[name] = callback

            def supports_hook(self, name) -> bool:
                return name in {
                    "pre_gateway_dispatch",
                    "gateway_control_message",
                    "gateway_history_message",
                }

            def register_platform_handler(self, platform, callback) -> None:
                self.platform_handlers[platform] = callback

            def spawn_task(self, coro, *, name=None):
                raise AssertionError("connect-time task must not start at registration")

            def on_unload(self, callback) -> None:
                self.unload_callbacks.append(callback)

        context = FakeContext()
        self.plugin.register(context)

        self.assertEqual(context.tools, ["discord_thread_links"])
        self.assertTrue(
            {
                "transform_llm_output",
                "pre_gateway_dispatch",
                "gateway_history_message",
                "gateway_control_message",
            }.issubset(context.hooks)
        )
        self.assertEqual(set(context.platform_handlers), {"discord"})
        self.assertEqual(len(context.unload_callbacks), 1)
        self.assertEqual(self.plugin._THREAD_ATTENTION_RUNTIME.state, "disabled")
        self.assertIsNone(
            self.plugin._THREAD_ATTENTION_RUNTIME._host_contract_error
        )


if __name__ == "__main__":
    unittest.main()
