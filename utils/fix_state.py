import json

with open("crawler_state.json", "r") as f:
    state = json.load(f)

state["processed"] = 30

with open("crawler_state.json", "w") as f:
    json.dump(state, f, indent=2)
