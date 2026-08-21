import urllib.request
import json

try:
    url = "http://localhost:8082/api/traceability/search?q=AGR000001783422245368"
    response = urllib.request.urlopen(url)
    data = json.loads(response.read().decode('utf-8'))
    print("API Response success! Status code:", response.getcode())
    print("Pallet:", data.get('pallet'))
    print("Plan:", data.get('plan'))
    print("Materials count:", len(data.get('materials', [])))
    print("First 3 materials:")
    for m in data.get('materials', [])[:3]:
        print("  ", m)
except Exception as e:
    print("Failed to reach server:", e)
