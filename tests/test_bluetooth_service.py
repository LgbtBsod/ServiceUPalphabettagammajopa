"""
Unit Tests for Bluetooth Service

Tests for Bluetooth connectivity, call management, and device handling.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from services.bluetooth import (
    BluetoothService,
    BluetoothDevice,
    BluetoothDeviceType,
    CallInfo,
    CallState,
    get_bluetooth_service,
)
from core.logging import BluetoothConnectionError, BluetoothCallError


class TestBluetoothDevice:
    """Tests for BluetoothDevice dataclass."""
    
    def test_device_creation(self):
        """Test creating a Bluetooth device."""
        device = BluetoothDevice(
            name="Test Phone",
            address="00:1A:7D:DA:71:13",
            device_type=BluetoothDeviceType.PHONE,
            battery_level=85
        )
        
        assert device.name == "Test Phone"
        assert device.address == "00:1A:7D:DA:71:13"
        assert device.device_type == BluetoothDeviceType.PHONE
        assert device.battery_level == 85
        assert device.is_connected is False
        assert device.is_trusted is False
    
    def test_device_to_dict(self):
        """Test converting device to dictionary."""
        device = BluetoothDevice(
            name="iPhone",
            address="AA:BB:CC:DD:EE:FF",
            device_type=BluetoothDeviceType.PHONE,
            is_connected=True,
            is_trusted=True,
            battery_level=90
        )
        
        result = device.to_dict()
        
        assert result["name"] == "iPhone"
        assert result["address"] == "AA:BB:CC:DD:EE:FF"
        assert result["device_type"] == "phone"
        assert result["is_connected"] is True
        assert result["is_trusted"] is True
        assert result["battery_level"] == 90


class TestCallInfo:
    """Tests for CallInfo dataclass."""
    
    def test_call_info_creation(self):
        """Test creating call information."""
        call = CallInfo(
            call_id="abc123",
            phone_number="+79991234567",
            contact_name="John Doe",
            state=CallState.INCOMING,
            duration=0,
            direction="incoming"
        )
        
        assert call.call_id == "abc123"
        assert call.phone_number == "+79991234567"
        assert call.contact_name == "John Doe"
        assert call.state == CallState.INCOMING
        assert call.duration == 0
        assert call.direction == "incoming"
    
    def test_call_info_to_dict(self):
        """Test converting call info to dictionary."""
        call = CallInfo(
            call_id="xyz789",
            phone_number="+79997654321",
            contact_name=None,
            state=CallState.ACTIVE,
            duration=120,
            direction="outgoing"
        )
        
        result = call.to_dict()
        
        assert result["call_id"] == "xyz789"
        assert result["phone_number"] == "+79997654321"
        assert result["contact_name"] is None
        assert result["state"] == "active"
        assert result["duration"] == 120
        assert result["direction"] == "outgoing"


class TestBluetoothService:
    """Tests for BluetoothService class."""
    
    @pytest.fixture
    def service(self):
        """Create a fresh BluetoothService instance."""
        return BluetoothService()
    
    def test_service_initialization(self, service):
        """Test service initializes correctly."""
        assert service._devices == {}
        assert service._active_device is None
        assert service._current_call is None
        assert service._is_scanning is False
    
    def test_singleton_pattern(self):
        """Test singleton pattern for get_bluetooth_service."""
        service1 = get_bluetooth_service()
        service2 = get_bluetooth_service()
        assert service1 is service2
    
    @pytest.mark.asyncio
    async def test_scan_devices(self, service):
        """Test scanning for Bluetooth devices."""
        devices = await service.scan_devices(timeout=1)
        
        assert len(devices) > 0
        assert all(isinstance(d, BluetoothDevice) for d in devices)
        assert not service._is_scanning
    
    @pytest.mark.asyncio
    async def test_connect_device(self, service):
        """Test connecting to a device."""
        # First scan to populate devices
        await service.scan_devices(timeout=1)
        devices = service.get_all_devices()
        
        assert len(devices) > 0
        first_device = devices[0]
        
        # Connect
        connected = await service.connect_device(first_device.address)
        
        assert connected.is_connected is True
        assert service.is_device_connected() is True
        assert service.get_active_device() == connected
    
    @pytest.mark.asyncio
    async def test_connect_nonexistent_device(self, service):
        """Test connecting to a non-existent device raises error."""
        with pytest.raises(BluetoothConnectionError):
            await service.connect_device("00:00:00:00:00:00")
    
    @pytest.mark.asyncio
    async def test_disconnect_device(self, service):
        """Test disconnecting from a device."""
        await service.scan_devices(timeout=1)
        devices = service.get_all_devices()
        
        await service.connect_device(devices[0].address)
        assert service.is_device_connected()
        
        await service.disconnect_device()
        assert not service.is_device_connected()
    
    @pytest.mark.asyncio
    async def test_simulate_incoming_call(self, service):
        """Test simulating an incoming call."""
        await service.scan_devices(timeout=1)
        await service.connect_device(service.get_all_devices()[0].address)
        
        call_received = False
        
        def on_call(call_info):
            nonlocal call_received
            call_received = True
            assert call_info.state == CallState.INCOMING
            assert call_info.direction == "incoming"
        
        service.set_incoming_call_callback(on_call)
        await service.simulate_incoming_call("+79991234567", "Test User")
        
        assert call_received
        assert service.get_current_call() is not None
    
    @pytest.mark.asyncio
    async def test_answer_call(self, service):
        """Test answering an incoming call."""
        await service.scan_devices(timeout=1)
        await service.connect_device(service.get_all_devices()[0].address)
        await service.simulate_incoming_call("+79991234567")
        
        call = await service.answer_call()
        
        assert call.state == CallState.ACTIVE
        assert service.get_current_call().state == CallState.ACTIVE
    
    @pytest.mark.asyncio
    async def test_make_outgoing_call(self, service):
        """Test making an outgoing call."""
        await service.scan_devices(timeout=1)
        await service.connect_device(service.get_all_devices()[0].address)
        
        call = await service.make_call("+79997654321", "Contact Name")
        
        assert call.phone_number == "+79997654321"
        assert call.contact_name == "Contact Name"
        assert call.state == CallState.ACTIVE
        assert call.direction == "outgoing"
    
    @pytest.mark.asyncio
    async def test_hangup_call(self, service):
        """Test hanging up a call."""
        await service.scan_devices(timeout=1)
        await service.connect_device(service.get_all_devices()[0].address)
        await service.simulate_incoming_call("+79991234567")
        await service.answer_call()
        
        await service.hangup_call()
        
        assert service.get_current_call() is None
    
    @pytest.mark.asyncio
    async def test_answer_call_without_device(self, service):
        """Test answering call without connected device raises error."""
        with pytest.raises(BluetoothCallError):
            await service.answer_call()
    
    @pytest.mark.asyncio
    async def test_make_call_without_device(self, service):
        """Test making call without connected device raises error."""
        with pytest.raises(BluetoothCallError):
            await service.make_call("+79991234567")
    
    @pytest.mark.asyncio
    async def test_device_callbacks(self, service):
        """Test device connection/disconnection callbacks."""
        connected_callback = MagicMock()
        disconnected_callback = MagicMock()
        
        service.set_device_connected_callback(connected_callback)
        service.set_device_disconnected_callback(disconnected_callback)
        
        await service.scan_devices(timeout=1)
        devices = service.get_all_devices()
        
        await service.connect_device(devices[0].address)
        connected_callback.assert_called_once()
        
        await service.disconnect_device()
        disconnected_callback.assert_called_once()


class TestCallStates:
    """Tests for call state transitions."""
    
    @pytest.mark.asyncio
    async def test_call_state_transitions(self):
        """Test valid call state transitions."""
        service = BluetoothService()
        await service.scan_devices(timeout=1)
        await service.connect_device(service.get_all_devices()[0].address)
        
        # IDLE -> INCOMING (simulated)
        await service.simulate_incoming_call("+79991234567")
        assert service.get_current_call().state == CallState.INCOMING
        
        # INCOMING -> ACTIVE (answered)
        await service.answer_call()
        assert service.get_current_call().state == CallState.ACTIVE
        
        # ACTIVE -> TERMINATED (hung up)
        await service.hangup_call()
        assert service.get_current_call() is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
