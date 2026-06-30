from broker.market_data import MarketData

market = MarketData()

print("=" * 60)

print("EXPIRY")

print("=" * 60)

expiry = market.get_current_expiry()

print(expiry)

print()

print("=" * 60)

print("DOWNLOADING OPTION CHAIN")

print("=" * 60)

chain = market.download_option_chain()

print(type(chain))

print(len(chain))

print()

print("=" * 60)

print("SUMMARY")

print("=" * 60)

print(market.summary())