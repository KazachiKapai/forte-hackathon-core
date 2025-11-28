from __future__ import annotations

import os

from clerk_backend_api import Clerk

clerk_client = Clerk(bearer_auth=os.environ.get("CLERK_SECRET_KEY"))
