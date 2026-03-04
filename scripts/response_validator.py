"""
Response Validator Module
===========================
PydanticAI-powered structured response validation for trading signals and analysis.

Ensures all AI responses conform to strict schemas before being used for trading decisions.
Provides type safety, validation, and structured output parsing.

Usage:
    from response_validator import get_response_validator, TradeSignal
    
    validator = get_response_validator()
    signal = validator.parse_trading_signal("BUY signal with confidence 0.85")
    # Returns validated TradeSignal object with type safety
"""

from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field, validator
from logger import get_logger

logger = get_logger(__name__)


# ─────────────────────────────────────────────────────
# Signal Enums
# ─────────────────────────────────────────────────────

class SignalType(str, Enum):
    """Trading signal direction."""
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"
    NEUTRAL = "neutral"


class Timeframe(str, Enum):
    """Trading timeframes."""
    M15 = "M15"
    M30 = "M30"
    H1 = "H1"
    H4 = "H4"
    D1 = "D1"


class SentimentType(str, Enum):
    """Market sentiment."""
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


# ─────────────────────────────────────────────────────
# Response Schemas (Pydantic Models)
# ─────────────────────────────────────────────────────

class TradeSignal(BaseModel):
    """Validated trade signal with confidence score."""
    signal: SignalType = Field(..., description="Buy/Sell/Hold signal")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence 0-1")
    reason: str = Field(..., max_length=500, description="Why this signal")
    target_price: Optional[float] = Field(None, description="Target price level")
    stop_loss: Optional[float] = Field(None, description="Stop loss level")
    timeframe: Timeframe = Field(default=Timeframe.H1, description="Chart timeframe")
    
    class Config:
        use_enum_values = False  # Keep enum objects, not strings
    
    @validator('confidence')
    def validate_confidence(cls, v):
        if not (0.0 <= v <= 1.0):
            raise ValueError('Confidence must be between 0 and 1')
        return v


class MarketAnalysis(BaseModel):
    """Validated market analysis response."""
    summary: str = Field(..., max_length=1000, description="Key findings")
    sentiment: SentimentType = Field(..., description="Market sentiment")
    support_levels: List[float] = Field(default_factory=list, description="Support prices")
    resistance_levels: List[float] = Field(default_factory=list, description="Resistance prices")
    key_events: List[str] = Field(default_factory=list, description="Important events")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Analysis confidence")
    
    @validator('support_levels', 'resistance_levels', pre=True)
    def validate_price_levels(cls, v):
        """Ensure price levels are positive floats."""
        if not isinstance(v, list):
            return []
        return [float(x) for x in v if x > 0]


class RiskAssessment(BaseModel):
    """Validated risk assessment response."""
    risk_level: str = Field(..., description="Low/Medium/High")
    daily_loss_limit: float = Field(..., gt=0, description="Max daily loss in USD")
    position_size: float = Field(..., gt=0, description="Recommended position size")
    margin_required: float = Field(..., ge=0, description="Margin requirement")
    max_positions: int = Field(..., ge=1, le=10, description="Max concurrent positions")
    reasoning: str = Field(..., max_length=500, description="Risk assessment rationale")
    
    @validator('risk_level')
    def validate_risk_level(cls, v):
        valid = ['low', 'medium', 'high']
        if v.lower() not in valid:
            raise ValueError(f'Risk level must be one of {valid}')
        return v.lower()


class ResearchFinding(BaseModel):
    """Validated AI research finding."""
    query: str = Field(..., max_length=500, description="Original research query")
    finding: str = Field(..., max_length=2000, description="Research result")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Finding confidence")
    sources: List[str] = Field(default_factory=list, description="Source citations")
    timestamp: str = Field(..., description="ISO 8601 timestamp")


class ConsensusResult(BaseModel):
    """Validated multi-AI consensus result."""
    task: str = Field(..., max_length=500, description="Task performed")
    consensus_signal: Optional[SignalType] = Field(None, description="Consensus signal")
    agreement_ratio: float = Field(..., ge=0.0, le=1.0, description="AI agreement ratio")
    responses: List[Dict[str, Any]] = Field(default_factory=list, description="Individual AI responses")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Overall consensus confidence")


# ─────────────────────────────────────────────────────
# Response Validator
# ─────────────────────────────────────────────────────

