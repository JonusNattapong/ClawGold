"""
Economic Calendar Module
========================
AI-powered economic calendar data extraction from ForexFactory/Investing.com
with high-impact event alerts and auto-pause trading functionality.

Usage:
    from economic_calendar import EconomicCalendar
    
    calendar = EconomicCalendar()
    events = calendar.get_today_events()
    high_impact = calendar.get_upcoming_high_impact_events(minutes=30)
    
    if calendar.should_pause_trading():
        print("High impact event soon - pausing trading")
"""

import os
import re
import json
import sqlite3
import subprocess
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, asdict
from pathlib import Path
from contextlib import contextmanager

from logger import get_logger

try:
    from notifier import get_notifier, notify_system
    NOTIFIER_AVAILABLE = True
except ImportError:
    NOTIFIER_AVAILABLE = False

logger = get_logger(__name__)


@dataclass
class EconomicEvent:
    """Economic event data model."""
    event_id: str
    title: str
    currency: str
    impact: str  # high, medium, low
    datetime: datetime
    actual: Optional[str] = None
    forecast: Optional[str] = None
    previous: Optional[str] = None
    source: str = "forexfactory"
    alerted: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        data = asdict(self)
        data['datetime'] = self.datetime.isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'EconomicEvent':
        """Create from dictionary."""
        data = data.copy()
        if isinstance(data.get('datetime'), str):
            data['datetime'] = datetime.fromisoformat(data['datetime'])
        return cls(**data)
    
    def is_high_impact(self) -> bool:
        """Check if this is a high impact event."""
        return self.impact.lower() == 'high'
    
    def time_until(self) -> timedelta:
        """Get time until event."""
        return self.datetime - datetime.now()
    
    def is_upcoming(self, minutes: int = 60) -> bool:
        """Check if event is upcoming within specified minutes."""
        time_until = self.time_until()
        return timedelta(0) < time_until <= timedelta(minutes=minutes)


