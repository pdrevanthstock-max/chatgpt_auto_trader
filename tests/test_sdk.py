from broker.dhan_client import DhanClient
from pprint import pprint

broker = DhanClient()

response = broker.client.expiry_list(
    under_security_id=13,
    under_exchange_segment=broker.client.INDEX,
)

pprint(response)