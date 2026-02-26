"""
Firebase client for state management and trade logging.
Implements robust error handling with fallback local storage.
"""
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict
import os

try:
    import firebase_admin
    from firebase_admin import credentials, firestore
    from google.cloud.firestore import Client as FirestoreClient
    FIREBASE_AVAILABLE = True
except ImportError:
    FIREBASE_AVAILABLE = False
    logging.warning("firebase-admin not installed. Using local storage fallback.")

@dataclass
class TradeRecord:
    """Data class for trade records with type safety."""
    symbol: str
    action: str  # BUY, SELL, HOLD
    price: float
    quantity: float
    timestamp: datetime
    strategy: str
    confidence: float
    portfolio_value: float
    metadata: Dict[str, Any] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to Firestore-compatible dictionary."""
        data = asdict(self)
        data['timestamp'] = self.timestamp
        data['metadata'] = self.metadata or {}
        return data

class FirebaseStateManager:
    """Robust state management with Firebase Firestore fallback to local storage."""
    
    def __init__(self, credentials_path: str = None, fallback_path: str = "local_state.json"):
        self._db = None
        self.fallback_path = fallback_path
        self._initialized = False
        
        if FIREBASE_AVAILABLE and credentials_path and os.path.exists(credentials_path):
            try:
                cred = credentials.Certificate(credentials_path)
                firebase_admin.initialize_app(cred)
                self._db = firestore.client()
                self._initialized = True
                logging.info("Firebase initialized successfully")
            except Exception as e:
                logging.error(f"Firebase initialization failed: {e}")
                self._setup_local_fallback()
        else:
            self._setup_local_fallback()
    
    def _setup_local_fallback(self):
        """Setup local JSON file storage as fallback."""
        logging.warning("Using local storage fallback for state management")
        os.makedirs(os.path.dirname(self.fallback_path) or '.', exist_ok=True)
        self._initialized = True
    
    def save_trade(self, trade: TradeRecord) -> bool:
        """Save trade record with error handling."""
        if not self._initialized:
            logging.error("State manager not initialized")
            return False
        
        try:
            data = trade.to_dict()
            
            if self._db:
                # Firebase storage
                collection = self._db.collection('trades')
                collection.add(data)
            else:
                # Local storage fallback
                self._save_to_local_file('trades', data)
            
            logging.info(f"Trade saved: {trade.symbol} {trade.action} at {trade.price}")
            return True
            
        except Exception as e:
            logging.error(f"Failed to save trade: {e}")
            return False
    
    def save_portfolio_state(self, portfolio: Dict[str, Any]) -> bool:
        """Save current portfolio state."""
        try:
            portfolio['last_updated'] = datetime.now()
            
            if self._db:
                doc_ref = self._db.collection('portfolio').document('current')
                doc_ref.set(portfolio)
            else:
                self._save_to_local_file('portfolio', portfolio)
            
            return True
        except Exception as e:
            logging.error(f"Failed to save portfolio: {e}")
            return False
    
    def get_recent_trades(self, symbol: str = None, limit: int = 100) -> List[Dict]:
        """Retrieve recent trades with optional symbol filter."""
        try:
            if self._db:
                collection = self._db.collection('trades')
                query = collection.order_by('timestamp', direction=firestore.Query.DESCENDING)
                
                if symbol:
                    query = query.where('symbol', '==', symbol)
                
                trades = [doc.to_dict() for doc in query.limit(limit).stream()]
                return trades
            else:
                return self._load_from_local_file('trades')[:limit]
        except Exception as e:
            logging.error(f"Failed to fetch trades: {e}")
            return []
    
    def _save_to_local_file(self, data_type: str, data: Dict):
        """Save data to local JSON file."""
        try:
            filepath = f"{self.fallback_path}_{data_type}.json"
            existing = []
            
            if os.path.exists(filepath):
                with open(filepath, 'r') as f:
                    existing = json.load(f)
            
            existing.append(data