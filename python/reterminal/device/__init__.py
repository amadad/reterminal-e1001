"""Device SDK for the current reTerminal firmware contract."""

from reterminal.device.adapter import ReTerminalDevice, SlotSnapshot
from reterminal.device.capabilities import DeviceCapabilities

__all__ = ["ReTerminalDevice", "SlotSnapshot", "DeviceCapabilities"]
