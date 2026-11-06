# Kill Switch Operations

Kill switches live in `app.core.kill_switch`:

```python
from app.core.kill_switch import KILL_SWITCHES

KILL_SWITCHES.set("models", True, reason="provider outage")
KILL_SWITCHES.require("models")  # raises ServiceUnavailableError
KILL_SWITCHES.set("models", False)
```

Default switches: `models`, `evaluation`, `mcp`. Changes must be audited and
require operator permission. Test in staging before using in an incident.