class EconomicCalendar:
    """
    AI-powered Economic Calendar with data extraction and trading protection.
    """
    
    # High impact events that should pause trading
    HIGH_IMPACT_KEYWORDS = [
        'non-farm payrolls', 'nfp', 'fomc', 'fed interest rate',
        'cpi', 'inflation rate', 'gdp', 'unemployment rate',
        'retail sales', 'pmi', 'ism', ' ECB ', 'BOE', 'BOJ',
        'treasury secretary', 'fed chair', 'powell'
    ]
    
    def __init__(self, db_path: str = "data/economic_calendar.db",
                 check_interval: int = 300):
        """
        Initialize Economic Calendar.
        
        Args:
            db_path: Path to SQLite database
            check_interval: How often to check for events (seconds)
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.check_interval = check_interval
        self._init_db()
        self._last_alert_time = 0
        
        # Trading pause state
        self.trading_paused = False
        self.pause_until = None
        
    @contextmanager
    def _connect(self):
        """Database connection context manager."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
    
    def _init_db(self):
        """Initialize database tables."""
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS economic_events (
                    event_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    currency TEXT NOT NULL,
                    impact TEXT NOT NULL,
                    event_datetime TIMESTAMP NOT NULL,
                    actual TEXT,
                    forecast TEXT,
                    previous TEXT,
                    source TEXT DEFAULT 'forexfactory',
                    alerted BOOLEAN DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_event_datetime 
                ON economic_events(event_datetime)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_impact 
                ON economic_events(impact)
            """)
            
            conn.commit()
    
    def _call_ai_tool(self, tool: str, prompt: str) -> Optional[str]:
        """Call an AI CLI tool to extract data."""
        try:
            if tool == 'opencode':
                cmd = ['opencode', 'run', prompt]
            elif tool == 'kilocode':
                cmd = ['kilo', 'run', prompt]
            elif tool == 'gemini':
                cmd = ['gemini', prompt]
            else:
                return None
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                return result.stdout.strip()
            else:
                logger.error(f"AI tool {tool} failed: {result.stderr}")
                return None
                
        except subprocess.TimeoutExpired:
            logger.error(f"AI tool {tool} timed out")
            return None
        except Exception as e:
            logger.error(f"Error calling AI tool {tool}: {e}")
            return None
    
    def fetch_events_with_ai(self, date: Optional[datetime] = None) -> List[EconomicEvent]:
        """
        Fetch economic events using AI tools to scrape ForexFactory/Investing.com.
        
        Args:
            date: Date to fetch events for (default: today)
            
        Returns:
            List of EconomicEvent objects
        """
        if date is None:
            date = datetime.now()
        
        date_str = date.strftime('%Y-%m-%d')
        
        # Create prompt for AI to extract economic calendar data
        prompt = f"""Visit forexfactory.com/calendar and extract all economic events for {date_str}.

For each event, provide:
1. Event title/name
2. Currency (USD, EUR, GBP, etc.)
3. Impact level (high, medium, low)
4. Event time
5. Actual value (if released)
6. Forecast value
7. Previous value

Format the output as JSON array:
[
  {{
    "title": "Non-Farm Payrolls",
    "currency": "USD",
    "impact": "high",
    "time": "08:30",
    "actual": "250K",
    "forecast": "200K",
    "previous": "180K"
  }}
]

Only include events from forexfactory.com. Return valid JSON only."""

        events = []
        
        # Try multiple AI tools
        for tool in ['opencode', 'kilocode', 'gemini']:
            logger.info(f"Fetching calendar data with {tool}...")
            response = self._call_ai_tool(tool, prompt)
            
            if response:
                try:
                    # Try to extract JSON from response
                    json_match = re.search(r'\[.*\]', response, re.DOTALL)
                    if json_match:
                        data = json.loads(json_match.group())
                    else:
                        data = json.loads(response)
                    
                    if isinstance(data, list):
                        for item in data:
                            event = self._parse_event(item, date)
                            if event:
                                events.append(event)
                        
                        if events:
                            logger.info(f"Successfully fetched {len(events)} events with {tool}")
                            break
                            
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse {tool} response: {e}")
                    continue
                except Exception as e:
                    logger.error(f"Error processing {tool} response: {e}")
                    continue
        
        if not events:
            logger.warning("Failed to fetch events from any AI tool")
        
        return events
    
    def _parse_event(self, data: Dict, date: datetime) -> Optional[EconomicEvent]:
        """Parse event data from AI response."""
        try:
            title = data.get('title', '')
            if not title:
                return None
            
            # Parse time
            time_str = data.get('time', '00:00')
            try:
                hour, minute = map(int, time_str.split(':')[:2])
                event_datetime = date.replace(hour=hour, minute=minute, second=0, microsecond=0)
            except:
                event_datetime = date
            
            # Determine impact
            impact = data.get('impact', 'low').lower()
            if impact not in ['high', 'medium', 'low']:
                # Try to determine from title
                impact = self._determine_impact(title)
            
            # Generate unique ID
            event_id = f"{event_datetime.strftime('%Y%m%d%H%M')}_{data.get('currency', 'XXX')}_{title[:20].replace(' ', '_')}"
            
            return EconomicEvent(
                event_id=event_id,
                title=title,
                currency=data.get('currency', 'USD').upper(),
                impact=impact,
                datetime=event_datetime,
                actual=data.get('actual'),
                forecast=data.get('forecast'),
                previous=data.get('previous'),
                source='forexfactory'
            )
            
        except Exception as e:
            logger.error(f"Error parsing event: {e}")
            return None
    
    def _determine_impact(self, title: str) -> str:
        """Determine impact level from event title."""
        title_lower = title.lower()
        
        for keyword in self.HIGH_IMPACT_KEYWORDS:
            if keyword in title_lower:
                return 'high'
        
        # Medium impact keywords
        medium_keywords = ['retail', 'manufacturing', 'services', 'housing', 'consumer']
        for keyword in medium_keywords:
            if keyword in title_lower:
                return 'medium'
        
        return 'low'
    
    def save_events(self, events: List[EconomicEvent]):
        """Save events to database."""
        with self._connect() as conn:
            cursor = conn.cursor()
            
            for event in events:
                cursor.execute("""
                    INSERT OR REPLACE INTO economic_events 
                    (event_id, title, currency, impact, event_datetime, actual, 
                     forecast, previous, source, alerted, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (
                    event.event_id, event.title, event.currency, event.impact,
                    event.datetime, event.actual, event.forecast, event.previous,
                    event.source, event.alerted
                ))
            
            conn.commit()
            logger.info(f"Saved {len(events)} events to database")
    
    def get_today_events(self) -> List[EconomicEvent]:
        """Get all events for today."""
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow = today + timedelta(days=1)
        
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM economic_events 
                WHERE event_datetime >= ? AND event_datetime < ?
                ORDER BY event_datetime ASC
            """, (today, tomorrow))
            
            rows = cursor.fetchall()
            return [self._row_to_event(row) for row in rows]
    
    def get_upcoming_events(self, hours: int = 24) -> List[EconomicEvent]:
        """Get upcoming events within specified hours."""
        now = datetime.now()
        future = now + timedelta(hours=hours)
        
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM economic_events 
                WHERE event_datetime >= ? AND event_datetime <= ?
                ORDER BY event_datetime ASC
            """, (now, future))
            
            rows = cursor.fetchall()
            return [self._row_to_event(row) for row in rows]
    
    def get_upcoming_high_impact_events(self, minutes: int = 60) -> List[EconomicEvent]:
        """Get high impact events upcoming within specified minutes."""
        events = self.get_upcoming_events(hours=24)
        return [e for e in events if e.is_high_impact() and e.is_upcoming(minutes)]
    
    def _row_to_event(self, row: sqlite3.Row) -> EconomicEvent:
        """Convert database row to EconomicEvent."""
        return EconomicEvent(
            event_id=row['event_id'],
            title=row['title'],
            currency=row['currency'],
            impact=row['impact'],
            datetime=datetime.fromisoformat(row['event_datetime']),
            actual=row['actual'],
            forecast=row['forecast'],
            previous=row['previous'],
            source=row['source'],
            alerted=bool(row['alerted'])
        )
    
    def should_pause_trading(self, pause_before_minutes: int = 30, 
                            resume_after_minutes: int = 30) -> bool:
        """
        Check if trading should be paused due to upcoming high impact event.
        
        Args:
            pause_before_minutes: Pause trading N minutes before event
            resume_after_minutes: Resume trading N minutes after event
            
        Returns:
            True if trading should be paused
        """
        now = datetime.now()
        
        # Check if we're in a manual pause period
        if self.trading_paused and self.pause_until:
            if now < self.pause_until:
                return True
            else:
                # Auto-resume
                self.trading_paused = False
                self.pause_until = None
                logger.info("Auto-resumed trading after high impact event")
                if NOTIFIER_AVAILABLE:
                    notify_system("Trading auto-resumed. High impact event period ended.", "info")
        
        # Get upcoming high impact events
        events = self.get_upcoming_events(hours=48)
        
        for event in events:
            if not event.is_high_impact():
                continue
            
            time_until = event.time_until()
            
            # Event is coming up soon - pause trading
            if timedelta(0) < time_until <= timedelta(minutes=pause_before_minutes):
                self.trading_paused = True
                self.pause_until = event.datetime + timedelta(minutes=resume_after_minutes)
                
                logger.warning(f"Trading paused for high impact event: {event.title}")
                
                # Send alert
                if NOTIFIER_AVAILABLE:
                    msg = f"Trading PAUSED\n\nEvent: {event.title}\nTime: {event.datetime.strftime('%H:%M')}\nImpact: HIGH\n\nTrading will resume at {self.pause_until.strftime('%H:%M')}"
                    notify_system(msg, "warning")
                
                # Mark as alerted
                self._mark_event_alerted(event.event_id)
                
                return True
            
            # Event just passed - check if we should still be paused
            if -timedelta(minutes=resume_after_minutes) <= time_until < timedelta(0):
                self.trading_paused = True
                self.pause_until = event.datetime + timedelta(minutes=resume_after_minutes)
                return True
        
        return False
    
    def _mark_event_alerted(self, event_id: str):
        """Mark event as alerted in database."""
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE economic_events SET alerted = 1 WHERE event_id = ?",
                (event_id,)
            )
            conn.commit()
    
    def update_calendar(self):
        """Fetch and update calendar with latest events."""
        logger.info("Updating economic calendar...")
        
        # Fetch today's and tomorrow's events
        events = []
        for days in [0, 1]:
            date = datetime.now() + timedelta(days=days)
            day_events = self.fetch_events_with_ai(date)
            events.extend(day_events)
        
        if events:
            self.save_events(events)
            logger.info(f"Calendar updated with {len(events)} events")
        else:
            logger.warning("No events fetched during calendar update")
    
    def get_next_high_impact_event(self) -> Optional[EconomicEvent]:
        """Get the next upcoming high impact event."""
        events = self.get_upcoming_events(hours=168)  # 1 week
        high_impact = [e for e in events if e.is_high_impact()]
        return high_impact[0] if high_impact else None
    
    def format_event_summary(self, event: EconomicEvent) -> str:
        """Format event for display/notification."""
        impact_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(event.impact, "⚪")
        
        msg = f"""
{impact_emoji} {event.impact.upper()} IMPACT EVENT

<b>{event.title}</b>
<b>Currency:</b> {event.currency}
<b>Time:</b> {event.datetime.strftime('%Y-%m-%d %H:%M')}
"""
        if event.forecast:
            msg += f"<b>Forecast:</b> {event.forecast}\n"
        if event.previous:
            msg += f"<b>Previous:</b> {event.previous}\n"
        if event.actual:
            msg += f"<b>Actual:</b> {event.actual}\n"
        
        return msg


def get_calendar() -> EconomicCalendar:
    """Get singleton EconomicCalendar instance."""
    return EconomicCalendar()


if __name__ == "__main__":
    # Test the calendar
    calendar = EconomicCalendar()
    
    print("Updating calendar...")
    calendar.update_calendar()
    
    print("\nToday's events:")
    for event in calendar.get_today_events():
        print(f"  [{event.impact.upper()}] {event.datetime.strftime('%H:%M')} - {event.title} ({event.currency})")
    
    print("\nUpcoming high impact events (next 60 min):")
    for event in calendar.get_upcoming_high_impact_events(minutes=60):
        print(f"  {event.datetime.strftime('%H:%M')} - {event.title}")
    
    print(f"\nShould pause trading: {calendar.should_pause_trading()}")
