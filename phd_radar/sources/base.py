"""信息源基类与注册表。"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from ..config import Profile, SourceConfig
from ..fetch import Fetcher
from ..models import SourceResult

log = logging.getLogger(__name__)

_REGISTRY: dict[str, type["BaseSource"]] = {}


class BaseSource(ABC):
    kind = "base"

    def __init__(self, config: SourceConfig, fetcher: Fetcher, profile: Profile) -> None:
        self.config = config
        self.options = config.options
        self.fetcher = fetcher
        self.profile = profile
        self.name = config.name or config.type

    @abstractmethod
    def collect(self) -> SourceResult: ...

    def result(self, **kwargs) -> SourceResult:
        return SourceResult(name=self.name, kind=self.kind, ok=True, **kwargs)

    def failure(self, error: Exception | str) -> SourceResult:
        message = f"{error}"
        log.warning("source failed name=%s error=%s", self.name, message)
        return SourceResult(name=self.name, kind=self.kind, ok=False, error=message[:400])


def register(cls: type[BaseSource]) -> type[BaseSource]:
    _REGISTRY[cls.kind] = cls
    return cls


def build_source(config: SourceConfig, fetcher: Fetcher, profile: Profile) -> BaseSource:
    if config.type not in _REGISTRY:
        raise ValueError(f"未知的信息源类型: {config.type}")
    return _REGISTRY[config.type](config, fetcher, profile)
