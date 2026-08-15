"""State Machine Module - Order Lifecycle Management

Uses `transitions` library for robust state machine implementation.
Follows SRP: Only handles state transitions and validation.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from transitions import Machine, State


class OrderStatus(StrEnum):
    """Order status states - Single Source of Truth (SSOT)"""

    DRAFT = "draft"
    NEW = "new"
    DIAGNOSTICS = "diagnostics"
    WAITING_APPROVAL = "waiting_approval"
    WAITING_PARTS = "waiting_parts"
    IN_PROGRESS = "in_progress"
    TESTING = "testing"
    READY = "ready"
    CLOSED = "closed"
    CANCELLED = "cancelled"


@dataclass
class StateTransition:
    """Represents a state transition event"""

    from_state: OrderStatus
    to_state: OrderStatus
    triggered_by: str
    timestamp: datetime = field(default_factory=datetime.now)
    comment: str | None = None


class OrderStateMachine:
    """State machine for order lifecycle management.

    Uses transitions library for:
    - State validation
    - Transition guards
    - Callbacks on enter/exit
    - Event logging

    Thread-safe: Machine operations are atomic
    """

    # Define all states
    STATES = [
        State(name=OrderStatus.DRAFT.value, on_enter="_on_enter_draft"),
        State(name=OrderStatus.NEW.value, on_enter="_on_enter_new"),
        State(name=OrderStatus.DIAGNOSTICS.value, on_enter="_on_enter_diagnostics"),
        State(
            name=OrderStatus.WAITING_APPROVAL.value,
            on_enter="_on_enter_waiting_approval",
        ),
        State(name=OrderStatus.WAITING_PARTS.value, on_enter="_on_enter_waiting_parts"),
        State(name=OrderStatus.IN_PROGRESS.value, on_enter="_on_enter_in_progress"),
        State(name=OrderStatus.TESTING.value, on_enter="_on_enter_testing"),
        State(name=OrderStatus.READY.value, on_enter="_on_enter_ready"),
        State(name=OrderStatus.CLOSED.value, on_enter="_on_enter_closed"),
        State(name=OrderStatus.CANCELLED.value, on_enter="_on_enter_cancelled"),
    ]

    # Define transitions with guards
    TRANSITIONS = [
        # From DRAFT
        {
            "trigger": "create_order",
            "source": OrderStatus.DRAFT.value,
            "dest": OrderStatus.NEW.value,
        },
        # From NEW
        {
            "trigger": "start_diagnostics",
            "source": OrderStatus.NEW.value,
            "dest": OrderStatus.DIAGNOSTICS.value,
        },
        {
            "trigger": "cancel_order",
            "source": OrderStatus.NEW.value,
            "dest": OrderStatus.CANCELLED.value,
        },
        # From DIAGNOSTICS
        {
            "trigger": "approve_estimate",
            "source": OrderStatus.DIAGNOSTICS.value,
            "dest": OrderStatus.WAITING_PARTS.value,
        },
        {
            "trigger": "request_client_approval",
            "source": OrderStatus.DIAGNOSTICS.value,
            "dest": OrderStatus.WAITING_APPROVAL.value,
        },
        {
            "trigger": "cancel_order",
            "source": OrderStatus.DIAGNOSTICS.value,
            "dest": OrderStatus.CANCELLED.value,
        },
        # From WAITING_APPROVAL
        {
            "trigger": "client_approved",
            "source": OrderStatus.WAITING_APPROVAL.value,
            "dest": OrderStatus.WAITING_PARTS.value,
        },
        {
            "trigger": "client_rejected",
            "source": OrderStatus.WAITING_APPROVAL.value,
            "dest": OrderStatus.CANCELLED.value,
        },
        # From WAITING_PARTS
        {
            "trigger": "parts_received",
            "source": OrderStatus.WAITING_PARTS.value,
            "dest": OrderStatus.IN_PROGRESS.value,
        },
        {
            "trigger": "cancel_order",
            "source": OrderStatus.WAITING_PARTS.value,
            "dest": OrderStatus.CANCELLED.value,
        },
        # From IN_PROGRESS
        {
            "trigger": "complete_repair",
            "source": OrderStatus.IN_PROGRESS.value,
            "dest": OrderStatus.TESTING.value,
        },
        # From TESTING
        {
            "trigger": "pass_testing",
            "source": OrderStatus.TESTING.value,
            "dest": OrderStatus.READY.value,
        },
        {
            "trigger": "fail_testing",
            "source": OrderStatus.TESTING.value,
            "dest": OrderStatus.IN_PROGRESS.value,
        },
        # From READY
        {
            "trigger": "deliver_to_client",
            "source": OrderStatus.READY.value,
            "dest": OrderStatus.CLOSED.value,
        },
        # From any state to CANCELLED (except already terminal)
        {
            "trigger": "cancel_order",
            "source": "*",
            "dest": OrderStatus.CANCELLED.value,
            "conditions": "is_not_terminal",
        },
    ]

    def __init__(self, order_id: str, initial_status: OrderStatus = OrderStatus.DRAFT):
        self.order_id = order_id
        self.current_status = initial_status
        self.transition_history: list[StateTransition] = []
        self.callbacks: dict[str, Callable] = {}

        # Initialize state machine
        self.machine = Machine(
            model=self,
            states=self.STATES,
            transitions=self.TRANSITIONS,
            initial=initial_status.value,
            send_event=True,
            queued=True,  # Enable queued transitions for thread safety
        )

        # Register transition logger (use after_state_change for reliable event data)
        self.machine.after_state_change.append(self._log_transition)

    def _register_transition_logger(self):
        """Register callback to log all transitions"""
        for transition in self.TRANSITIONS:
            trigger = transition["trigger"]
            self.machine.get_transitions(trigger=trigger, source=transition["source"])[
                0
            ].before.append(self._log_transition)

    def _log_transition(self, event):
        """Log transition after it happens (called from after_state_change)"""
        # Access state from model directly (transitions library stores state in model.state)
        source_state = event.transition.source
        dest_state = event.transition.dest
        trigger_name = event.event.name

        transition = StateTransition(
            from_state=OrderStatus(source_state),
            to_state=OrderStatus(dest_state),
            triggered_by=trigger_name,
        )
        self.transition_history.append(transition)

        # Call registered callback if exists
        if callback := self.callbacks.get(trigger_name):
            callback(self.order_id, transition)

    def _register_transition_logger(self):
        """Register callback to log all transitions (deprecated - use after_state_change)"""
        # Kept for backward compatibility

    # State entry callbacks (to be overridden or configured)
    def _on_enter_draft(self, event):
        pass

    def _on_enter_new(self, event):
        pass

    def _on_enter_diagnostics(self, event):
        pass

    def _on_enter_waiting_approval(self, event):
        pass

    def _on_enter_waiting_parts(self, event):
        pass

    def _on_enter_in_progress(self, event):
        pass

    def _on_enter_testing(self, event):
        pass

    def _on_enter_ready(self, event):
        pass

    def _on_enter_closed(self, event):
        pass

    def _on_enter_cancelled(self, event):
        pass

    def is_not_terminal(self) -> bool:
        """Guard condition: check if state is not terminal"""
        return self.current_status not in [OrderStatus.CLOSED, OrderStatus.CANCELLED]

    def can_trigger(self, trigger_name: str) -> bool:
        """Check if a trigger is available in current state"""
        return hasattr(self, trigger_name)

    def get_available_triggers(self) -> list[str]:
        """Get all available triggers for current state"""
        return [
            t["trigger"]
            for t in self.TRANSITIONS
            if t["source"] == "*" or t["source"] == self.current_status.value
        ]

    def register_callback(self, trigger: str, callback: Callable):
        """Register callback for specific trigger"""
        self.callbacks[trigger] = callback

    def get_history(self) -> list[StateTransition]:
        """Get full transition history"""
        return self.transition_history.copy()

    def __repr__(self) -> str:
        return (
            f"OrderStateMachine(order_id={self.order_id}, status={self.current_status})"
        )
