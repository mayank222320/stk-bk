from domain.calc.sizing import calculate_position_size

# Fallback stub if core.database is not accessible in tests
class MockDB:
    class _SwingPositions:
        def find(self, query):
            class Cursor:
                async def __aiter__(self):
                    return
                async def __anext__(self):
                    raise StopAsyncIteration
            return Cursor()
    
    swing_positions = _SwingPositions()

class MockMongo:
    db = MockDB()

try:
    from core.database import mongo
except ImportError:
    mongo = MockMongo()

def get_risk_config():
    return { 
        "capital": 500000.0, 
        "risk_pct": 1.0, 
        "max_heat_pct": 5.0, 
        "max_single_pct": 15.0, 
        "hard_block": True 
    }

def get_regime():
    return {
        "state": "RISK_ON", 
        "size_multiplier": 1.0, 
        "max_positions": 5
    }

async def portfolio_heat() -> dict:
    """
    Read from the swing_positions collection to sum up the risk of all OPEN positions
    (risk = qty * (fill_price - stop_loss)).
    """
    total_risk = 0.0
    open_positions = 0
    
    if mongo.db is not None:
        try:
            cursor = mongo.db.swing_positions.find({"status": "OPEN"})
            if hasattr(cursor, 'to_list'):
                # Motor cursor
                positions = await cursor.to_list(None)
                for pos in positions:
                    qty = pos.get("qty", 0)
                    fill_price = pos.get("fill_price", 0.0)
                    stop_loss = pos.get("stop_loss", 0.0)
                    
                    if qty > 0 and fill_price > stop_loss:
                        total_risk += qty * (fill_price - stop_loss)
                    open_positions += 1
            else:
                # Async for (mock or different driver)
                async for pos in cursor:
                    qty = pos.get("qty", 0)
                    fill_price = pos.get("fill_price", 0.0)
                    stop_loss = pos.get("stop_loss", 0.0)
                    
                    if qty > 0 and fill_price > stop_loss:
                        total_risk += qty * (fill_price - stop_loss)
                    open_positions += 1
        except Exception as e:
            pass
            
    config = get_risk_config()
    heat_pct = (total_risk / config["capital"]) * 100 if config["capital"] > 0 else 0
    
    return {
        "total_risk": total_risk,
        "heat_pct": heat_pct,
        "open_positions": open_positions,
        "max_heat_pct": config["max_heat_pct"],
        "max_positions": get_regime()["max_positions"]
    }

async def size_position(entry: float, stop: float) -> dict:
    """
    Calculate position size based on entry, stop, config, and regime.
    Also checks if it exceeds the portfolio heat.
    """
    config = get_risk_config()
    regime = get_regime()
    
    calc = calculate_position_size(
        entry=entry,
        stop=stop,
        capital=config["capital"],
        risk_pct=config["risk_pct"],
        size_multiplier=regime["size_multiplier"],
        max_single_pct=config["max_single_pct"]
    )
    
    heat = await portfolio_heat()
    
    new_heat_pct = heat["heat_pct"] + (calc["risk_amount"] / config["capital"]) * 100
    
    blocked = False
    reasons = []
    
    if heat["open_positions"] >= regime["max_positions"]:
        blocked = True
        reasons.append("max positions reached")
        
    if new_heat_pct > config["max_heat_pct"]:
        if config["hard_block"]:
            blocked = True
            reasons.append("max heat breached")
        else:
            reasons.append("heat warning")
            
    calc["blocked"] = blocked
    calc["reasons"] = reasons
    calc["new_heat_pct"] = new_heat_pct
    calc["current_heat"] = heat
    
    return calc
