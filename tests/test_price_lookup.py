from alpha.option_chain import OptionChain
from engine.price_lookup import PriceLookup

chain = OptionChain().download()

security = 44620      # use your current CE security id

price = PriceLookup.get_price(
    chain["chain"],
    security,
)

print(price)