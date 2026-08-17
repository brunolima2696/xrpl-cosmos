import requests
from decimal import Decimal

# COSMOS_REST_URL = "http://localhost:1317"  # Chain A
COSMOS_REST_URL = "http://localhost:2317"  # Chain B
# COSMOS_REST_URL = "http://localhost:3317"  # Chain C


ADDRESS = "ethm1dakgyqjulg29m5fmv992g2y66m9g2mjn6hahwg"

url = f"{COSMOS_REST_URL}/cosmos/bank/v1beta1/balances/{ADDRESS}"

response = requests.get(url)
data = response.json()

print("Address:", ADDRESS)
print()

for balance in data["balances"]:
    denom = balance["denom"]
    amount = int(balance["amount"])

    print("Denom:", denom)
    print("Amount:", amount)

    if denom == "axrp":
        amount_xrp = Decimal(amount) / Decimal(10**18)
        print("Amount XRP:", amount_xrp)

    print()