from pprint import pprint

from engine.position_monitor import PositionMonitor

position = {

    "entry_price":150,

    "quantity":75,

    "closed":False
}

updated = PositionMonitor.update(
    position,
    154
)

pprint(updated)