"""Trailing stop model for dynamic stop loss management."""
from sqlalchemy import Column, String, Float, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from app.models.base import Base


class TrailingStop(Base):
    """Model for tracking trailing stop configurations per position."""
    
    __tablename__ = "trailing_stops"
    
    # Position reference
    symbol = Column(String, nullable=False, unique=True, index=True)
    
    # Trailing stop configuration
    enabled = Column(Boolean, default=True)
    trail_percent = Column(Float, nullable=False, default=0.02)  # 2% default
    trail_amount = Column(Float, nullable=True)  # Alternative: fixed dollar amount
    
    # Current state
    initial_price = Column(Float, nullable=False)  # Entry price
    highest_price = Column(Float, nullable=False)  # Highest price since entry
    stop_price = Column(Float, nullable=False)     # Current stop loss price
    
    # Tracking
    last_updated = Column(DateTime(timezone=True), default=datetime.utcnow)
    times_adjusted = Column(Float, default=0)      # How many times stop was raised
    
    # Status
    is_active = Column(Boolean, default=True)
    triggered_at = Column(DateTime(timezone=True), nullable=True)
    triggered_price = Column(Float, nullable=True)
    
    def update_stop(self, current_price: float) -> bool:
        """Update trailing stop based on current price.
        
        Returns:
            bool: True if stop was updated, False otherwise
        """
        if not self.enabled or not self.is_active:
            return False
        
        # Check if we have a new high
        if current_price > self.highest_price:
            self.highest_price = current_price
            
            # Calculate new stop price
            if self.trail_amount:
                # Fixed dollar amount trailing
                new_stop = current_price - self.trail_amount
            else:
                # Percentage trailing
                new_stop = current_price * (1 - self.trail_percent)
            
            # Only raise stop, never lower it
            if new_stop > self.stop_price:
                self.stop_price = new_stop
                self.times_adjusted += 1
                self.last_updated = datetime.utcnow()
                return True
        
        return False
    
    def check_triggered(self, current_price: float) -> bool:
        """Check if trailing stop has been triggered.
        
        Returns:
            bool: True if stop is triggered, False otherwise
        """
        if not self.enabled or not self.is_active:
            return False
        
        if current_price <= self.stop_price:
            self.is_active = False
            self.triggered_at = datetime.utcnow()
            self.triggered_price = current_price
            return True
        
        return False
    
    def __repr__(self):
        return f"<TrailingStop {self.symbol} stop@{self.stop_price:.2f} high@{self.highest_price:.2f}>"