class ResponseValidator:
    """
    Validates and parses structured responses from AI systems.
    
    Uses Pydantic models to enforce type safety and data validation
    before trading decisions are made.
    """
    
    def __init__(self):
        self.schemas = {
            'signal': TradeSignal,
            'analysis': MarketAnalysis,
            'risk': RiskAssessment,
            'research': ResearchFinding,
            'consensus': ConsensusResult,
        }
    
    def parse_trading_signal(self, response: str, **kwargs) -> TradeSignal:
        """
        Parse AI response into validated TradeSignal.
        
        Args:
            response: AI response text
            **kwargs: Optional overrides (signal, confidence, reason, etc.)
        
        Returns:
            Validated TradeSignal object
        
        Raises:
            ValueError if response cannot be parsed
        """
        try:
            # Extract signal keywords
            signal_type = self._extract_signal_type(response)
            confidence = self._extract_confidence(response)
            reason = response[:500] if len(response) <= 500 else response[:497] + "..."
            
            # Create validated object
            signal = TradeSignal(
                signal=signal_type,
                confidence=confidence,
                reason=reason,
                **kwargs
            )
            logger.info(f"✓ TradeSignal validated: {signal_type} @ {confidence:.2%}")
            return signal
        except Exception as e:
            logger.error(f"✗ Failed to parse signal: {e}")
            raise ValueError(f"Invalid trading signal: {e}")
    
    def parse_market_analysis(self, response: str, sentiment: str = "neutral") -> MarketAnalysis:
        """Parse AI response into validated MarketAnalysis."""
        try:
            analysis = MarketAnalysis(
                summary=response[:1000],
                sentiment=SentimentType(sentiment.lower()),
                confidence=self._extract_confidence(response),
            )
            logger.info(f"✓ MarketAnalysis validated: {sentiment}")
            return analysis
        except Exception as e:
            logger.error(f"✗ Failed to parse analysis: {e}")
            raise ValueError(f"Invalid market analysis: {e}")
    
    def parse_risk_assessment(self, response: str, **overrides) -> RiskAssessment:
        """Parse AI response into validated RiskAssessment."""
        try:
            extract_num = lambda t, default: self._extract_number(t, default)
            
            risk = RiskAssessment(
                risk_level="medium",  # Default
                daily_loss_limit=extract_num(response, 500.0),
                position_size=extract_num(response, 0.1),
                margin_required=extract_num(response, 50.0),
                max_positions=int(extract_num(response, 5)),
                reasoning=response[:500],
                **overrides
            )
            logger.info(f"✓ RiskAssessment validated")
            return risk
        except Exception as e:
            logger.error(f"✗ Failed to parse risk assessment: {e}")
            raise ValueError(f"Invalid risk assessment: {e}")
    
    def parse_research_finding(self, query: str, finding: str) -> ResearchFinding:
        """Parse AI response into validated ResearchFinding."""
        try:
            from datetime import datetime
            
            result = ResearchFinding(
                query=query,
                finding=finding,
                confidence=self._extract_confidence(finding),
                timestamp=datetime.now().isoformat(),
            )
            logger.info(f"✓ ResearchFinding validated")
            return result
        except Exception as e:
            logger.error(f"✗ Failed to parse research finding: {e}")
            raise ValueError(f"Invalid research finding: {e}")
    
    # ─────────────────────────────────────────────────
    # Helper methods
    # ─────────────────────────────────────────────────
    
    @staticmethod
    def _extract_signal_type(text: str) -> SignalType:
        """Extract signal type from text."""
        text_lower = text.lower()
        
        if 'sell' in text_lower or 'short' in text_lower:
            return SignalType.SELL
        elif 'buy' in text_lower or 'long' in text_lower:
            return SignalType.BUY
        elif 'hold' in text_lower:
            return SignalType.HOLD
        else:
            return SignalType.NEUTRAL
    
    @staticmethod
    def _extract_confidence(text: str) -> float:
        """Extract confidence score (0-1) from text."""
        import re
        
        # Look for percentage
        pct_match = re.search(r'(\d+\.?\d*)\s*%', text)
        if pct_match:
            return min(1.0, float(pct_match.group(1)) / 100.0)
        
        # Look for decimal 0-1
        conf_match = re.search(r'confidence[\s:]*(\d+\.?\d*)', text, re.IGNORECASE)
        if conf_match:
            return min(1.0, float(conf_match.group(1)))
        
        # Default confidence based on content length
        return min(0.9, len(text.split()) / 100.0)
    
    @staticmethod
    def _extract_number(text: str, default: float) -> float:
        """Extract first number from text."""
        import re
        match = re.search(r'\d+\.?\d*', text)
        return float(match.group(0)) if match else default


# ─────────────────────────────────────────────────────
# Singleton factory
# ─────────────────────────────────────────────────────

_validator_instance: Optional[ResponseValidator] = None


def get_response_validator() -> ResponseValidator:
    """Get or create singleton ResponseValidator instance."""
    global _validator_instance
    if _validator_instance is None:
        _validator_instance = ResponseValidator()
        logger.info("[ResponseValidator] Singleton created")
    return _validator_instance
