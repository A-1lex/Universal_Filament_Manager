"""Notification delivery port."""

from typing import Protocol

from ufm.application.dto import DeliveryResult, Notification
from ufm.domain.value_objects import EntityId


class NotificationProvider(Protocol):
    async def send(self, notice: Notification, delivery_key: EntityId) -> DeliveryResult: ...
