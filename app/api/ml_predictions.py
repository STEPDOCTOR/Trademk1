"""Machine learning predictions API endpoints."""
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from typing import Dict, List, Optional, Any
from datetime import datetime

from app.auth.dependencies import get_current_user
from app.models.user import User
from app.services.ml import price_predictor, PricePrediction, MLSignal
from app.monitoring.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/ml", tags=["ml-predictions"])


@router.post("/train")
async def train_models(
    symbols: List[str],
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """Train ML models for given symbols."""
    try:
        # Add training task to background
        background_tasks.add_task(price_predictor.train_models, symbols)
        
        return {
            "status": "training_started",
            "symbols": symbols,
            "message": f"Training ML models for {len(symbols)} symbols in background"
        }
        
    except Exception as e:
        logger.error(f"Error starting model training: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/predict/{symbol}")
async def predict_price(
    symbol: str,
    time_horizon: int = 15,
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """Get price prediction for a symbol."""
    try:
        prediction = await price_predictor.predict_price(symbol, time_horizon)
        
        if not prediction:
            raise HTTPException(
                status_code=404,
                detail=f"No prediction available for {symbol} with {time_horizon}min horizon"
            )
            
        return {
            "symbol": prediction.symbol,
            "current_price": prediction.current_price,
            "predicted_price": prediction.predicted_price,
            "predicted_change": prediction.predicted_change,
            "predicted_change_pct": prediction.predicted_change_pct,
            "confidence": prediction.confidence,
            "time_horizon_minutes": prediction.time_horizon,
            "features_importance": prediction.features_importance,
            "model_type": prediction.model_type,
            "prediction_time": prediction.prediction_time.isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error predicting price for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/predictions")
async def get_predictions(
    symbols: List[str],
    time_horizon: int = 15,
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """Get predictions for multiple symbols."""
    try:
        predictions = []
        
        for symbol in symbols:
            pred = await price_predictor.predict_price(symbol, time_horizon)
            if pred:
                predictions.append({
                    "symbol": pred.symbol,
                    "current_price": pred.current_price,
                    "predicted_price": pred.predicted_price,
                    "predicted_change_pct": pred.predicted_change_pct,
                    "confidence": pred.confidence,
                    "time_horizon_minutes": pred.time_horizon
                })
                
        # Sort by predicted return
        predictions.sort(key=lambda x: abs(x["predicted_change_pct"]), reverse=True)
        
        return {
            "predictions": predictions,
            "count": len(predictions),
            "time_horizon_minutes": time_horizon,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting predictions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/signals")
async def get_ml_signals(
    symbols: List[str],
    min_confidence: float = 0.7,
    min_return: float = 0.002,
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """Get ML-based trading signals."""
    try:
        signals = await price_predictor.generate_signals(
            symbols,
            min_confidence,
            min_return
        )
        
        return {
            "signals": [
                {
                    "symbol": signal.symbol,
                    "action": signal.action,
                    "confidence": signal.confidence,
                    "predicted_return": signal.predicted_return,
                    "time_horizon_minutes": signal.time_horizon,
                    "risk_score": signal.risk_score,
                    "reason": signal.reason
                }
                for signal in signals
            ],
            "count": len(signals),
            "filters": {
                "min_confidence": min_confidence,
                "min_return": min_return
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error generating ML signals: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/model-status")
async def get_model_status(current_user: User = Depends(get_current_user)) -> Dict[str, Any]:
    """Get status of trained models."""
    try:
        model_info = {}
        
        for symbol, models in price_predictor.models.items():
            model_info[symbol] = {
                "horizons": list(models.keys()),
                "count": len(models)
            }
            
        return {
            "trained_symbols": list(price_predictor.models.keys()),
            "total_models": sum(len(m) for m in price_predictor.models.values()),
            "model_details": model_info,
            "feature_columns": price_predictor.feature_columns,
            "prediction_horizons": price_predictor.prediction_horizons,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting model status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/save-models")
async def save_models(
    path: str = "./models",
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """Save trained models to disk."""
    try:
        price_predictor.save_models(path)
        
        return {
            "status": "success",
            "message": f"Models saved to {path}",
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error saving models: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/load-models")
async def load_models(
    path: str = "./models",
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """Load models from disk."""
    try:
        price_predictor.load_models(path)
        
        # Get loaded model status
        model_count = sum(len(m) for m in price_predictor.models.values())
        
        return {
            "status": "success",
            "message": f"Models loaded from {path}",
            "models_loaded": model_count,
            "symbols": list(price_predictor.models.keys()),
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error loading models: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/start-continuous-training")
async def start_continuous_training(
    symbols: List[str],
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """Start continuous model training in background."""
    try:
        # Add continuous training task
        background_tasks.add_task(
            price_predictor.update_models_continuously,
            symbols
        )
        
        return {
            "status": "started",
            "symbols": symbols,
            "update_interval_seconds": price_predictor.model_update_interval,
            "message": "Continuous ML model training started"
        }
        
    except Exception as e:
        logger.error(f"Error starting continuous training: {e}")
        raise HTTPException(status_code=500, detail=str(e))