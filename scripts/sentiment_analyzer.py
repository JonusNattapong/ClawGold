"""
Sentiment Analysis Module
=========================
Analyzes sentiment from news and AI research results.
"""

import re
import json
from typing import List, Dict, Tuple, Optional
from collections import Counter
from dataclasses import dataclass

from logger import get_logger

try:
    from agent_executor import AgentExecutor, AgentTool
    from config_loader import load_config
    AGENT_AVAILABLE = True
except ImportError:
    AGENT_AVAILABLE = False

logger = get_logger(__name__)


@dataclass
class SentimentScore:
    """Sentiment analysis result."""
    score: float  # -1 to 1
    confidence: float  # 0 to 1
    label: str  # bullish, bearish, neutral
    keywords: List[str]


class SentimentAnalyzer:
    """
    Sentiment analyzer for trading content.
    
    Uses keyword-based analysis and pattern matching.
    """
    
    # Keywords for sentiment classification
    BULLISH_KEYWORDS = [
        'bullish', 'buy', 'long', 'up', 'rise', 'rising', 'rally', 'surge',
        'surging', 'gain', 'gains', 'higher', 'high', 'strong', 'strength',
        'support', 'breakout', 'moon', 'rocket', 'pump', 'accumulate',
        'undervalued', 'opportunity', 'growth', 'rally', 'soar', 'jump',
        'positive', 'optimistic', 'confident', 'recovery', 'recovering',
        'demand', 'buying', 'accumulation', 'support', 'bounce', 'rebound'
    ]
    
    BEARISH_KEYWORDS = [
        'bearish', 'sell', 'short', 'down', 'fall', 'falling', 'drop', 'dropping',
        'crash', 'dump', 'decline', 'declining', 'lower', 'low', 'weak', 'weakness',
        'resistance', 'breakdown', 'dumping', 'distribution', 'overvalued',
        'correction', 'correcting', 'sell-off', 'panic', 'fear', 'concern',
        'negative', 'pessimistic', 'worry', 'worried', 'recession', 'inflation',
        'supply', 'selling', 'pressure', 'rejection', 'rejected'
    ]
    
    # Weight modifiers
    STRONG_INDICATORS = ['very', 'extremely', 'highly', 'strongly', 'massive']
    WEAK_INDICATORS = ['slightly', 'somewhat', 'mildly', 'moderately']
    
    def __init__(self):
        self.bullish_pattern = re.compile(
            r'\b(' + '|'.join(self.BULLISH_KEYWORDS) + r')\b',
            re.IGNORECASE
        )
        self.bearish_pattern = re.compile(
            r'\b(' + '|'.join(self.BEARISH_KEYWORDS) + r')\b',
            re.IGNORECASE
        )
        
        # Initialize AI Agent support
        self.agent_executor = None
        if AGENT_AVAILABLE:
            try:
                config = load_config()
                self.agent_executor = AgentExecutor(config)
            except Exception as e:
                logger.warning(f"Could not initialize AgentExecutor in SentimentAnalyzer: {e}")
    
    def analyze_text(self, text: str, use_ai: bool = False) -> SentimentScore:
        """
        Analyze sentiment of text.
        
        Args:
            text: Text to analyze
            use_ai: Whether to use AI agent for deeper analysis
        
        Returns:
            SentimentScore object
        """
        if not text:
            return SentimentScore(0, 0, 'neutral', [])
        
        # If AI is requested and available, use it for deeper reasoning
        if use_ai and self.agent_executor:
            return self._analyze_text_with_ai(text)
            
        text_lower = text.lower()
        
        # Count keyword matches
        bullish_matches = self.bullish_pattern.findall(text_lower)
        bearish_matches = self.bearish_pattern.findall(text_lower)
        
        # Calculate base score
        bullish_count = len(bullish_matches)
        bearish_count = len(bearish_matches)
        total = bullish_count + bearish_count
        
        if total == 0:
            return SentimentScore(0, 0.5, 'neutral', [])
        
        # Score from -1 to 1
        score = (bullish_count - bearish_count) / total
        
        # Determine label
        if score > 0.2:
            label = 'bullish'
        elif score < -0.2:
            label = 'bearish'
        else:
            label = 'neutral'
        
        # Calculate confidence based on keyword density and strength
        word_count = len(text.split())
        keyword_density = total / max(word_count, 1)
        confidence = min(0.5 + keyword_density * 10, 1.0)
        
        # Collect unique keywords
        keywords = list(set(bullish_matches + bearish_matches))
        
        return SentimentScore(score, confidence, label, keywords)

    def _analyze_text_with_ai(self, text: str) -> SentimentScore:
        """Analyze sentiment using AI Agent for better context understanding."""
        prompt = f"""
        Analyze the market sentiment of the following news/text for XAUUSD (Gold) trading.
        Respond ONLY with a JSON object containing:
        - "score": (float between -1.0 and 1.0, where -1 is very bearish, 0 is neutral, 1 is very bullish)
        - "confidence": (float between 0.0 and 1.0)
        - "label": ("bullish", "bearish", or "neutral")
        - "keywords": (list of important keywords found)
        - "reasoning": (short explanation)

        Text to analyze:
        ---
        {text}
        ---
        """
        
        try:
            # We use gemini or kilocode for high-quality reasoning
            result = self.agent_executor.run_best(prompt, task_name="ai_sentiment_analysis")
            
            if result.get('success'):
                # Extract JSON from response
                content = result.get('output', '')
                try:
                    # Look for JSON block if formatted with markdown
                    if "```json" in content:
                        content = content.split("```json")[1].split("```")[0].strip()
                    elif "```" in content:
                        content = content.split("```")[1].split("```")[0].strip()
                    
                    data = json.loads(content)
                    return SentimentScore(
                        score=float(data.get('score', 0)),
                        confidence=float(data.get('confidence', 0.8)),
                        label=data.get('label', 'neutral').lower(),
                        keywords=data.get('keywords', [])
                    )
                except (json.JSONDecodeError, ValueError) as e:
                    logger.warning(f"Failed to parse AI sentiment JSON: {e}")
        except Exception as e:
            logger.error(f"AI sentiment analysis failed: {e}")
            
        # Fallback to keyword-based if AI fails
        return self.analyze_text(text, use_ai=False)
    
    def analyze_multiple(self, texts: List[str]) -> Dict:
        """
        Analyze sentiment of multiple texts.
        
        Returns:
            Aggregated sentiment analysis
        """
        if not texts:
            return {
                'average_score': 0,
                'average_confidence': 0,
                'dominant_sentiment': 'neutral',
                'sentiment_distribution': {'bullish': 0, 'bearish': 0, 'neutral': 0},
                'all_keywords': []
            }
        
        scores = []
        sentiments = []
        all_keywords = []
        
        for text in texts:
            result = self.analyze_text(text)
            scores.append(result.score)
            sentiments.append(result.label)
            all_keywords.extend(result.keywords)
        
        # Calculate averages
        avg_score = sum(scores) / len(scores)
        avg_confidence = sum(s.confidence for s in [
            self.analyze_text(t) for t in texts
        ]) / len(texts)
        
        # Count sentiments
        sentiment_counts = Counter(sentiments)
        dominant = sentiment_counts.most_common(1)[0][0]
        
        return {
            'average_score': avg_score,
            'average_confidence': avg_confidence,
            'dominant_sentiment': dominant,
            'sentiment_distribution': dict(sentiment_counts),
            'all_keywords': list(set(all_keywords)),
            'keyword_frequency': dict(Counter(all_keywords).most_common(10))
        }
    
    def compare_sentiments(self, text1: str, text2: str) -> Dict:
        """Compare sentiment between two texts."""
        s1 = self.analyze_text(text1)
        s2 = self.analyze_text(text2)
        
        return {
            'text1': {'score': s1.score, 'label': s1.label},
            'text2': {'score': s2.score, 'label': s2.label},
            'difference': s2.score - s1.score,
            'agreement': s1.label == s2.label,
            'shift': self._describe_shift(s1.score, s2.score)
        }
    
    def _describe_shift(self, old: float, new: float) -> str:
        """Describe sentiment shift."""
        diff = new - old
        if abs(diff) < 0.1:
            return 'stable'
        elif diff > 0.5:
            return 'strongly more bullish'
        elif diff > 0.2:
            return 'more bullish'
        elif diff < -0.5:
            return 'strongly more bearish'
        elif diff < -0.2:
            return 'more bearish'
        else:
            return 'slight shift'
    
    def calculate_impact_score(self, text: str, source_weight: float = 1.0) -> float:
        """
        Calculate potential market impact score.
        
        Args:
            text: News text
            source_weight: Weight based on source credibility
        
        Returns:
            Impact score 0-1
        """
        sentiment = self.analyze_text(text)
        
        # Factors affecting impact
        factors = {
            'sentiment_strength': abs(sentiment.score),
            'confidence': sentiment.confidence,
            'source_weight': source_weight,
            'urgency': self._detect_urgency(text),
            'specificity': self._detect_specificity(text)
        }
        
        # Weighted combination
        impact = (
            factors['sentiment_strength'] * 0.3 +
            factors['confidence'] * 0.2 +
            factors['source_weight'] * 0.2 +
            factors['urgency'] * 0.15 +
            factors['specificity'] * 0.15
        )
        
        return min(impact, 1.0)
    
    def _detect_urgency(self, text: str) -> float:
        """Detect urgency level in text."""
        urgency_words = [
            'breaking', 'urgent', 'alert', 'immediate', 'now',
            'just', 'latest', 'update', 'developing'
        ]
        
        text_lower = text.lower()
        count = sum(1 for word in urgency_words if word in text_lower)
        return min(count / 3, 1.0)
    
    def _detect_specificity(self, text: str) -> float:
        """Detect how specific/detailed the text is."""
        # Check for numbers, percentages, specific figures
        numbers = len(re.findall(r'\d+\.?\d*', text))
        percentages = len(re.findall(r'\d+\.?\d*%', text))
        
        # Check for named entities (simple heuristic)
        capitalized = len(re.findall(r'\b[A-Z][a-z]+\b', text))
        
        score = min((numbers * 0.1 + percentages * 0.2 + capitalized * 0.05), 1.0)
        return score
