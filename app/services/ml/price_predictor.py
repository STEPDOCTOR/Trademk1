"""Machine learning price prediction service."""
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
import joblib
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
import asyncio

from app.db.questdb import get_questdb_pool
from app.monitoring.logger import get_logger

logger = get_logger(__name__)


@dataclass
class PricePrediction:
    """Price prediction result."""
    symbol: str
    current_price: float
    predicted_price: float
    predicted_change: float
    predicted_change_pct: float
    confidence: float
    time_horizon: int  # minutes
    features_importance: Dict[str, float]
    prediction_time: datetime
    model_type: str


@dataclass
class MLSignal:
    """ML-based trading signal."""
    symbol: str
    action: str  # "buy", "sell", "hold"
    confidence: float
    predicted_return: float
    time_horizon: int
    risk_score: float
    reason: str


class PricePredictor:
    """Machine learning price prediction service."""
    
    def __init__(self):
        self.models: Dict[str, Any] = {}
        self.scalers: Dict[str, StandardScaler] = {}
        self.feature_columns = [
            'returns_1m', 'returns_5m', 'returns_15m', 'returns_30m', 'returns_1h',
            'volume_ratio_5m', 'volume_ratio_15m', 'volume_ratio_1h',
            'price_sma_ratio_5', 'price_sma_ratio_15', 'price_sma_ratio_50',
            'volatility_5m', 'volatility_15m', 'volatility_1h',
            'rsi_14', 'macd_signal', 'bb_position',
            'hour_of_day', 'day_of_week'
        ]
        self.model_update_interval = 3600  # Update models every hour
        self.min_training_samples = 1000
        self.prediction_horizons = [5, 15, 30, 60]  # minutes
        
    async def train_models(self, symbols: List[str]):
        """Train ML models for given symbols."""
        for symbol in symbols:
            try:
                # Get historical data
                df = await self._get_training_data(symbol)
                
                if df is None or len(df) < self.min_training_samples:
                    logger.warning(f"Insufficient data for {symbol}: {len(df) if df is not None else 0} samples")
                    continue
                    
                # Create features
                features_df = self._create_features(df)
                
                if features_df is None or len(features_df) < 100:
                    continue
                    
                # Train models for different time horizons
                self.models[symbol] = {}
                self.scalers[symbol] = {}
                
                for horizon in self.prediction_horizons:
                    model, scaler = self._train_model(features_df, horizon)
                    if model:
                        self.models[symbol][horizon] = model
                        self.scalers[symbol][horizon] = scaler
                        
                logger.info(f"Trained models for {symbol}")
                
            except Exception as e:
                logger.error(f"Error training models for {symbol}: {e}")
                
    async def _get_training_data(self, symbol: str, days: int = 30) -> Optional[pd.DataFrame]:
        """Get historical data for training."""
        try:
            query = f"""
            SELECT 
                timestamp,
                price,
                volume
            FROM market_ticks
            WHERE symbol = '{symbol}'
            AND timestamp > dateadd('d', -{days}, now())
            ORDER BY timestamp ASC
            """
            
            async with get_questdb_pool() as conn:
                result = await conn.fetch(query)
                
            if not result:
                return None
                
            # Convert to DataFrame
            df = pd.DataFrame(result)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df.set_index('timestamp', inplace=True)
            
            # Resample to 1-minute bars
            ohlc = df['price'].resample('1min').ohlc()
            volume = df['volume'].resample('1min').sum()
            
            df_resampled = pd.concat([ohlc, volume], axis=1)
            df_resampled.dropna(inplace=True)
            
            return df_resampled
            
        except Exception as e:
            logger.error(f"Error getting training data for {symbol}: {e}")
            return None
            
    def _create_features(self, df: pd.DataFrame) -> Optional[pd.DataFrame]:
        """Create features for ML model."""
        try:
            features_df = pd.DataFrame(index=df.index)
            
            # Price returns
            for period in [1, 5, 15, 30, 60]:
                features_df[f'returns_{period}m'] = df['close'].pct_change(period)
                
            # Volume ratios
            for period in [5, 15, 60]:
                features_df[f'volume_ratio_{period}m'] = df['volume'] / df['volume'].rolling(period).mean()
                
            # Price to SMA ratios
            for period in [5, 15, 50]:
                sma = df['close'].rolling(period).mean()
                features_df[f'price_sma_ratio_{period}'] = df['close'] / sma
                
            # Volatility (rolling std of returns)
            returns = df['close'].pct_change()
            for period in [5, 15, 60]:
                features_df[f'volatility_{period}m'] = returns.rolling(period).std()
                
            # RSI
            features_df['rsi_14'] = self._calculate_rsi(df['close'], 14)
            
            # MACD
            exp1 = df['close'].ewm(span=12, adjust=False).mean()
            exp2 = df['close'].ewm(span=26, adjust=False).mean()
            macd = exp1 - exp2
            signal = macd.ewm(span=9, adjust=False).mean()
            features_df['macd_signal'] = (macd - signal) / df['close']
            
            # Bollinger Bands position
            sma20 = df['close'].rolling(20).mean()
            std20 = df['close'].rolling(20).std()
            upper_band = sma20 + (std20 * 2)
            lower_band = sma20 - (std20 * 2)
            features_df['bb_position'] = (df['close'] - lower_band) / (upper_band - lower_band)
            
            # Time features
            features_df['hour_of_day'] = df.index.hour
            features_df['day_of_week'] = df.index.dayofweek
            
            # Drop NaN values
            features_df.dropna(inplace=True)
            
            return features_df
            
        except Exception as e:
            logger.error(f"Error creating features: {e}")
            return None
            
    def _calculate_rsi(self, prices: pd.Series, period: int = 14) -> pd.Series:
        """Calculate RSI indicator."""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
        
    def _train_model(
        self,
        features_df: pd.DataFrame,
        horizon: int
    ) -> Tuple[Optional[Any], Optional[StandardScaler]]:
        """Train a model for specific time horizon."""
        try:
            # Create target variable (future returns)
            target = features_df['returns_1m'].shift(-horizon).dropna()
            
            # Align features with target
            X = features_df[:-horizon][self.feature_columns]
            y = target
            
            # Ensure alignment
            X = X.loc[y.index]
            
            if len(X) < 100:
                return None, None
                
            # Split data
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=0.2, shuffle=False
            )
            
            # Scale features
            scaler = StandardScaler()
            X_train_scaled = scaler.fit_transform(X_train)
            X_test_scaled = scaler.transform(X_test)
            
            # Train Random Forest model
            model = RandomForestRegressor(
                n_estimators=100,
                max_depth=10,
                min_samples_split=20,
                min_samples_leaf=10,
                random_state=42,
                n_jobs=-1
            )
            
            model.fit(X_train_scaled, y_train)
            
            # Evaluate
            train_score = model.score(X_train_scaled, y_train)
            test_score = model.score(X_test_scaled, y_test)
            
            logger.info(
                f"Model trained for {horizon}min horizon: "
                f"train_score={train_score:.3f}, test_score={test_score:.3f}"
            )
            
            return model, scaler
            
        except Exception as e:
            logger.error(f"Error training model: {e}")
            return None, None
            
    async def predict_price(
        self,
        symbol: str,
        time_horizon: int = 15
    ) -> Optional[PricePrediction]:
        """Predict future price for a symbol."""
        try:
            # Check if model exists
            if symbol not in self.models or time_horizon not in self.models[symbol]:
                logger.warning(f"No model found for {symbol} with {time_horizon}min horizon")
                return None
                
            # Get recent data
            df = await self._get_training_data(symbol, days=1)
            
            if df is None or len(df) < 100:
                return None
                
            # Create features
            features_df = self._create_features(df)
            
            if features_df is None or len(features_df) == 0:
                return None
                
            # Get latest features
            latest_features = features_df[self.feature_columns].iloc[-1:].values
            
            # Scale features
            scaler = self.scalers[symbol][time_horizon]
            features_scaled = scaler.transform(latest_features)
            
            # Make prediction
            model = self.models[symbol][time_horizon]
            predicted_return = model.predict(features_scaled)[0]
            
            # Get current price
            current_price = df['close'].iloc[-1]
            predicted_price = current_price * (1 + predicted_return)
            
            # Calculate feature importance
            feature_importance = dict(zip(
                self.feature_columns,
                model.feature_importances_
            ))
            
            # Calculate confidence (based on model score and prediction magnitude)
            confidence = min(0.95, model.score(features_scaled, [predicted_return]) * 0.8 + 0.2)
            
            return PricePrediction(
                symbol=symbol,
                current_price=current_price,
                predicted_price=predicted_price,
                predicted_change=predicted_price - current_price,
                predicted_change_pct=predicted_return,
                confidence=confidence,
                time_horizon=time_horizon,
                features_importance=feature_importance,
                prediction_time=datetime.utcnow(),
                model_type="RandomForest"
            )
            
        except Exception as e:
            logger.error(f"Error predicting price for {symbol}: {e}")
            return None
            
    async def generate_signals(
        self,
        symbols: List[str],
        min_confidence: float = 0.7,
        min_return: float = 0.002  # 0.2%
    ) -> List[MLSignal]:
        """Generate trading signals based on ML predictions."""
        signals = []
        
        for symbol in symbols:
            try:
                # Get predictions for different horizons
                predictions = []
                for horizon in self.prediction_horizons:
                    pred = await self.predict_price(symbol, horizon)
                    if pred:
                        predictions.append(pred)
                        
                if not predictions:
                    continue
                    
                # Aggregate predictions
                avg_return = np.mean([p.predicted_change_pct for p in predictions])
                avg_confidence = np.mean([p.confidence for p in predictions])
                
                # Calculate risk score (based on prediction variance)
                return_variance = np.var([p.predicted_change_pct for p in predictions])
                risk_score = min(1.0, return_variance * 100)
                
                # Generate signal
                if avg_confidence >= min_confidence:
                    if avg_return >= min_return:
                        signal = MLSignal(
                            symbol=symbol,
                            action="buy",
                            confidence=avg_confidence,
                            predicted_return=avg_return,
                            time_horizon=int(np.mean(self.prediction_horizons)),
                            risk_score=risk_score,
                            reason=f"ML prediction: {avg_return:.2%} return expected"
                        )
                        signals.append(signal)
                        
                    elif avg_return <= -min_return:
                        signal = MLSignal(
                            symbol=symbol,
                            action="sell",
                            confidence=avg_confidence,
                            predicted_return=avg_return,
                            time_horizon=int(np.mean(self.prediction_horizons)),
                            risk_score=risk_score,
                            reason=f"ML prediction: {avg_return:.2%} decline expected"
                        )
                        signals.append(signal)
                        
            except Exception as e:
                logger.error(f"Error generating signal for {symbol}: {e}")
                
        # Sort by confidence * abs(return)
        signals.sort(key=lambda x: x.confidence * abs(x.predicted_return), reverse=True)
        
        return signals
        
    async def update_models_continuously(self, symbols: List[str]):
        """Continuously update models in the background."""
        while True:
            try:
                logger.info("Updating ML models...")
                await self.train_models(symbols)
                await asyncio.sleep(self.model_update_interval)
                
            except Exception as e:
                logger.error(f"Error in continuous model update: {e}")
                await asyncio.sleep(300)  # Wait 5 minutes on error
                
    def save_models(self, path: str = "./models"):
        """Save trained models to disk."""
        import os
        os.makedirs(path, exist_ok=True)
        
        for symbol, models in self.models.items():
            for horizon, model in models.items():
                model_path = f"{path}/{symbol}_{horizon}min_model.pkl"
                scaler_path = f"{path}/{symbol}_{horizon}min_scaler.pkl"
                
                joblib.dump(model, model_path)
                joblib.dump(self.scalers[symbol][horizon], scaler_path)
                
        logger.info(f"Models saved to {path}")
        
    def load_models(self, path: str = "./models"):
        """Load models from disk."""
        import os
        
        if not os.path.exists(path):
            logger.warning(f"Model path {path} does not exist")
            return
            
        for filename in os.listdir(path):
            if filename.endswith("_model.pkl"):
                parts = filename.replace("_model.pkl", "").split("_")
                symbol = parts[0]
                horizon = int(parts[1].replace("min", ""))
                
                model_path = os.path.join(path, filename)
                scaler_path = model_path.replace("_model.pkl", "_scaler.pkl")
                
                if os.path.exists(scaler_path):
                    if symbol not in self.models:
                        self.models[symbol] = {}
                        self.scalers[symbol] = {}
                        
                    self.models[symbol][horizon] = joblib.load(model_path)
                    self.scalers[symbol][horizon] = joblib.load(scaler_path)
                    
        logger.info(f"Models loaded from {path}")


# Global instance
price_predictor = PricePredictor()