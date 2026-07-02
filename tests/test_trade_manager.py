from engine.trade_manager import TradeManager

trade = {

    "direction": "LONG_CE",

    "entry_security_id": 1,

    "hedge_security_id": 2,

    "entry_price": 100,

    "quantity": 75,

}

manager = TradeManager()

print(manager.has_position())

manager.open(trade)

print(manager.has_position())

manager.update(110)

print(manager.position)

manager.close()

print(manager.has_position())