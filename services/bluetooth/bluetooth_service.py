"""Bluetooth Service Module

Provides Bluetooth connectivity for call forwarding and headset functionality.
Simulates Windows-like phone integration via Bluetooth.
"""

import asyncio
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

from core.logging import BluetoothCallError, BluetoothConnectionError

logger = logging.getLogger(__name__)


class BluetoothDeviceType(Enum):
    """Types of Bluetooth devices."""

    PHONE = "phone"
    HEADSET = "headset"
    CAR = "car"
    OTHER = "other"


class CallState(Enum):
    """Phone call states."""

    IDLE = "idle"
    INCOMING = "incoming"
    OUTGOING = "outgoing"
    ACTIVE = "active"
    HELD = "held"
    TERMINATED = "terminated"


@dataclass
class BluetoothDevice:
    """Represents a Bluetooth device."""

    name: str
    address: str
    device_type: BluetoothDeviceType
    is_connected: bool = False
    is_trusted: bool = False
    battery_level: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "address": self.address,
            "device_type": self.device_type.value,
            "is_connected": self.is_connected,
            "is_trusted": self.is_trusted,
            "battery_level": self.battery_level,
        }


@dataclass
class CallInfo:
    """Information about an active call."""

    call_id: str
    phone_number: str
    contact_name: str | None
    state: CallState
    duration: int  # seconds
    direction: str  # "incoming" or "outgoing"

    def to_dict(self) -> dict[str, Any]:
        return {
            "call_id": self.call_id,
            "phone_number": self.phone_number,
            "contact_name": self.contact_name,
            "state": self.state.value,
            "duration": self.duration,
            "direction": self.direction,
        }


