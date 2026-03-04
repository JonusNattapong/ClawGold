"""
Event Bus Module
================
Central communication system for all modules to publish and subscribe to events.
Enables loose coupling and intelligent coordination between components.

Usage:
    from event_bus import EventBus, EventTypes
    
    # Subscribe to events
    bus = EventBus()
    bus.subscribe(EventTypes.TRADE_EXECUTED, my_handler)
    
    # Publish events
    bus.publish(EventTypes.TRADE_EXECUTED, {'ticket': 123, 'profit': 50})
"""

import threading
import queue
from typing import Dict, List, Callable, Any, Optional
from enum import Enum, auto
from dataclasses import dataclass
from datetime import datetime
import time

from logger import get_logger

logger = get_logger(__name__)


class EventTypes(Enum):
    """System event types."""
    # Trading Events
    TRADE_EXECUTED = auto()
    TRADE_CLOSED = auto()
    POSITION_UPDATED = auto()
    ORDER_PLACED = auto()
    ORDER_CANCELLED = auto()
    
    # Market Events
    PRICE_UPDATE = auto()
    MARKET_CONDITION_CHANGED = auto()
    BREAKOUT_DETECTED = auto()
    
    # News & Calendar Events
    NEWS_HIGH_IMPACT = auto()
    ECONOMIC_EVENT_UPCOMING = auto()
    TRADING_PAUSED = auto()
    TRADING_RESUMED = auto()
    
    # Analysis Events
    SIGNAL_GENERATED = auto()
    SENTIMENT_UPDATED = auto()
    AI_RESEARCH_COMPLETED = auto()
    
    # Learning Events
    STRATEGY_OPTIMIZED = auto()
    PARAMETERS_UPDATED = auto()
    PERFORMANCE_ANALYZED = auto()
    
    # System Events
    ERROR_OCCURRED = auto()
    CONFIG_CHANGED = auto()
    SHUTDOWN_REQUESTED = auto()


@dataclass
class Event:
    """Event data structure."""
    type: EventTypes
    data: Dict[str, Any]
    timestamp: datetime
    source: str
    priority: int = 5  # 1-10, lower is higher priority


