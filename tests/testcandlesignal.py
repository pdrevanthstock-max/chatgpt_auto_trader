from alpha.market_state import MarketState
from alpha.candle_signal import CandleSignal

state = MarketState()

print(CandleSignal.detect(state))

state.update(24000, 24000)

state.update(24050, 24050)

print(CandleSignal.detect(state))

state.update(23950, 23950)

print(CandleSignal.detect(state))