class BluetoothService:
    """Service for managing Bluetooth connections and call forwarding.

    Features:
    - Device discovery and pairing
    - Call forwarding from phone to PC
    - PC as Bluetooth headset (HFP profile simulation)
    - Call management (answer, hangup, mute)
    """

    def __init__(self):
        self._devices: dict[str, BluetoothDevice] = {}
        self._active_device: BluetoothDevice | None = None
        self._current_call: CallInfo | None = None
        self._is_scanning: bool = False
        self._on_device_connected: Callable[[BluetoothDevice], None] | None = None
        self._on_device_disconnected: Callable[[str], None] | None = None
        self._on_incoming_call: Callable[[CallInfo], None] | None = None
        self._on_call_state_changed: Callable[[CallInfo], None] | None = None

        logger.info("BluetoothService initialized")

    def set_device_connected_callback(
        self, callback: Callable[[BluetoothDevice], None]
    ):
        """Set callback for when a device is connected."""
        self._on_device_connected = callback

    def set_device_disconnected_callback(self, callback: Callable[[str], None]):
        """Set callback for when a device is disconnected."""
        self._on_device_disconnected = callback

    def set_incoming_call_callback(self, callback: Callable[[CallInfo], None]):
        """Set callback for incoming calls."""
        self._on_incoming_call = callback

    def set_call_state_changed_callback(self, callback: Callable[[CallInfo], None]):
        """Set callback for call state changes."""
        self._on_call_state_changed = callback

    async def scan_devices(self, timeout: int = 10) -> list[BluetoothDevice]:
        """Scan for nearby Bluetooth devices.

        Args:
            timeout: Scan duration in seconds

        Returns:
            List of discovered devices
        """
        if self._is_scanning:
            logger.warning("Scan already in progress")
            return list(self._devices.values())

        self._is_scanning = True
        logger.info(f"Starting Bluetooth scan for {timeout}s")

        try:
            # Simulate device discovery (in production, use bleak or pybluez)
            await asyncio.sleep(min(timeout, 3))  # Simulated delay

            # Mock discovered devices for demonstration
            mock_devices = [
                BluetoothDevice(
                    name="iPhone 14 Pro",
                    address="00:1A:7D:DA:71:13",
                    device_type=BluetoothDeviceType.PHONE,
                    is_trusted=True,
                    battery_level=85,
                ),
                BluetoothDevice(
                    name="Samsung Galaxy S23",
                    address="00:1B:44:11:3A:B7",
                    device_type=BluetoothDeviceType.PHONE,
                    is_trusted=False,
                    battery_level=62,
                ),
                BluetoothDevice(
                    name="AirPods Pro",
                    address="00:25:00:12:34:56",
                    device_type=BluetoothDeviceType.HEADSET,
                    is_trusted=True,
                    battery_level=90,
                ),
            ]

            for device in mock_devices:
                self._devices[device.address] = device

            logger.info(f"Found {len(mock_devices)} devices")
            return mock_devices

        except Exception as e:
            logger.exception(f"Scan failed: {e}")
            raise
        finally:
            self._is_scanning = False

    async def connect_device(self, address: str) -> BluetoothDevice:
        """Connect to a Bluetooth device.

        Args:
            address: Device MAC address

        Returns:
            Connected device
        """
        if address not in self._devices:
            raise BluetoothConnectionError(address, "Device not found")

        device = self._devices[address]

        if device.is_connected:
            logger.info(f"Device {device.name} already connected")
            return device

        logger.info(f"Connecting to {device.name} ({address})")

        try:
            # Simulate connection process
            await asyncio.sleep(1.5)

            device.is_connected = True
            self._active_device = device

            logger.info(f"Connected to {device.name}")

            if self._on_device_connected:
                self._on_device_connected(device)

            return device

        except Exception as e:
            logger.exception(f"Connection failed: {e}")
            raise BluetoothConnectionError(device.name, str(e))

    async def disconnect_device(self, address: str | None = None):
        """Disconnect from a Bluetooth device.

        Args:
            address: Device MAC address (disconnects active device if None)
        """
        addr_to_disconnect = address or (
            self._active_device.address if self._active_device else None
        )

        if not addr_to_disconnect or addr_to_disconnect not in self._devices:
            logger.warning("No device to disconnect")
            return

        device = self._devices[addr_to_disconnect]

        if not device.is_connected:
            return

        logger.info(f"Disconnecting from {device.name}")

        try:
            # If there's an active call, terminate it
            if self._current_call and self._current_call.state != CallState.TERMINATED:
                await self.hangup_call()

            device.is_connected = False

            if (
                self._active_device
                and self._active_device.address == addr_to_disconnect
            ):
                self._active_device = None

            logger.info(f"Disconnected from {device.name}")

            if self._on_device_disconnected:
                self._on_device_disconnected(addr_to_disconnect)

        except Exception as e:
            logger.exception(f"Disconnection failed: {e}")
            raise

    async def answer_call(self) -> CallInfo:
        """Answer an incoming call."""
        if not self._active_device or not self._active_device.is_connected:
            raise BluetoothCallError("", "answer", "No connected device")

        if not self._current_call or self._current_call.state != CallState.INCOMING:
            raise BluetoothCallError(
                self._active_device.name, "answer", "No incoming call"
            )

        logger.info("Answering call")

        self._current_call.state = CallState.ACTIVE
        self._current_call.direction = "incoming"

        if self._on_call_state_changed:
            self._on_call_state_changed(self._current_call)

        return self._current_call

    async def make_call(
        self, phone_number: str, contact_name: str | None = None
    ) -> CallInfo:
        """Make an outgoing call.

        Args:
            phone_number: Phone number to call
            contact_name: Optional contact name

        Returns:
            Call information
        """
        if not self._active_device or not self._active_device.is_connected:
            raise BluetoothCallError("", "make_call", "No connected device")

        call_id = str(uuid.uuid4())[:8]

        self._current_call = CallInfo(
            call_id=call_id,
            phone_number=phone_number,
            contact_name=contact_name,
            state=CallState.OUTGOING,
            duration=0,
            direction="outgoing",
        )

        logger.info(f"Making call to {phone_number}")

        # Simulate call connecting
        await asyncio.sleep(1)
        self._current_call.state = CallState.ACTIVE

        if self._on_call_state_changed:
            self._on_call_state_changed(self._current_call)

        return self._current_call

    async def hangup_call(self):
        """Terminate the current call."""
        if not self._current_call:
            logger.warning("No active call to hangup")
            return

        logger.info("Hanging up call")

        self._current_call.state = CallState.TERMINATED

        if self._on_call_state_changed:
            self._on_call_state_changed(self._current_call)

        self._current_call = None

    async def mute_call(self, muted: bool = True):
        """Mute or unmute the current call."""
        if not self._current_call or self._current_call.state != CallState.ACTIVE:
            raise BluetoothCallError("", "mute", "No active call")

        logger.info(f"Call {'muted' if muted else 'unmuted'}")
        # In production, send HFP command to device

    async def simulate_incoming_call(
        self, phone_number: str, contact_name: str | None = None
    ):
        """Simulate an incoming call (for testing).

        Args:
            phone_number: Caller's phone number
            contact_name: Optional contact name
        """
        if not self._active_device or not self._active_device.is_connected:
            return

        call_id = str(uuid.uuid4())[:8]

        self._current_call = CallInfo(
            call_id=call_id,
            phone_number=phone_number,
            contact_name=contact_name,
            state=CallState.INCOMING,
            duration=0,
            direction="incoming",
        )

        logger.info(f"Incoming call from {contact_name or phone_number}")

        if self._on_incoming_call:
            self._on_incoming_call(self._current_call)

    def get_active_device(self) -> BluetoothDevice | None:
        """Get the currently active/connected device."""
        return self._active_device

    def get_current_call(self) -> CallInfo | None:
        """Get information about the current call."""
        return self._current_call

    def get_all_devices(self) -> list[BluetoothDevice]:
        """Get all discovered devices."""
        return list(self._devices.values())

    def is_device_connected(self) -> bool:
        """Check if any device is connected."""
        return self._active_device is not None and self._active_device.is_connected


# Singleton instance
_bluetooth_service: BluetoothService | None = None


def get_bluetooth_service() -> BluetoothService:
    """Get the singleton Bluetooth service instance."""
    global _bluetooth_service
    if _bluetooth_service is None:
        _bluetooth_service = BluetoothService()
    return _bluetooth_service


__all__ = [
    "BluetoothDevice",
    "BluetoothDeviceType",
    "BluetoothService",
    "CallInfo",
    "CallState",
    "get_bluetooth_service",
]
