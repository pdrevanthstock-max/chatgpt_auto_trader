"""Backward-compatible display helpers for trades held across Streamlit reloads."""


def units_per_leg(trade) -> int:
    value = getattr(trade, "units_per_leg", None)
    if value is not None:
        return int(value)
    return int(trade.quantity) * int(trade.lot_size)


def is_post_daily_sl(trade) -> bool:
    return bool(getattr(trade, "post_daily_sl", False))


def display_trade_id(trade) -> str:
    trade_id = str(getattr(trade, "id", ""))
    if is_post_daily_sl(trade) and not trade_id.endswith("-SL"):
        return f"{trade_id}-SL"
    return trade_id


def daily_sl_status(trade) -> str:
    return "POST-SL" if is_post_daily_sl(trade) else "NORMAL"
