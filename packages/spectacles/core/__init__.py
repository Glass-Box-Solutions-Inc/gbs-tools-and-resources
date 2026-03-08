"""
Spectacles Core Module
Agent orchestration, state machine, and browser specialist
"""

from .state_machine import StateMachine, StateCheckpoint

__all__ = [
    "StateMachine",
    "StateCheckpoint",
]
