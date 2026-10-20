"""Coordinate conversion for DPI-unaware legacy controls on scaled monitors."""
import ctypes
from ctypes import wintypes
from contextlib import contextmanager


@contextmanager
def physical_dpi_context():
    user = ctypes.windll.user32
    user.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
    old = user.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
    try:
        yield
    finally:
        if old:
            user.SetThreadDpiAwarenessContext(ctypes.c_void_p(old))


def physical_client_point(hwnd, x, y):
    user = ctypes.windll.user32
    user.GetWindowDpiAwarenessContext.restype = ctypes.c_void_p
    user.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
    target_context = user.GetWindowDpiAwarenessContext(hwnd)
    old = user.SetThreadDpiAwarenessContext(ctypes.c_void_p(target_context))
    point = wintypes.POINT(x, y)
    try:
        if not user.ClientToScreen(hwnd, ctypes.byref(point)):
            raise ctypes.WinError()
        if not user.LogicalToPhysicalPointForPerMonitorDPI(hwnd, ctypes.byref(point)):
            raise ctypes.WinError()
        return point.x, point.y
    finally:
        if old:
            user.SetThreadDpiAwarenessContext(ctypes.c_void_p(old))
