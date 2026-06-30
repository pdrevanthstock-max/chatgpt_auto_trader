from broker.dhan_client import DhanClient

client = DhanClient()

client.connect()

print("=" * 60)

print("PROFILE")

print(client.get_profile())

print("=" * 60)

print("FUNDS")

print(client.get_funds())

print("=" * 60)