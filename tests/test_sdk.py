from broker.dhan_client import DhanClient
import inspect

broker = DhanClient()

print("=" * 60)
print("OPTION CHAIN SIGNATURE")
print("=" * 60)

print(inspect.signature(broker.client.option_chain))