from pprint import pprint

from engine.trading_engine import TradingEngine

position = TradingEngine().run()

print()
print("=" * 80)
print("FINAL POSITION")
print("=" * 80)

pprint(position)