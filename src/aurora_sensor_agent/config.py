"""Agent configuration, validated at startup.

Kept minimal for milestone 1; sampling interval, thresholds, transport, and credentials are
added in later milestones.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class AgentConfig(BaseModel):
    """Static configuration for a single device agent."""

    device_id: str = Field(min_length=1)
    clinic_id: str = Field(min_length=1)
    sample_interval_seconds: float = Field(default=30.0, gt=0)
