from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

from litestar.di import Provide
from litestar.exceptions import ImproperlyConfiguredException
from litestar.plugins import CLIPluginProtocol, InitPluginProtocol

from litestar_saq.base import Queue, Worker
from litestar_saq.config import SAQConfig
from litestar_saq.controllers import SAQController

__all__ = ["SAQConfig", "SAQPlugin"]


if TYPE_CHECKING:
    from click import Group
    from litestar.config.app import AppConfig


T = TypeVar("T")


class SAQPlugin(InitPluginProtocol, CLIPluginProtocol):
    """SAQ plugin."""

    __slots__ = ("_config",)

    def __init__(self, config: SAQConfig) -> None:
        """Initialize ``SAQPlugin``.

        Args:
            config: configure and start SAQ.
        """
        self._config = config
        self._worker_instances: list[Worker] | None = None

    def on_cli_init(self, cli: Group) -> None:
        from litestar_saq.cli import background_worker_group

        cli.add_command(background_worker_group)
        return super().on_cli_init(cli)

    def on_app_init(self, app_config: AppConfig) -> AppConfig:
        """Configure application for use with SQLAlchemy.

        Args:
            app_config: The :class:`AppConfig <.config.app.AppConfig>` instance.
        """
        app_config.dependencies.update(
            {
                self._config.queues_dependency_key: Provide(
                    dependency=self._config.provide_queues,
                    sync_to_thread=False,
                ),
            },
        )
        if self._config.web_enabled:
            app_config.route_handlers.append(SAQController)
        app_config.on_shutdown.append(self._config.on_shutdown)
        app_config.signature_namespace.update(self._config.signature_namespace)
        return app_config

    def get_workers(self) -> list[Worker]:
        """Return workers"""
        if self._worker_instances is not None:
            return self._worker_instances
        queues = self._config.get_queues()
        self._worker_instances = []
        self._worker_instances.extend(
            Worker(
                queue=self._get_queue(queue_config.name, queues),
                functions=queue_config.tasks,
                cron_jobs=queue_config.scheduled_tasks,
                concurrency=queue_config.concurrency,
                startup=queue_config.startup,
                shutdown=queue_config.shutdown,
                before_process=queue_config.before_process,
                after_process=queue_config.after_process,
                timers=queue_config.timers,
                dequeue_timeout=queue_config.dequeue_timeout,
            )
            for queue_config in self._config.queue_configs
        )
        return self._worker_instances

    @staticmethod
    def _get_queue(name: str, queues: dict[str, Queue]) -> Queue:
        queue = queues.get(name)
        if queue is not None:
            return queue
        msg = "Could not find the specified queue.  Please check your configuration."
        raise ImproperlyConfiguredException(msg)