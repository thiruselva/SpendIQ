"""
Email Parser — Stubs for Gmail and Outlook email sync.
Full implementation requires OAuth2 credentials.
"""


class GmailSync:
    """Gmail receipt sync via Gmail API (OAuth2)."""

    def __init__(self, client_id: str = None, client_secret: str = None):
        self.client_id = client_id
        self.client_secret = client_secret
        self.is_configured = bool(client_id and client_secret)

    def get_status(self) -> dict:
        return {
            "source": "gmail",
            "configured": self.is_configured,
            "status": "ready" if self.is_configured else "not_configured",
            "message": (
                "Gmail sync ready"
                if self.is_configured
                else "Set GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET in .env"
            ),
        }

    async def fetch_receipts(self, since_days: int = 30) -> list[dict]:
        """Fetch receipt emails from Gmail. Requires OAuth2 setup."""
        if not self.is_configured:
            return []
        # TODO: Implement Gmail API OAuth2 flow and receipt fetching
        # 1. Authenticate with OAuth2
        # 2. Search for emails matching receipt patterns
        # 3. Extract transaction data from email body
        # 4. Return list of transaction dicts
        return []


class OutlookSync:
    """Outlook/Microsoft 365 email sync via Microsoft Graph API."""

    def __init__(self, client_id: str = None, client_secret: str = None):
        self.client_id = client_id
        self.client_secret = client_secret
        self.is_configured = bool(client_id and client_secret)

    def get_status(self) -> dict:
        return {
            "source": "outlook",
            "configured": self.is_configured,
            "status": "ready" if self.is_configured else "not_configured",
            "message": (
                "Outlook sync ready"
                if self.is_configured
                else "Set OUTLOOK_CLIENT_ID and OUTLOOK_CLIENT_SECRET in .env"
            ),
        }

    async def fetch_receipts(self, since_days: int = 30) -> list[dict]:
        """Fetch receipt emails from Outlook. Requires Microsoft Graph API setup."""
        if not self.is_configured:
            return []
        # TODO: Implement Microsoft Graph API flow
        return []
