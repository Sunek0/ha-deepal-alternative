"""Supervised live MQTT session for the international Deepal platform.

The one-shot exchange in :mod:`deepal.intl` is still the fallback. This module
keeps one connection open for the ``protocolType: MQTT`` vehicles of an account,
subscribes to their telemetry topics, logs in once and dispatches unsolicited
reports without blocking the socket reader.

The car publishes full snapshots and small deltas. The session accumulates the
raw parameters per vehicle before parsing, so a two-field window report does
not reset the rest of the condition.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import random
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, Optional

from deepal.exceptions import (
    CA_TOKEN_ERROR_CODES,
    DeepalAPIError,
    DeepalMqttAuthRejected,
)
from deepal.location import find_location
from deepal.models import Vehicle, VehicleCondition
from deepal.mqtt import (
    MqttBrokerSettings,
    MqttKeepalive,
    MqttSessionState,
    MqttSessionStats,
    MqttTopics,
    build_puback_packet,
    build_publish_packet,
    build_subscribe_packet,
    condition_request_payload,
    condition_request_services,
    config_mqtt_identity,
    new_request_id,
    normalize_s05_params,
    parse_publish,
    parse_suback,
    read_packet,
    resolve_mqtt_topics,
    s05_report_timestamp,
    topic_device_id,
    wake_request_payload,
    wake_request_services,
)

logger = logging.getLogger("deepal_sdk")

ConditionCallback = Callable[[str, VehicleCondition], None]
EventCallback = Callable[[str, dict[str, Any]], None]
StateCallback = Callable[[str, dict[str, Any]], None]
RefreshCallback = Callable[[str], Awaitable[bool]]


@dataclass
class _VehicleContext:
    """Per-vehicle bootstrap material and accumulated telemetry."""

    vehicle: Vehicle
    config: dict[str, Any]
    topics: MqttTopics
    basic_info: dict[str, Any]
    login_did: str
    device_did: str
    accumulated: dict[str, Any] = field(default_factory=dict)
    latest_condition: Optional[VehicleCondition] = None
    last_report_timestamp: Optional[int] = None
    last_response_timestamp: Optional[int] = None
    model_code: Optional[str] = None


@dataclass
class _SessionOutcome:
    """Result of one connection attempt."""

    error: Optional[BaseException] = None
    duration: float = 0.0
    connected: bool = False


class DeepalIntlMqttSession:
    """One supervised live MQTT session for a group of MQTT vehicles."""

    def __init__(
        self,
        client: Any,
        vehicles: Sequence[Vehicle],
        *,
        on_condition: Optional[ConditionCallback] = None,
        on_event: Optional[EventCallback] = None,
        on_state: Optional[StateCallback] = None,
        refresh_session: Optional[RefreshCallback] = None,
        backoff_initial: float = 1.0,
        backoff_max: float = 300.0,
        conflict_window: float = 10.0,
        conflict_threshold: int = 3,
        conflict_delay: float = 300.0,
        stable_after: float = 60.0,
        request_timeout: float = 20.0,
    ) -> None:
        self.client = client
        self._requested_vehicles = list(vehicles)
        self._on_condition = on_condition
        self._on_event = on_event
        self._on_state = on_state
        self._refresh_session = refresh_session
        self._backoff_initial = max(0.05, float(backoff_initial))
        self._backoff_max = max(self._backoff_initial, float(backoff_max))
        self._conflict_window = max(0.1, float(conflict_window))
        self._conflict_threshold = max(1, int(conflict_threshold))
        self._conflict_delay = max(1.0, float(conflict_delay))
        self._stable_after = max(1.0, float(stable_after))
        self._request_timeout = max(1.0, float(request_timeout))

        self._contexts: dict[str, _VehicleContext] = {}
        self._state = MqttSessionState.STOPPED
        self._stats = MqttSessionStats()
        self._task: Optional[asyncio.Task[None]] = None
        self._stop_event = asyncio.Event()
        self._connected_event = asyncio.Event()
        self._write_lock = asyncio.Lock()
        self._close_lock = asyncio.Lock()
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._resolved: Optional[MqttTopics] = None
        self._secret_key: Optional[str] = None
        self._settings: Optional[MqttBrokerSettings] = None
        self._logout: Any = None
        self._keepalive: Optional[MqttKeepalive] = None
        self._keepalive_task: Optional[asyncio.Task[None]] = None
        self._pending: dict[str, tuple[str, asyncio.Future[Any], str]] = {}
        self._short_lived = 0

    # ------------------------------------------------------------------
    # Public surface
    # ------------------------------------------------------------------
    @property
    def state(self) -> str:
        """Return the current session state."""
        return self._state.value

    @property
    def is_connected(self) -> bool:
        """Return whether the session is connected and logged in."""
        return self._state is MqttSessionState.CONNECTED and self._writer is not None

    @property
    def is_active(self) -> bool:
        """Return whether the supervisor is trying to keep the session alive."""
        return self._state is not MqttSessionState.STOPPED

    @property
    def is_connecting(self) -> bool:
        """Return whether a connection attempt is in progress."""
        return self._state is MqttSessionState.CONNECTING

    @property
    def vehicles(self) -> tuple[Vehicle, ...]:
        """Return the vehicles covered by this session."""
        return tuple(context.vehicle for context in self._contexts.values())

    def supports(self, vehicle_id: str) -> bool:
        """Return whether the session covers a vehicle."""
        return vehicle_id in self._contexts

    async def wait_connected(self, timeout: float) -> bool:
        """Wait for the session to connect, returning whether it did.

        The one-shot fallback uses this to wait only while a connection attempt
        is in flight instead of failing immediately or opening a second socket.
        """
        if self.is_connected:
            return True
        if timeout <= 0:
            return False
        try:
            await asyncio.wait_for(self._connected_event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            return False
        return self.is_connected

    def stats(self) -> MqttSessionStats:
        """Return a snapshot of the session counters."""
        return replace(self._stats, state=self._state.value)

    async def start(self) -> None:
        """Start the supervisor if it is not running yet."""
        if self._task is not None and not self._task.done():
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(
            self._supervisor(), name="deepal-intl-mqtt-live"
        )

    async def stop(self) -> None:
        """Stop the supervisor and close the connection."""
        self._stop_event.set()
        await self._close_current()
        task = self._task
        self._task = None
        if task is not None and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._set_state(MqttSessionState.STOPPED)

    async def request_condition(
        self,
        vehicle_id: str,
        *,
        timeout: Optional[float] = None,
        require_timestamp: bool = False,
    ) -> VehicleCondition:
        """Request one condition snapshot on the live session."""
        context = self._context(vehicle_id)
        if not self.is_connected or self._writer is None or not self._secret_key:
            raise DeepalAPIError("The live MQTT session is not connected.")
        topic = context.topics.properties_publish
        if not topic:
            raise DeepalAPIError(
                "The live MQTT session has no properties/get topic."
            )
        request_id = new_request_id(context.device_did)
        request = condition_request_payload(
            context.device_did,
            context.login_did,
            self._secret_key,
            request_id,
            basic_info=context.basic_info,
        )
        future = asyncio.get_running_loop().create_future()
        self._pending[request_id] = (vehicle_id, future, "condition")
        self._emit_mqtt(
            "publish",
            vehicle_id=vehicle_id,
            stage="live_condition",
            topic=topic,
            payload=request,
            services=condition_request_services(),
            request_id=request_id,
        )
        try:
            try:
                await self._write(
                    build_publish_packet(
                        topic,
                        request,
                        qos=self._effective_qos,
                        packet_id=self.client._next_mqtt_packet_id(),
                    )
                )
            except (ConnectionError, OSError, RuntimeError) as err:
                raise DeepalAPIError(
                    "The live MQTT condition request could not be sent."
                ) from err
            try:
                condition = await asyncio.wait_for(
                    future,
                    timeout=self._request_timeout if timeout is None else timeout,
                )
            except asyncio.TimeoutError as err:
                raise DeepalAPIError(
                    "The live MQTT condition request timed out."
                ) from err
        finally:
            self._pending.pop(request_id, None)
        if require_timestamp and context.last_response_timestamp is None:
            raise DeepalAPIError("The live condition did not carry a report timestamp.")
        return condition

    async def wake(
        self, vehicle_id: str, *, timeout: Optional[float] = None
    ) -> None:
        """Wake one vehicle on the live session."""
        context = self._context(vehicle_id)
        if not self.is_connected or self._writer is None or not self._secret_key:
            raise DeepalAPIError("The live MQTT session is not connected.")
        request_id = new_request_id(context.device_did)
        payload = wake_request_payload(
            context.device_did,
            context.login_did,
            self._secret_key,
            request_id,
            basic_info=context.basic_info,
        )
        topic = context.topics.properties_set_publish
        if not topic:
            raise DeepalAPIError(
                "The live MQTT session has no properties/set topic for the wake."
            )
        future = asyncio.get_running_loop().create_future()
        self._pending[request_id] = (vehicle_id, future, "wake")
        self._emit_mqtt(
            "publish",
            vehicle_id=vehicle_id,
            stage="live_wake",
            topic=topic,
            payload=payload,
            services=wake_request_services(request_id),
            request_id=request_id,
        )
        try:
            try:
                await self._write(
                    build_publish_packet(
                        topic,
                        payload,
                        qos=self._wake_qos,
                        packet_id=self.client._next_mqtt_packet_id(),
                    )
                )
            except (ConnectionError, OSError, RuntimeError) as err:
                raise DeepalAPIError(
                    "The live MQTT wake request could not be sent."
                ) from err
            try:
                await asyncio.wait_for(
                    future,
                    timeout=self._request_timeout if timeout is None else timeout,
                )
            except asyncio.TimeoutError as err:
                raise DeepalAPIError(
                    "The live MQTT wake request timed out."
                ) from err
        finally:
            self._pending.pop(request_id, None)

    async def wait_for_report(
        self,
        vehicle_id: str,
        *,
        previous_timestamp: Optional[int] = None,
        interval: float = 5.0,
        timeout: float = 60.0,
    ) -> Optional[VehicleCondition]:
        """Wait for a newer report, using the live reports and condition probes."""
        context = self._context(vehicle_id)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + max(0.05, timeout)
        if not self.is_connected:
            raise DeepalAPIError("The live MQTT session is not connected.")
        while loop.time() < deadline:
            current = context.latest_condition
            if current is not None:
                if previous_timestamp is None:
                    return current
                if (
                    context.last_report_timestamp is not None
                    and context.last_report_timestamp > previous_timestamp
                ):
                    return current
            remaining = deadline - loop.time()
            if remaining <= 0:
                break
            try:
                condition = await self.request_condition(
                    vehicle_id,
                    timeout=min(interval, remaining),
                    require_timestamp=previous_timestamp is not None,
                )
            except (DeepalAPIError, asyncio.TimeoutError):
                await asyncio.sleep(min(interval, max(0.0, deadline - loop.time())))
                continue
            if previous_timestamp is None or (
                condition.last_updated_timestamp is not None
                and condition.last_updated_timestamp > previous_timestamp
            ):
                return condition
            await asyncio.sleep(min(interval, max(0.0, deadline - loop.time())))
        return None

    # ------------------------------------------------------------------
    # Supervisor
    # ------------------------------------------------------------------
    async def _supervisor(self) -> None:
        attempt = 0
        auth_retried = False
        try:
            while not self._stop_event.is_set():
                self._set_state(
                    MqttSessionState.CONNECTING,
                    attempt=attempt + 1,
                )
                outcome: Optional[_SessionOutcome] = None
                try:
                    outcome = await self._connect_once()
                except asyncio.CancelledError:
                    raise
                except Exception as err:  # noqa: BLE001 - supervised session
                    outcome = _SessionOutcome(error=err)
                    if (
                        not auth_retried
                        and self._refresh_session is not None
                        and self._is_auth_rejection(err)
                    ):
                        self._stats.last_error = (
                            f"{type(err).__name__}: {err}"
                        )
                        try:
                            refreshed = await self._refresh_session(str(err))
                        except Exception as refresh_err:  # noqa: BLE001
                            logger.warning(
                                "Deepal live MQTT session refresh failed: %s",
                                refresh_err,
                            )
                            refreshed = False
                        if refreshed:
                            auth_retried = True
                            continue

                if self._stop_event.is_set():
                    break
                if outcome is None:
                    outcome = _SessionOutcome()
                if outcome.connected:
                    auth_retried = False
                if outcome.duration >= self._stable_after:
                    self._short_lived = 0
                    attempt = 0
                if outcome.connected and outcome.duration < self._conflict_window:
                    self._short_lived += 1
                elif outcome.connected:
                    self._short_lived = 0

                if outcome.error is not None:
                    self._stats.last_error = (
                        f"{type(outcome.error).__name__}: {outcome.error}"
                    )
                    self._emit_mqtt(
                        "error",
                        stage="live",
                        error=str(outcome.error),
                        error_type=type(outcome.error).__name__,
                    )
                    logger.warning(
                        "Deepal live MQTT session error: %s", outcome.error
                    )

                if self._short_lived >= self._conflict_threshold:
                    delay = self._conflict_delay
                    self._set_state(
                        MqttSessionState.CONFLICT,
                        retry_in=delay,
                        short_lived=self._short_lived,
                    )
                    self._emit_mqtt(
                        "session_conflict",
                        stage="live",
                        short_lived=self._short_lived,
                        retry_in=delay,
                    )
                else:
                    delay = min(
                        self._backoff_max,
                        self._backoff_initial * (2 ** min(attempt, 10)),
                    )
                    delay *= random.uniform(0.8, 1.2)
                    self._set_state(
                        MqttSessionState.BACKOFF,
                        retry_in=round(delay, 1),
                        attempt=attempt + 1,
                    )
                attempt += 1
                await self._wait_or_stop(delay)
        finally:
            await self._close_current()
            self._set_state(MqttSessionState.STOPPED)

    async def _connect_once(self) -> _SessionOutcome:
        contexts = await self._bootstrap_contexts()
        if not contexts:
            raise DeepalAPIError("No MQTT vehicle could be bootstrapped.")
        first = contexts[0]
        token = await self.client.get_mqtt_token()
        connected_at: Optional[float] = None
        # Hold the transport lock only while the connection is being set up.
        # The reader loop runs unlocked so a one-shot call can acquire the
        # lock, see the connected session and delegate to it instead of
        # waiting for the whole connection lifetime.
        async with self.client._live_mqtt_lock:
            reader, writer, resolved, basic_info, secret_key, _plan, settings = (
                await self.client._open_s05_mqtt(
                    first.config,
                    token,
                    vehicle_id=first.vehicle.car_id,
                )
            )
            self._reader = reader
            self._writer = writer
            self._resolved = resolved
            self._secret_key = secret_key
            self._settings = settings
            self._logout = self.client._logout_context(
                resolved, basic_info, secret_key, settings
            )
            try:
                if secret_key is None:
                    raise DeepalAPIError(
                        "The live MQTT login did not return a secret key."
                    )
                await self._subscribe_extra(contexts, settings)
                self._stats.connects += 1
                if self._stats.connects > 1:
                    self._stats.reconnects += 1
                connected_at = time.monotonic()
                self._stats.connected_since = time.time()
                self._stats.subscriptions = tuple(
                    dict.fromkeys(
                        topic
                        for context in contexts
                        for topic in context.topics.subscriptions
                    )
                )
                self._set_state(
                    MqttSessionState.CONNECTED,
                    qos=settings.effective_qos,
                    keepalive=settings.effective_keepalive,
                    subscriptions=len(self._stats.subscriptions),
                )
                self._connected_event.set()
                self._keepalive = MqttKeepalive(
                    writer,
                    self._write_lock,
                    settings.effective_keepalive,
                    on_timeout=self._on_keepalive_timeout,
                )
                self._keepalive_task = asyncio.create_task(
                    self._keepalive.run(self._stop_event),
                    name="deepal-intl-mqtt-keepalive",
                )
            except BaseException:
                await self._close_current()
                raise
        try:
            started_at = connected_at if connected_at is not None else time.monotonic()
            error = await self._reader_loop(settings)
            return _SessionOutcome(
                error=error,
                duration=time.monotonic() - started_at,
                connected=True,
            )
        finally:
            await self._close_current()

    async def _bootstrap_contexts(self) -> list[_VehicleContext]:
        contexts: list[_VehicleContext] = []
        group_key: Optional[tuple[str, int, str, str]] = None
        first_error: Optional[BaseException] = None
        for vehicle in self._requested_vehicles:
            if not self.client.is_mqtt_vehicle(vehicle) or self.client.is_sda_mqtt_vehicle(
                vehicle
            ):
                continue
            try:
                config = await self.client.get_mqtt_config(vehicle.car_id)
            except Exception as err:  # noqa: BLE001 - one vehicle must not kill all
                if first_error is None:
                    first_error = err
                logger.warning(
                    "Deepal live MQTT bootstrap failed for %s: %s",
                    vehicle.car_id,
                    err,
                )
                continue
            topics = resolve_mqtt_topics(
                config, fallback_did=self.client.mqtt_client_id
            )
            settings = self.client._resolve_broker_settings(config)
            if (
                not settings.usable
                or not topics.login_did
                or not topics.device_did
            ):
                logger.warning(
                    "Deepal live MQTT bootstrap for %s has no usable broker/topics",
                    vehicle.car_id,
                )
                continue
            client_id, username = config_mqtt_identity(
                config,
                topics.login_did,
                client_id=self.client.mqtt_client_id,
                username=self.client.mqtt_username,
            )
            key = (settings.host, settings.port, client_id or "", username or "")
            if group_key is None:
                group_key = key
            elif key != group_key:
                logger.warning(
                    "Deepal live MQTT session ignores %s: it resolves a different "
                    "broker identity than the first vehicle",
                    vehicle.car_id,
                )
                continue
            basic_info = self.client._mqtt_basic_identifiers(
                config, topics.login_did
            )
            contexts.append(
                _VehicleContext(
                    vehicle=vehicle,
                    config=config,
                    topics=topics,
                    basic_info=basic_info,
                    login_did=topics.login_did,
                    device_did=topics.device_did,
                    model_code=vehicle.model_code,
                )
            )
        if not contexts and first_error is not None:
            raise first_error
        self._contexts = {
            context.vehicle.car_id: context for context in contexts
        }
        return contexts

    async def _subscribe_extra(
        self,
        contexts: Sequence[_VehicleContext],
        settings: MqttBrokerSettings,
    ) -> None:
        """Subscribe to the topics of vehicles beyond the first one."""
        if self._resolved is None or self._writer is None or self._reader is None:
            return
        existing = set(self._resolved.subscriptions)
        extra = sorted(
            {
                topic
                for context in contexts
                for topic in context.topics.subscriptions
                if topic not in existing
            }
        )
        if not extra:
            return
        subscribe_id = self.client._next_mqtt_packet_id()
        self._writer.write(
            build_subscribe_packet(
                subscribe_id, extra, qos=settings.effective_qos
            )
        )
        await self._writer.drain()
        prefetched: list[tuple[str, dict[str, Any], Optional[int]]] = []
        while True:
            if self._stop_event.is_set():
                raise DeepalAPIError(
                    "The live MQTT session was stopped during subscription."
                )
            try:
                first, body = await asyncio.wait_for(
                    read_packet(
                        self._reader, max_size=settings.maximum_packet_size
                    ),
                    timeout=settings.connect_timeout,
                )
            except asyncio.TimeoutError as err:
                raise DeepalAPIError(
                    "The live MQTT broker did not acknowledge the extra "
                    "subscription."
                ) from err
            packet_type = first >> 4
            if packet_type == 9:  # SUBACK
                packet_id, reasons = parse_suback(first, body)
                if (
                    packet_id != subscribe_id
                    or not reasons
                    or any(reason >= 0x80 for reason in reasons)
                ):
                    raise DeepalAPIError(
                        "The live MQTT broker rejected the extra subscription."
                    )
                break
            if packet_type == 3:
                try:
                    topic, payload, packet_id = parse_publish(first, body)
                except ValueError:
                    continue
                if packet_id is not None:
                    self._writer.write(build_puback_packet(packet_id))
                    await self._writer.drain()
                prefetched.append((topic, payload, packet_id))
                continue
            if packet_type == 13:
                continue
        for topic, payload, _packet_id in prefetched:
            await self._dispatch(topic, payload)

    async def _reader_loop(
        self, settings: MqttBrokerSettings
    ) -> Optional[BaseException]:
        if self._reader is None:
            return None
        while not self._stop_event.is_set():
            try:
                first, body = await read_packet(
                    self._reader, max_size=settings.maximum_packet_size
                )
            except asyncio.CancelledError:
                raise
            except (asyncio.IncompleteReadError, ConnectionError, OSError) as err:
                return err
            except ValueError as err:
                self._stats.dropped += 1
                return err
            packet_type = first >> 4
            if packet_type == 13:  # PINGRESP
                if self._keepalive is not None:
                    self._keepalive.note_pingresp()
                continue
            if packet_type != 3:
                continue
            try:
                topic, payload, packet_id = parse_publish(first, body)
            except ValueError as err:
                self._stats.dropped += 1
                logger.debug(
                    "Deepal live MQTT: skipping malformed PUBLISH (%s)", err
                )
                continue
            if packet_id is not None:
                try:
                    await self._write(build_puback_packet(packet_id))
                except (ConnectionError, OSError, RuntimeError) as err:
                    return err
            await self._dispatch(topic, payload)
        return None

    # ------------------------------------------------------------------
    # Message dispatch
    # ------------------------------------------------------------------
    async def _dispatch(self, topic: str, payload: Mapping[str, Any]) -> None:
        self._stats.messages += 1
        self._stats.last_message_at = time.time()
        request_id = payload.get("r")
        pending = self._pending.get(request_id) if isinstance(request_id, str) else None
        if pending is not None:
            vehicle_id, future, kind = pending
            if kind == "wake":
                if topic.endswith("/properties/set/res"):
                    result = self.client._service_result_from_payload(
                        payload, self._secret_key or ""
                    )
                    if result is None:
                        self._reject(
                            future,
                            DeepalAPIError(
                                "The vehicle wake response carried no result."
                            ),
                        )
                    else:
                        code, success = result
                        if success or code in ("000000", "0", "00000"):
                            self._resolve(future, None)
                        else:
                            self._reject(
                                future,
                                DeepalAPIError(
                                    f"Vehicle wake was rejected: {code}", code=code
                                ),
                            )
                    self._emit_receive(vehicle_id, topic, payload, {})
                    return

        params = self.client._s05_params_from_payload(
            payload, self._secret_key or ""
        )
        context = self._vehicle_for(topic, payload, pending)
        is_event = any(
            marker in topic
            for marker in ("/events/", "/msg/", "/strategy/", "/server/event")
        )
        if is_event:
            self._stats.events += 1
            vehicle_id = context.vehicle.car_id if context is not None else ""
            self._emit_receive(vehicle_id, topic, payload, params)
            self._call_event(vehicle_id, topic, payload)
            return
        if params:
            self._stats.reports += 1
            if context is None:
                self._stats.dropped += 1
                logger.debug(
                    "Deepal live MQTT: condition without a matching vehicle"
                )
                return
            model_code = (
                self.client._model_code_from_payload(payload) or context.model_code
            )
            pending_condition = (
                pending is not None
                and pending[2] == "condition"
                and pending[0] == context.vehicle.car_id
            )
            timestamp = s05_report_timestamp(params)
            if (
                timestamp is not None
                and context.last_report_timestamp is not None
                and timestamp < context.last_report_timestamp
            ):
                self._stats.dropped += 1
                if pending_condition:
                    context.last_response_timestamp = timestamp
                    self._resolve_condition_request(
                        pending[1],
                        context,
                        model_code,
                        source="legacy-mqtt",
                    )
                self._emit_receive(
                    context.vehicle.car_id,
                    topic,
                    payload,
                    params,
                    dropped="stale",
                )
                return
            changed = self._accumulate(context, params, model_code)
            if timestamp is not None and (
                context.last_report_timestamp is None
                or timestamp > context.last_report_timestamp
            ):
                context.last_report_timestamp = timestamp
            if pending_condition:
                # A response to our own condition request is not an
                # unsolicited push: resolve the caller without publishing a
                # second condition or scheduling an overlay for it.
                context.last_response_timestamp = timestamp
                self._resolve_condition_request(
                    pending[1], context, model_code, source="legacy-mqtt"
                )
                self._emit_receive(
                    context.vehicle.car_id,
                    topic,
                    payload,
                    params,
                    solicited=True,
                )
                return
            if not changed:
                self._stats.dropped += 1
                return
            condition = self._parse_condition(
                context, model_code, source="mqtt-push"
            )
            context.latest_condition = condition
            self._resolve_pending_conditions(context)
            self._emit_receive(
                context.vehicle.car_id, topic, payload, params
            )
            self._call_condition(context.vehicle.car_id, condition)
            return

        if pending is not None:
            if pending[2] == "condition":
                self._reject(
                    pending[1],
                    DeepalAPIError(
                        "The live MQTT condition response carried no parameters."
                    ),
                )
            self._emit_receive(
                pending[0], topic, payload, params
            )
            return
        self._stats.dropped += 1

    def _accumulate(
        self,
        context: _VehicleContext,
        params: Mapping[str, Any],
        model_code: Optional[str],
    ) -> bool:
        before = dict(context.accumulated)
        context.accumulated.update(params)
        if model_code:
            context.model_code = model_code
        return context.accumulated != before

    def _parse_condition(
        self,
        context: _VehicleContext,
        model_code: Optional[str],
        *,
        source: str = "mqtt-push",
    ) -> VehicleCondition:
        raw = dict(context.accumulated)
        condition = self.client.parse_condition(
            normalize_s05_params(raw, model_code=model_code),
            context.vehicle.car_id,
            vin=context.vehicle.vin,
            model_code=model_code,
        )
        location = find_location(raw)
        if location is not None:
            condition.latitude, condition.longitude = location
        condition.mqtt_raw_data = raw
        condition.condition_source = source
        return condition

    def _vehicle_for(
        self,
        topic: str,
        payload: Mapping[str, Any],
        pending: Optional[tuple[str, asyncio.Future[Any], str]],
    ) -> Optional[_VehicleContext]:
        basic = payload.get("b")
        if isinstance(basic, Mapping):
            car_id = basic.get("cid")
            if isinstance(car_id, str) and car_id in self._contexts:
                return self._contexts[car_id]
        did = payload.get("did")
        if isinstance(did, str):
            for context in self._contexts.values():
                if did in (context.device_did, context.login_did):
                    return context
        topic_did = topic_device_id(topic)
        if topic_did:
            for context in self._contexts.values():
                if topic_did in (context.device_did, context.login_did):
                    return context
        if pending is not None:
            return self._contexts.get(pending[0])
        return None

    def _resolve_condition_request(
        self,
        future: asyncio.Future[Any],
        context: _VehicleContext,
        model_code: Optional[str],
        *,
        source: str,
    ) -> None:
        if future.done():
            return
        condition = self._parse_condition(context, model_code, source=source)
        context.latest_condition = condition
        self._resolve(future, condition)

    def _resolve_pending_conditions(self, context: _VehicleContext) -> None:
        for request_id, (vehicle_id, future, kind) in list(self._pending.items()):
            if vehicle_id != context.vehicle.car_id or kind != "condition":
                continue
            if future.done():
                self._pending.pop(request_id, None)
                continue
            context.last_response_timestamp = context.last_report_timestamp
            self._resolve_condition_request(
                future,
                context,
                context.model_code,
                source="mqtt-push",
            )

    # ------------------------------------------------------------------
    # Transport helpers
    # ------------------------------------------------------------------
    async def _write(self, data: bytes) -> None:
        async with self._write_lock:
            writer = self._writer
            if writer is None:
                raise DeepalAPIError("The live MQTT session is closed.")
            writer.write(data)
            await writer.drain()
            if self._keepalive is not None:
                self._keepalive.note_send()

    async def _close_current(self) -> None:
        async with self._close_lock:
            task = self._keepalive_task
            self._keepalive_task = None
            if task is not None and not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            self._keepalive = None
            async with self._write_lock:
                writer = self._writer
                self._writer = None
            logout = self._logout
            self._reader = None
            self._connected_event.clear()
            if writer is not None:
                try:
                    await self.client._close_s05_mqtt(
                        writer,
                        vehicle_id=(
                            next(iter(self._contexts), None)
                            if self._contexts
                            else None
                        ),
                        logout=logout,
                        timeout=(
                            self._settings.connect_timeout
                            if self._settings is not None
                            else 15.0
                        ),
                    )
                except Exception as err:  # noqa: BLE001 - close must be best effort
                    logger.debug("Deepal live MQTT close failed: %s", err)
            self._fail_pending("The live MQTT session closed.")
            self._logout = None
            self._resolved = None
            self._secret_key = None
            self._stats.connected_since = None

    async def _on_keepalive_timeout(self, reason: str) -> None:
        self._stats.last_error = reason
        self._emit_mqtt("timeout", stage="live_keepalive", reason=reason)
        writer = self._writer
        if writer is not None:
            writer.close()

    def _fail_pending(self, reason: str) -> None:
        for _request_id, (_vehicle_id, future, _kind) in list(
            self._pending.items()
        ):
            if not future.done():
                future.set_exception(DeepalAPIError(reason))
        self._pending.clear()

    @staticmethod
    def _resolve(future: asyncio.Future[Any], value: Any) -> None:
        if not future.done():
            future.set_result(value)

    @staticmethod
    def _reject(future: asyncio.Future[Any], error: BaseException) -> None:
        if not future.done():
            future.set_exception(error)

    async def _wait_or_stop(self, delay: float) -> None:
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=delay)
        except asyncio.TimeoutError:
            pass

    def _context(self, vehicle_id: str) -> _VehicleContext:
        context = self._contexts.get(vehicle_id)
        if context is None:
            raise DeepalAPIError(
                f"The live MQTT session does not cover vehicle {vehicle_id}."
            )
        return context

    @staticmethod
    def _is_auth_rejection(err: BaseException) -> bool:
        if isinstance(err, DeepalMqttAuthRejected):
            return True
        return getattr(err, "code", None) in CA_TOKEN_ERROR_CODES

    @property
    def _effective_qos(self) -> int:
        return self._settings.effective_qos if self._settings else 1

    @property
    def _wake_qos(self) -> int:
        if self._settings is None:
            return 1
        if self._settings.maximum_qos == 0:
            return 0
        return 1

    # ------------------------------------------------------------------
    # Callbacks and diagnostics
    # ------------------------------------------------------------------
    def _set_state(self, state: MqttSessionState, **details: Any) -> None:
        if state is self._state and not details:
            return
        self._state = state
        self._stats.state = state.value
        self._emit_mqtt("session_state", stage="live", state=state.value, **details)
        if state is not MqttSessionState.CONNECTED:
            self._connected_event.clear()
        if self._on_state is not None:
            try:
                self._on_state(state.value, dict(details))
            except Exception:  # noqa: BLE001 - callback must not break the session
                logger.exception("Deepal live MQTT state callback failed")

    def _call_condition(self, vehicle_id: str, condition: VehicleCondition) -> None:
        if self._on_condition is None:
            return
        try:
            self._on_condition(vehicle_id, condition)
        except Exception:  # noqa: BLE001
            logger.exception("Deepal live MQTT condition callback failed")

    def _call_event(
        self, vehicle_id: str, topic: str, payload: Mapping[str, Any]
    ) -> None:
        if self._on_event is None:
            return
        try:
            self._on_event(
                vehicle_id,
                {
                    "topic": topic,
                    "mt": payload.get("mt"),
                    "request_id": payload.get("r"),
                    "payload": dict(payload),
                },
            )
        except Exception:  # noqa: BLE001
            logger.exception("Deepal live MQTT event callback failed")

    def _emit_mqtt(self, event: str, **data: Any) -> None:
        emitter = getattr(self.client, "_emit_mqtt", None)
        if callable(emitter):
            emitter(event, **data)

    def _emit_receive(
        self,
        vehicle_id: str,
        topic: str,
        payload: Mapping[str, Any],
        params: Mapping[str, Any],
        **extra: Any,
    ) -> None:
        self._emit_mqtt(
            "receive",
            vehicle_id=vehicle_id or None,
            stage="live",
            topic=topic,
            payload=dict(payload),
            params=dict(params),
            decoded=bool(params),
            request_id=payload.get("r"),
            **extra,
        )
