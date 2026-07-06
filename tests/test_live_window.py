from alpha.option_chain import OptionChain
from alpha.strike_selector import StrikeSelector

chain = OptionChain().download()

selector = StrikeSelector(chain)
window = selector.get_window()

print("=" * 80)
print("SPOT:", chain["spot"])
print("ATM :", selector.get_atm())
print("=" * 80)

for strike in window:

    option = chain["chain"][f"{strike:.6f}"]

    ce = option["ce"]
    pe = option["pe"]

    print("-" * 80)
    print(f"STRIKE : {strike}")

    print(
        "CE |",
        "LTP:", ce["last_price"],
        "OI:", ce["oi"],
        "VOL:", ce["volume"],
        "BID:", ce["top_bid_price"],
        "ASK:", ce["top_ask_price"]
    )

    print(
        "PE |",
        "LTP:", pe["last_price"],
        "OI:", pe["oi"],
        "VOL:", pe["volume"],
        "BID:", pe["top_bid_price"],
        "ASK:", pe["top_ask_price"]
    )