class EventBus:
    """
    Central event bus for inter-module communication.
    Thread-safe implementation with priority queue.
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        """Singleton pattern."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self._initialized = True
        self._subscribers: Dict[EventTypes, List[Callable]] = {event_type: [] for event_type in EventTypes}
        self._event_queue: queue.PriorityQueue = queue.PriorityQueue()
        self._running = False
        self._worker_thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()
        
        # Event history for learning
        self._event_history: List[Event] = []
        self._max_history = 1000
        
        logger.info("EventBus initialized")
    
    def start(self):
        """Start the event processing thread."""
        if not self._running:
            self._running = True
            self._worker_thread = threading.Thread(target=self._process_events, daemon=True)
            self._worker_thread.start()
            logger.info("EventBus started")
    
    def stop(self):
        """Stop the event processing thread."""
        self._running = False
        if self._worker_thread:
            self._worker_thread.join(timeout=5)
            logger.info("EventBus stopped")
    
    def subscribe(self, event_type: EventTypes, handler: Callable[[Event], None]):
        """
        Subscribe to an event type.
        
        Args:
            event_type: Type of event to subscribe to
            handler: Callback function to handle the event
        """
        with self._lock:
            if handler not in self._subscribers[event_type]:
                self._subscribers[event_type].append(handler)
                logger.debug(f"Handler subscribed to {event_type.name}")
    
    def unsubscribe(self, event_type: EventTypes, handler: Callable[[Event], None]):
        """Unsubscribe from an event type."""
        with self._lock:
            if handler in self._subscribers[event_type]:
                self._subscribers[event_type].remove(handler)
                logger.debug(f"Handler unsubscribed from {event_type.name}")
    
    def publish(self, event_type: EventTypes, data: Dict[str, Any], 
                source: str = "system", priority: int = 5):
        """
        Publish an event to the bus.
        
        Args:
            event_type: Type of event
            data: Event data dictionary
            source: Module that published the event
            priority: Event priority (1-10, lower is higher)
        """
        event = Event(
            type=event_type,
            data=data,
            timestamp=datetime.now(),
            source=source,
            priority=priority
        )
        
        # Add to history
        self._add_to_history(event)
        
        # Add to queue with priority
        # PriorityQueue uses smallest number first, so we invert
        self._event_queue.put((priority, event))
        
        logger.debug(f"Event published: {event_type.name} from {source}")
    
    def publish_immediate(self, event_type: EventTypes, data: Dict[str, Any],
                         source: str = "system"):
        """
        Publish and process event immediately (synchronous).
        
        Args:
            event_type: Type of event
            data: Event data dictionary
            source: Module that published the event
        """
        event = Event(
            type=event_type,
            data=data,
            timestamp=datetime.now(),
            source=source,
            priority=1
        )
        
        self._add_to_history(event)
        self._dispatch_event(event)
    
    def _process_events(self):
        """Worker thread to process events."""
        while self._running:
            try:
                # Get event with timeout to allow checking _running
                priority, event = self._event_queue.get(timeout=1)
                self._dispatch_event(event)
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Error processing event: {e}")
    
    def _dispatch_event(self, event: Event):
        """Dispatch event to all subscribers."""
        with self._lock:
            handlers = self._subscribers[event.type].copy()
        
        for handler in handlers:
            try:
                handler(event)
            except Exception as e:
                logger.error(f"Error in event handler: {e}")
    
    def _add_to_history(self, event: Event):
        """Add event to history buffer."""
        self._event_history.append(event)
        if len(self._event_history) > self._max_history:
            self._event_history.pop(0)
    
    def get_recent_events(self, event_type: Optional[EventTypes] = None, 
                         seconds: int = 3600) -> List[Event]:
        """
        Get recent events from history.
        
        Args:
            event_type: Filter by event type (optional)
            seconds: Time window in seconds
            
        Returns:
            List of recent events
        """
        cutoff = datetime.now() - timedelta(seconds=seconds)
        events = [e for e in self._event_history if e.timestamp > cutoff]
        
        if event_type:
            events = [e for e in events if e.type == event_type]
        
        return events
    
    def get_event_stats(self) -> Dict[str, Any]:
        """Get event bus statistics."""
        return {
            'total_events_processed': len(self._event_history),
            'queue_size': self._event_queue.qsize(),
            'subscribers': {et.name: len(hs) for et, hs in self._subscribers.items()},
            'is_running': self._running
        }


# Global event bus instance
event_bus = EventBus()


# Convenience functions
def publish(event_type: EventTypes, data: Dict[str, Any], source: str = "system", priority: int = 5):
    """Publish an event to the global bus."""
    event_bus.publish(event_type, data, source, priority)


def subscribe(event_type: EventTypes, handler: Callable[[Event], None]):
    """Subscribe to events on the global bus."""
    event_bus.subscribe(event_type, handler)


def unsubscribe(event_type: EventTypes, handler: Callable[[Event], None]):
    """Unsubscribe from events on the global bus."""
    event_bus.unsubscribe(event_type, handler)


if __name__ == "__main__":
    # Test event bus
    print("Testing EventBus...")
    
    received_events = []
    
    def test_handler(event):
        received_events.append(event)
        print(f"Received: {event.type.name} - {event.data}")
    
    bus = EventBus()
    bus.subscribe(EventTypes.TRADE_EXECUTED, test_handler)
    bus.start()
    
    # Publish test events
    bus.publish(EventTypes.TRADE_EXECUTED, {'ticket': 123, 'profit': 50}, source="test")
    bus.publish(EventTypes.PRICE_UPDATE, {'price': 2950.5}, source="test")
    
    # Wait for processing
    time.sleep(1)
    
    print(f"\nTotal events received: {len(received_events)}")
    print(f"Event stats: {bus.get_event_stats()}")
    
    bus.stop()
    print("Test completed!")
