from dataclasses import dataclass


# Dhan/NSE equity-option rates applicable on 2026-07-14.
# Brokerage: Dhan pricing, ₹20 per executed option order.
# Exchange: NSE/FA/73061, effective 2026-03-01, ₹3,552/crore premium turnover.
# STT: Finance Act 2026, effective 2026-04-01, 0.15% of sell premium turnover.
DHAN_BROKERAGE_PER_OPTION_ORDER = 20.0
NSE_OPTION_TRANSACTION_RATE = 0.0003552
OPTION_STT_SELL_RATE = 0.0015
SEBI_TURNOVER_RATE = 0.000001
OPTION_BUY_STAMP_DUTY_RATE = 0.00003
GST_RATE = 0.18


@dataclass(frozen=True)
class OptionCostBreakdown:
    brokerage: float
    exchange_transaction_charge: float
    stt: float
    sebi_turnover_fee: float
    stamp_duty: float
    gst: float

    @property
    def total(self) -> float:
        return round(
            self.brokerage
            + self.exchange_transaction_charge
            + self.stt
            + self.sebi_turnover_fee
            + self.stamp_duty
            + self.gst,
            2,
        )


def calculate_option_round_trip_costs(
    entry_ce_price: float,
    entry_pe_price: float,
    exit_ce_price: float,
    exit_pe_price: float,
    lots: int,
    lot_size: int,
    executed_order_count: int = 4,
) -> OptionCostBreakdown:
    """Estimate all-in costs for two option buys followed by two option sells."""
    if lots <= 0 or lot_size <= 0:
        return OptionCostBreakdown(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    prices = (entry_ce_price, entry_pe_price, exit_ce_price, exit_pe_price)
    if any(price < 0.0 for price in prices):
        raise ValueError("Option prices used for transaction costs cannot be negative.")

    units_per_leg = lots * lot_size
    buy_turnover = (entry_ce_price + entry_pe_price) * units_per_leg
    sell_turnover = (exit_ce_price + exit_pe_price) * units_per_leg
    total_turnover = buy_turnover + sell_turnover

    if executed_order_count < 0:
        raise ValueError("executed_order_count cannot be negative.")
    brokerage = DHAN_BROKERAGE_PER_OPTION_ORDER * executed_order_count
    exchange_charge = total_turnover * NSE_OPTION_TRANSACTION_RATE
    stt = sell_turnover * OPTION_STT_SELL_RATE
    sebi_fee = total_turnover * SEBI_TURNOVER_RATE
    stamp_duty = buy_turnover * OPTION_BUY_STAMP_DUTY_RATE
    gst = (brokerage + exchange_charge + sebi_fee) * GST_RATE

    return OptionCostBreakdown(
        brokerage=round(brokerage, 2),
        exchange_transaction_charge=round(exchange_charge, 4),
        stt=round(stt, 4),
        sebi_turnover_fee=round(sebi_fee, 4),
        stamp_duty=round(stamp_duty, 4),
        gst=round(gst, 4),
    )
