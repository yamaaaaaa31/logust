from logust import logger, parse_json

logger.remove()
logger.add("app.json", serialize=True, mode="w")

logger.bind(user="alice").info("Logged in")
logger.bind(user="bob").error("Payment failed")

for record in parse_json("app.json"):
    print(record["level"], record["message"], record["extra"])

errors = [r for r in parse_json("app.json") if r["level"] == "ERROR"]
print(len(errors), "error(s)")
