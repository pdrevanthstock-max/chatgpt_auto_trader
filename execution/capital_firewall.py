import math


class LiveCapitalFirewall:
    """Independent last-line budget check for every LIVE entry basket."""

    def __init__(self, allocation_limit: float, reserve_pct: float = 0.10) -> None:
        allocation = float(allocation_limit)
        reserve = float(reserve_pct)
        if not math.isfinite(allocation) or allocation <= 0.0:
            raise ValueError("LIVE strategy allocation must be finite and positive.")
        if not math.isfinite(reserve) or not 0.0 <= reserve < 1.0:
            raise ValueError("LIVE reserve percentage must be between 0 and 1.")
        self.allocation_limit = round(allocation, 2)
        self.reserve_pct = reserve

    @property
    def deployable_limit(self) -> float:
        return round(self.allocation_limit * (1.0 - self.reserve_pct), 2)

    def authorize_entry(
        self,
        required_funds: float,
        broker_available_funds: float | None,
    ) -> None:
        required = float(required_funds)
        if not math.isfinite(required) or required <= 0.0:
            raise ValueError("Required LIVE entry funds must be finite and positive.")
        if broker_available_funds is None:
            raise ValueError("LIVE entry requires broker-confirmed available funds.")
        broker_funds = float(broker_available_funds)
        if not math.isfinite(broker_funds) or broker_funds < 0.0:
            raise ValueError("LIVE entry requires valid broker-confirmed available funds.")
        if required > self.allocation_limit:
            raise ValueError(
                f"Required funds Rs {required:.2f} exceed strategy allocation "
                f"Rs {self.allocation_limit:.2f}."
            )
        if required > self.deployable_limit:
            raise ValueError(
                f"Required funds Rs {required:.2f} exceed deployable allocation "
                f"Rs {self.deployable_limit:.2f} after reserve."
            )
        if required > broker_funds:
            raise ValueError(
                f"Required funds Rs {required:.2f} exceed broker-confirmed available "
                f"funds Rs {broker_funds:.2f}."
            )
