from alpha.market_state import MarketState

state = MarketState()

print(state.is_first_run())

state.update(24000, 24000)

print(state.is_first_run())

state.update(24035, 24050)

print(state.movement())