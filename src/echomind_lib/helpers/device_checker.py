"""
Device detection utilities for GPU/CPU selection.

Provides utilities to detect available compute devices for ML inference.
"""

import os
from dataclasses import dataclass
from enum import Enum


class DeviceType(str, Enum):
    """Available compute device types."""
    
    CPU = "cpu"
    CUDA = "cuda"
    MPS = "mps"  # Apple Silicon


@dataclass
class DeviceInfo:
    """Information about available compute devices."""
    
    device_type: DeviceType
    device_name: str
    device_index: int | None
    memory_total: int | None  # bytes
    memory_available: int | None  # bytes


class DeviceChecker:
    """
    Utility to detect and select compute devices.
    
    Usage:
        checker = DeviceChecker()
        device = checker.get_best_device()
        print(f"Using: {device.device_type}:{device.device_index}")
    """
    
    def __init__(self, prefer_gpu: bool = True):
        """
        Initialize device checker.
        
        Args:
            prefer_gpu: Prefer GPU over CPU if available
        """
        self._prefer_gpu = prefer_gpu
        self._torch_available = self._check_torch()
    
    def _check_torch(self) -> bool:
        """Check if PyTorch is available."""
        try:
            import torch
            return True
        except ImportError:
            return False
    
    def get_available_devices(self) -> list[DeviceInfo]:
        """
        Get list of all available compute devices.
        
        Returns:
            List of DeviceInfo for each available device
        """
        devices = []
        
        # Always add CPU
        devices.append(DeviceInfo(
            device_type=DeviceType.CPU,
            device_name="CPU",
            device_index=None,
            memory_total=None,
            memory_available=None,
        ))
        
        if not self._torch_available:
            return devices
        
        import torch
        
        # Check CUDA GPUs
        if torch.cuda.is_available():
            for i in range(torch.cuda.device_count()):
                props = torch.cuda.get_device_properties(i)
                mem_total = props.total_memory
                mem_free = mem_total - torch.cuda.memory_allocated(i)
                
                devices.append(DeviceInfo(
                    device_type=DeviceType.CUDA,
                    device_name=props.name,
                    device_index=i,
                    memory_total=mem_total,
                    memory_available=mem_free,
                ))
        
        # Check Apple Silicon MPS
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            devices.append(DeviceInfo(
                device_type=DeviceType.MPS,
                device_name="Apple Silicon",
                device_index=0,
                memory_total=None,
                memory_available=None,
            ))
        
        return devices
    
    def get_best_device(self) -> DeviceInfo:
        """
        Get the best available device based on preferences.
        
        Returns:
            DeviceInfo for the recommended device
        """
        devices = self.get_available_devices()
        
        if not self._prefer_gpu:
            return devices[0]  # CPU
        
        # Prefer CUDA with most memory
        cuda_devices = [d for d in devices if d.device_type == DeviceType.CUDA]
        if cuda_devices:
            return max(cuda_devices, key=lambda d: d.memory_available or 0)
        
        # Fall back to MPS
        mps_devices = [d for d in devices if d.device_type == DeviceType.MPS]
        if mps_devices:
            return mps_devices[0]
        
        # Fall back to CPU
        return devices[0]
    
    def get_torch_device(self) -> str:
        """
        Get device string for PyTorch.
        
        Returns:
            Device string like "cuda:0", "mps", or "cpu"
        """
        device = self.get_best_device()
        
        if device.device_type == DeviceType.CUDA:
            return f"cuda:{device.device_index}"
        elif device.device_type == DeviceType.MPS:
            return "mps"
        else:
            return "cpu"
    
    def is_gpu_available(self) -> bool:
        """Check if any GPU is available."""
        devices = self.get_available_devices()
        return any(d.device_type in (DeviceType.CUDA, DeviceType.MPS) for d in devices)


def get_device() -> str:
    """
    Get the best available device string for PyTorch.
    
    Convenience function that creates a DeviceChecker and returns the device string.
    
    Returns:
        Device string like "cuda:0", "mps", or "cpu"
    """
    return DeviceChecker().get_torch_device()


def is_gpu_available() -> bool:
    """Check if any GPU is available."""
    return DeviceChecker().is_gpu_available()
