# Fast path engine (Command Center)

Command Center **Run** uses `FastPathEngine` (`core/fast_path.py`): 1 ICMP probe/hop via `ping -n 1 -i TTL -w 300`, async PTR fill-in, prompt Cancel (taskkill). Stock Windows `tracert` remains for Classic tabs (`TracerouteEngine`).

