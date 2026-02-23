from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from langfuse import Langfuse

from app.core.config import Settings


class ObservabilityService:
    def __init__(self, settings: Settings):
        self._client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            base_url=settings.langfuse_base_url,
        )

    @property
    def client(self) -> Langfuse:
        return self._client

    @contextmanager
    def trace(
        self,
        name: str,
        input_data: Any | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Iterator[Any]:
        if not hasattr(self._client, "start_as_current_observation"):
            yield None
            return

        with self._client.start_as_current_observation(
            as_type="span",
            name=name,
            input=input_data,
            metadata=metadata,
        ) as span:
            yield span

    @contextmanager
    def span(
        self,
        name: str,
        input_data: Any | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Iterator[Any]:
        if not hasattr(self._client, "start_as_current_observation"):
            yield None
            return

        with self._client.start_as_current_observation(
            as_type="span",
            name=name,
            input=input_data,
            metadata=metadata,
        ) as span:
            yield span

    @contextmanager
    def generation(
        self,
        name: str,
        input_data: Any | None = None,
        metadata: dict[str, Any] | None = None,
        model: str | None = None,
        model_parameters: dict[str, Any] | None = None,
    ) -> Iterator[Any]:
        if not hasattr(self._client, "start_as_current_observation"):
            yield None
            return

        with self._client.start_as_current_observation(
            as_type="generation",
            name=name,
            input=input_data,
            metadata=metadata,
            model=model,
            model_parameters=model_parameters,
        ) as gen:
            yield gen

    def annotate(self, span: Any, output_data: Any) -> None:
        if hasattr(span, "update"):
            span.update(output=output_data)
        self.flush()

    def flush(self) -> None:
        self._client.flush()
