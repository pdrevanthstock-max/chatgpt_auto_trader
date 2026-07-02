from dataclasses import dataclass


@dataclass
class OptionLeg:

    strike: float
    option_type: str

    security_id: int

    last_price: float

    oi: int

    volume: int

    iv: float

    delta: float

    gamma: float

    theta: float

    vega: float


@dataclass
class OptionPair:

    call: OptionLeg

    put: OptionLeg

    score: float = 0.0