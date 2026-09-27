"""Real-hardware implementations of the seams.

Everything in this package imports its hardware library **lazily**, inside a method, so the
package imports cleanly on any laptop with no ``smbus2``/``pyserial``/``gpiozero`` installed and
no hardware wired up. Import-time is safe; only actually opening a device needs the hardware.
"""
