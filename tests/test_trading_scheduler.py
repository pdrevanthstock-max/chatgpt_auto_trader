from engine.trading_scheduler import TradingScheduler

scheduler = TradingScheduler()

scheduler.start(interval=10)