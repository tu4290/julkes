"""
Key Level Identifier v2.5 - EOTS "Apex Predator"

Identifies critical support/resistance levels, key price points, and significant
options activity zones for enhanced trading decision making.

Author: EOTS Development Team
Version: 2.5.0
Last Updated: 2024
"""

import logging
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
from datetime import datetime, timedelta

# Configure logging
logger = logging.getLogger(__name__)

@dataclass
class KeyLevel:
    """Represents a key price level with associated metadata."""
    price: float
    level_type: str  # 'support', 'resistance', 'pivot', 'max_pain', 'gamma_wall'
    strength: float  # 0.0 to 1.0
    volume: Optional[float] = None
    open_interest: Optional[float] = None
    last_tested: Optional[datetime] = None
    break_count: int = 0
    confidence: float = 0.0

@dataclass
class KeyLevelAnalysis:
    """Complete key level analysis results."""
    symbol: str
    timestamp: datetime
    current_price: float
    key_levels: List[KeyLevel]
    nearest_support: Optional[KeyLevel]
    nearest_resistance: Optional[KeyLevel]
    max_pain_level: Optional[KeyLevel]
    gamma_walls: List[KeyLevel]
    pivot_points: List[KeyLevel]
    level_density_score: float
    breakout_probability: float

class KeyLevelIdentifierV2_5:
    """
    Advanced key level identification system that combines technical analysis
    with options flow data to identify critical price levels.
    """
    
    def __init__(self, config):
        """
        Initialize the Key Level Identifier.
        Accepts either a Pydantic model or a dict for config.
        """
        self.logger = logging.getLogger(__name__)
        # Defensive: convert Pydantic model to dict if needed
        if hasattr(config, 'dict') and callable(getattr(config, 'dict')):
            config_dict = config.dict()
        elif isinstance(config, dict):
            config_dict = config
        else:
            raise TypeError("KeyLevelIdentifierV2_5 expects a Pydantic model or dict for config.")
        self.config = config_dict
        # Configuration parameters
        self.lookback_periods = config_dict.get('lookback_periods', 20)
        self.min_touches = config_dict.get('min_touches', 2)
        self.level_tolerance = config_dict.get('level_tolerance', 0.005)
        self.volume_threshold = config_dict.get('volume_threshold', 1.5)
        self.oi_threshold = config_dict.get('oi_threshold', 1000)
        self.gamma_threshold = config_dict.get('gamma_threshold', 0.1)
        
        # Historical data storage
        self.price_history: Dict[str, pd.DataFrame] = {}
        self.options_data: Dict[str, pd.DataFrame] = {}
        
        self.logger.info("Key Level Identifier v2.5 initialized")
    
    def identify_key_levels(self, 
                          symbol: str,
                          price_data: pd.DataFrame,
                          options_data: Optional[pd.DataFrame] = None) -> KeyLevelAnalysis:
        """
        Identify key levels for a given symbol.
        
        Args:
            symbol: Trading symbol
            price_data: Historical price data with OHLCV
            options_data: Options chain data with strikes, OI, volume
            
        Returns:
            KeyLevelAnalysis object containing all identified levels
        """
        try:
            self.logger.info(f"[KeyLevelIdentifier] Starting key level identification for {symbol}")
            
            # Debug input data
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"[KeyLevelIdentifier] Price data shape: {price_data.shape}")
                logger.debug(f"[KeyLevelIdentifier] Price data columns: {price_data.columns.tolist()}")
                logger.debug(f"[KeyLevelIdentifier] Price data index type: {type(price_data.index)}")
                if not price_data.empty:
                    logger.debug(f"[KeyLevelIdentifier] Price data sample:\n{price_data.tail(3)}")
                
                if options_data is not None:
                    logger.debug(f"[KeyLevelIdentifier] Options data shape: {options_data.shape}")
                    logger.debug(f"[KeyLevelIdentifier] Options data columns: {options_data.columns.tolist()}")
                    if not options_data.empty:
                        logger.debug(f"[KeyLevelIdentifier] Options data sample:\n{options_data.head(3)}")
                else:
                    logger.debug(f"[KeyLevelIdentifier] No options data provided")
            
            # Handle different possible column names for price data
            if 'close' in price_data.columns:
                current_price = float(price_data['close'].iloc[-1])
                self.logger.info(f"[KeyLevelIdentifier] Current price from 'close': {current_price}")
            elif 'price' in price_data.columns:
                current_price = float(price_data['price'].iloc[-1])
                self.logger.info(f"[KeyLevelIdentifier] Current price from 'price': {current_price}")
            elif len(price_data.columns) > 0:
                # Use the last column as price if no standard column found
                current_price = float(price_data.iloc[-1, -1])
                self.logger.warning(f"[KeyLevelIdentifier] Current price from last column: {current_price}")
            else:
                self.logger.error(f"No price data found in DataFrame for {symbol}")
                raise ValueError(f"No price data available for {symbol}")
            timestamp = datetime.now()
            
            # Store data for historical analysis
            self.price_history[symbol] = price_data
            if options_data is not None:
                self.options_data[symbol] = options_data
            
            # Identify different types of levels
            self.logger.info(f"[KeyLevelIdentifier] Identifying technical levels...")
            technical_levels = self._identify_technical_levels(price_data)
            self.logger.info(f"[KeyLevelIdentifier] Found {len(technical_levels)} technical levels")
            
            self.logger.info(f"[KeyLevelIdentifier] Calculating pivot points...")
            pivot_levels = self._calculate_pivot_points(price_data)
            self.logger.info(f"[KeyLevelIdentifier] Found {len(pivot_levels)} pivot levels")
            
            key_levels = technical_levels + pivot_levels
            
            # Add options-based levels if data available
            if options_data is not None:
                self.logger.info(f"[KeyLevelIdentifier] Calculating max pain...")
                max_pain = self._calculate_max_pain(options_data, current_price)
                if max_pain:
                    self.logger.info(f"[KeyLevelIdentifier] Max pain level: {max_pain.price}")
                    key_levels.append(max_pain)
                else:
                    self.logger.warning(f"[KeyLevelIdentifier] No max pain level calculated")
                
                self.logger.info(f"[KeyLevelIdentifier] Identifying gamma walls...")
                gamma_walls = self._identify_gamma_walls(options_data, current_price)
                self.logger.info(f"[KeyLevelIdentifier] Found {len(gamma_walls)} gamma walls")
                key_levels.extend(gamma_walls)
            else:
                self.logger.warning(f"[KeyLevelIdentifier] No options data available for options-based levels")
            
            # Sort levels by price
            key_levels.sort(key=lambda x: x.price)
            self.logger.info(f"[KeyLevelIdentifier] Total key levels found: {len(key_levels)}")
            
            # Debug all levels found
            if logger.isEnabledFor(logging.DEBUG):
                for i, level in enumerate(key_levels):
                    logger.debug(f"[KeyLevelIdentifier] Level {i}: price={level.price}, type={level.level_type}, strength={level.strength}, confidence={level.confidence}")
            
            # Find nearest support and resistance
            nearest_support, nearest_resistance = self._find_nearest_levels(
                key_levels, current_price
            )
            
            if nearest_support:
                self.logger.info(f"[KeyLevelIdentifier] Nearest support: {nearest_support.price}")
            if nearest_resistance:
                self.logger.info(f"[KeyLevelIdentifier] Nearest resistance: {nearest_resistance.price}")
            
            # Calculate additional metrics
            level_density = self._calculate_level_density(key_levels, current_price)
            breakout_prob = self._calculate_breakout_probability(
                price_data, key_levels, current_price
            )
            
            self.logger.info(f"[KeyLevelIdentifier] Level density: {level_density}, Breakout probability: {breakout_prob}")
            
            # Filter and categorize levels
            gamma_walls = [level for level in key_levels if level.level_type == 'gamma_wall']
            pivot_points = [level for level in key_levels if level.level_type == 'pivot']
            max_pain_level = next((level for level in key_levels if level.level_type == 'max_pain'), None)
            
            self.logger.info(f"[KeyLevelIdentifier] Categorized levels - Gamma walls: {len(gamma_walls)}, Pivots: {len(pivot_points)}, Max pain: {'Yes' if max_pain_level else 'No'}")
            
            analysis = KeyLevelAnalysis(
                symbol=symbol,
                timestamp=timestamp,
                current_price=current_price,
                key_levels=key_levels,
                nearest_support=nearest_support,
                nearest_resistance=nearest_resistance,
                max_pain_level=max_pain_level,
                gamma_walls=gamma_walls,
                pivot_points=pivot_points,
                level_density_score=level_density,
                breakout_probability=breakout_prob
            )
            
            self.logger.info(f"[KeyLevelIdentifier] Key level analysis completed for {symbol} at {timestamp}")
            return analysis
            
        except Exception as e:
            self.logger.error(f"Error identifying key levels for {symbol}: {str(e)}", exc_info=True)
            raise
    
    def _identify_technical_levels(self, price_data: pd.DataFrame) -> List[KeyLevel]:
        """Identify technical support and resistance levels."""
        levels = []
        
        # Check if required OHLC columns exist
        if price_data.empty:
            self.logger.warning("Price data is empty, cannot identify technical levels")
            return levels
            
        required_columns = ['high', 'low']
        missing_columns = [col for col in required_columns if col not in price_data.columns]
        
        if missing_columns:
            self.logger.warning(f"Missing required columns for technical analysis: {missing_columns}")
            self.logger.debug(f"Available columns: {list(price_data.columns)}")
            return levels
        
        # Find swing highs and lows
        highs = self._find_swing_points(price_data['high'], 'high')
        lows = self._find_swing_points(price_data['low'], 'low')
        
        # Process swing highs as resistance
        for idx, price in highs:
            volume = float(price_data['volume'].iloc[idx]) if 'volume' in price_data.columns and pd.notnull(price_data['volume'].iloc[idx]) else 0.0
            strength = float(self._calculate_level_strength(price_data, price, 'resistance') or 0.0)
            last_tested = price_data.index[idx]
            if not isinstance(last_tested, datetime):
                try:
                    last_tested = pd.to_datetime(last_tested)
                except Exception:
                    last_tested = None
            levels.append(KeyLevel(
                price=float(price),
                level_type='resistance',
                strength=strength,
                volume=volume,
                last_tested=last_tested,
                confidence=min(strength * 1.2, 1.0)
            ))
        
        # Process swing lows as support
        for idx, price in lows:
            volume = float(price_data['volume'].iloc[idx]) if 'volume' in price_data.columns and pd.notnull(price_data['volume'].iloc[idx]) else 0.0
            strength = float(self._calculate_level_strength(price_data, price, 'support') or 0.0)
            last_tested = price_data.index[idx]
            if not isinstance(last_tested, datetime):
                try:
                    last_tested = pd.to_datetime(last_tested)
                except Exception:
                    last_tested = None
            levels.append(KeyLevel(
                price=float(price),
                level_type='support',
                strength=strength,
                volume=volume,
                last_tested=last_tested,
                confidence=min(strength * 1.2, 1.0)
            ))
        
        return levels
    
    def _find_swing_points(self, series: pd.Series, point_type: str) -> List[Tuple[int, float]]:
        """Find swing highs or lows in price series."""
        points = []
        window = 5  # Look for peaks/troughs in 5-period windows
        
        for i in range(window, len(series) - window):
            if point_type == 'high':
                if all(series.iloc[i] >= series.iloc[i-j] for j in range(1, window+1)) and \
                   all(series.iloc[i] >= series.iloc[i+j] for j in range(1, window+1)):
                    points.append((i, series.iloc[i]))
            else:  # low
                if all(series.iloc[i] <= series.iloc[i-j] for j in range(1, window+1)) and \
                   all(series.iloc[i] <= series.iloc[i+j] for j in range(1, window+1)):
                    points.append((i, series.iloc[i]))
        
        return points
    
    def _calculate_level_strength(self, price_data: pd.DataFrame, level_price: float, level_type: str) -> float:
        """Calculate the strength of a support/resistance level."""
        touches = 0
        total_volume = 0
        
        tolerance = level_price * self.level_tolerance
        
        # Check if required columns exist
        required_col = 'low' if level_type == 'support' else 'high'
        if required_col not in price_data.columns:
            self.logger.warning(f"Missing column '{required_col}' for level strength calculation")
            return 0.5  # Default strength
        
        for i, row in price_data.iterrows():
            if level_type == 'support':
                if abs(row['low'] - level_price) <= tolerance:
                    touches += 1
                    if 'volume' in price_data.columns:
                        total_volume += row['volume']
            else:  # resistance
                if abs(row['high'] - level_price) <= tolerance:
                    touches += 1
                    if 'volume' in price_data.columns:
                        total_volume += row['volume']
        
        # Normalize strength (0.0 to 1.0)
        strength = min(touches / 10.0, 1.0)  # Max strength at 10 touches
        
        # Boost strength if high volume
        if 'volume' in price_data.columns and total_volume > 0:
            avg_volume = price_data['volume'].mean()
            if total_volume > avg_volume * self.volume_threshold:
                strength = min(strength * 1.3, 1.0)
        
        return strength
    
    def _calculate_pivot_points(self, price_data: pd.DataFrame) -> List[KeyLevel]:
        """Calculate traditional pivot points."""
        if len(price_data) < 1:
            return []
        
        # Check if required columns exist
        required_columns = ['high', 'low', 'close']
        missing_columns = [col for col in required_columns if col not in price_data.columns]
        
        if missing_columns:
            self.logger.warning(f"Missing required columns for pivot points: {missing_columns}")
            return []
        
        # Use previous day's data for pivot calculation
        prev_high = price_data['high'].iloc[-2] if len(price_data) > 1 else price_data['high'].iloc[-1]
        prev_low = price_data['low'].iloc[-2] if len(price_data) > 1 else price_data['low'].iloc[-1]
        prev_close = price_data['close'].iloc[-2] if len(price_data) > 1 else price_data['close'].iloc[-1]
        
        # Calculate pivot point
        pivot = (prev_high + prev_low + prev_close) / 3
        
        # Calculate support and resistance levels
        r1 = 2 * pivot - prev_low
        s1 = 2 * pivot - prev_high
        r2 = pivot + (prev_high - prev_low)
        s2 = pivot - (prev_high - prev_low)
        
        levels = [
            KeyLevel(price=pivot, level_type='pivot', strength=0.8, confidence=0.7),
            KeyLevel(price=r1, level_type='resistance', strength=0.6, confidence=0.6),
            KeyLevel(price=s1, level_type='support', strength=0.6, confidence=0.6),
            KeyLevel(price=r2, level_type='resistance', strength=0.4, confidence=0.5),
            KeyLevel(price=s2, level_type='support', strength=0.4, confidence=0.5)
        ]
        
        return levels
    
    def _calculate_max_pain(self, options_data: pd.DataFrame, current_price: float) -> Optional[KeyLevel]:
        """Calculate max pain level from options data."""
        if options_data.empty:
            return None
        
        try:
            # Group by strike and sum open interest
            strikes = options_data.groupby('strike').agg({
                'open_interest': 'sum'
            }).reset_index()
            
            max_pain_strike = None
            min_pain = float('inf')
            
            for _, row in strikes.iterrows():
                strike = row['strike']
                total_pain = 0
                
                # Calculate pain for calls and puts at this strike
                for _, opt_row in options_data.iterrows():
                    oi = opt_row['open_interest']
                    opt_strike = opt_row['strike']
                    
                    if opt_row['option_type'].lower() == 'call':
                        if strike > opt_strike:
                            total_pain += oi * (strike - opt_strike)
                    else:  # put
                        if strike < opt_strike:
                            total_pain += oi * (opt_strike - strike)
                
                if total_pain < min_pain:
                    min_pain = total_pain
                    max_pain_strike = strike
            
            if max_pain_strike:
                return KeyLevel(
                    price=max_pain_strike,
                    level_type='max_pain',
                    strength=0.7,
                    open_interest=strikes[strikes['strike'] == max_pain_strike]['open_interest'].iloc[0],
                    confidence=0.6
                )
        
        except Exception as e:
            self.logger.warning(f"Error calculating max pain: {str(e)}")
        
        return None
    
    def _identify_gamma_walls(self, options_data: pd.DataFrame, current_price: float) -> List[KeyLevel]:
        """Identify gamma walls from options data."""
        gamma_walls = []
        
        if options_data.empty or 'gamma' not in options_data.columns:
            return gamma_walls
        
        try:
            # Group by strike and sum gamma * open_interest
            gamma_exposure = options_data.groupby('strike').apply(
                lambda x: (x['gamma'] * x['open_interest']).sum()
            ).reset_index()
            gamma_exposure.columns = ['strike', 'total_gamma_exposure']
            
            # Find strikes with significant gamma exposure
            threshold = gamma_exposure['total_gamma_exposure'].quantile(0.8)
            
            for _, row in gamma_exposure.iterrows():
                if abs(row['total_gamma_exposure']) > threshold:
                    strength = min(abs(row['total_gamma_exposure']) / threshold, 1.0)
                    
                    gamma_walls.append(KeyLevel(
                        price=row['strike'],
                        level_type='gamma_wall',
                        strength=strength,
                        open_interest=row['total_gamma_exposure'],
                        confidence=strength * 0.8
                    ))
        
        except Exception as e:
            self.logger.warning(f"Error identifying gamma walls: {str(e)}")
        
        return gamma_walls
    
    def _find_nearest_levels(self, levels: List[KeyLevel], current_price: float) -> Tuple[Optional[KeyLevel], Optional[KeyLevel]]:
        """Find nearest support and resistance levels."""
        support_levels = [l for l in levels if l.price < current_price and l.level_type in ['support', 'pivot']]
        resistance_levels = [l for l in levels if l.price > current_price and l.level_type in ['resistance', 'pivot']]
        
        nearest_support = max(support_levels, key=lambda x: x.price) if support_levels else None
        nearest_resistance = min(resistance_levels, key=lambda x: x.price) if resistance_levels else None
        
        return nearest_support, nearest_resistance
    
    def _calculate_level_density(self, levels: List[KeyLevel], current_price: float) -> float:
        """Calculate density of levels around current price."""
        if not levels:
            return 0.0
        
        # Count levels within 5% of current price
        tolerance = current_price * 0.05
        nearby_levels = [l for l in levels if abs(l.price - current_price) <= tolerance]
        
        return len(nearby_levels) / 10.0  # Normalize to 0-1 scale
    
    def _calculate_breakout_probability(self, price_data: pd.DataFrame, 
                                      levels: List[KeyLevel], current_price: float) -> float:
        """Calculate probability of breakout based on price action and levels."""
        if len(price_data) < 10:
            return 0.5
        
        # Recent volatility
        recent_returns = price_data['close'].pct_change().tail(10)
        volatility = recent_returns.std()
        
        # Distance to nearest levels
        nearest_support, nearest_resistance = self._find_nearest_levels(levels, current_price)
        
        support_distance = abs(current_price - nearest_support.price) / current_price if nearest_support else 0.1
        resistance_distance = abs(nearest_resistance.price - current_price) / current_price if nearest_resistance else 0.1
        
        # Higher volatility and closer to levels = higher breakout probability
        breakout_prob = min(volatility * 10 + (1 / min(support_distance, resistance_distance)), 1.0)
        
        return breakout_prob
    
    def get_level_summary(self, analysis: KeyLevelAnalysis) -> Dict[str, Any]:
        """Get a summary of key level analysis."""
        return {
            'symbol': analysis.symbol,
            'current_price': analysis.current_price,
            'total_levels': len(analysis.key_levels),
            'nearest_support': analysis.nearest_support.price if analysis.nearest_support else None,
            'nearest_resistance': analysis.nearest_resistance.price if analysis.nearest_resistance else None,
            'max_pain': analysis.max_pain_level.price if analysis.max_pain_level else None,
            'gamma_walls_count': len(analysis.gamma_walls),
            'level_density': analysis.level_density_score,
            'breakout_probability': analysis.breakout_probability,
            'timestamp': analysis.timestamp
        }