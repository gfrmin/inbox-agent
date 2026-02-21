import os

import httpx

EMAIL_PROPERTIES = [
    "id",
    "subject",
    "from",
    "preview",
    "receivedAt",
    "threadId",
    "mailboxIds",
    "keywords",
]


class JMAPClient:
    def __init__(self):
        self.user = os.environ.get("FASTMAIL_USER")
        self.token = os.environ.get("FASTMAIL_TOKEN")
        if not self.user or not self.token:
            raise RuntimeError(
                "FASTMAIL_USER and FASTMAIL_TOKEN must be set in environment or .env"
            )
        self._discover_session()

    def _discover_session(self):
        resp = httpx.get(
            "https://api.fastmail.com/.well-known/jmap",
            headers={"Authorization": f"Bearer {self.token}"},
            follow_redirects=True,
        )
        resp.raise_for_status()
        data = resp.json()
        self.api_url = data["apiUrl"]
        self.account_id = data["primaryAccounts"]["urn:ietf:params:jmap:mail"]

    def _jmap_call(self, method_calls: list) -> list:
        resp = httpx.post(
            self.api_url,
            headers={"Authorization": f"Bearer {self.token}"},
            json={
                "using": [
                    "urn:ietf:params:jmap:core",
                    "urn:ietf:params:jmap:mail",
                ],
                "methodCalls": method_calls,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        responses = data["methodResponses"]
        for r in responses:
            if r[0].endswith("/error") or r[0] == "error":
                raise RuntimeError(f"JMAP error in {r[0]}: {r[1]}")
        return responses

    def _get_mailbox_id_by_role(self, role: str) -> str:
        resp = self._jmap_call([
            ["Mailbox/get", {"accountId": self.account_id, "ids": None}, "m0"]
        ])
        mailboxes = resp[0][1]["list"]
        return next(m["id"] for m in mailboxes if m.get("role") == role)

    def _query_email_ids(self, mailbox_id: str, limit: int | None = None) -> list[str]:
        all_ids = []
        position = 0
        batch_size = 500
        while True:
            if limit is not None:
                remaining = limit - len(all_ids)
                if remaining <= 0:
                    break
                batch_size = min(500, remaining)
            responses = self._jmap_call([
                [
                    "Email/query",
                    {
                        "accountId": self.account_id,
                        "filter": {"inMailbox": mailbox_id},
                        "sort": [{"property": "receivedAt", "isAscending": False}],
                        "position": position,
                        "limit": batch_size,
                    },
                    "0",
                ]
            ])
            ids = responses[0][1]["ids"]
            if not ids:
                break
            all_ids.extend(ids)
            position += len(ids)
            if len(ids) < batch_size:
                break
        return all_ids[:limit] if limit else all_ids

    def _fetch_emails(self, ids: list[str]) -> list[dict]:
        all_emails = []
        for i in range(0, len(ids), 100):
            chunk = ids[i : i + 100]
            responses = self._jmap_call([
                [
                    "Email/get",
                    {
                        "accountId": self.account_id,
                        "ids": chunk,
                        "properties": EMAIL_PROPERTIES,
                    },
                    "0",
                ]
            ])
            all_emails.extend(responses[0][1]["list"])
        return all_emails

    def get_inbox_emails(self, limit: int = 500) -> list[dict]:
        mailbox_id = self._get_mailbox_id_by_role("inbox")
        ids = self._query_email_ids(mailbox_id, limit)
        return self._fetch_emails(ids)
