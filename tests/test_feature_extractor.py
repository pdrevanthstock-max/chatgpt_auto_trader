from pprint import pprint

from alpha.option_chain import OptionChain
from alpha.strike_selector import StrikeSelector
from alpha.pair_generator import PairGenerator
from alpha.feature_extractor import FeatureExtractor

chain = OptionChain().download()

selector = StrikeSelector(chain)

window = selector.get_window()

pairs = PairGenerator.generate(
    window,
    chain["chain"]
)

features = FeatureExtractor.extract(
    pairs[0],
    selector.get_atm()
)

pprint(features)