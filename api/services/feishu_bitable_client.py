import logging
from typing import Any

import requests


logger = logging.getLogger(__name__)


class FeishuBitableClient:
    def __init__(self, app_id: str, app_secret: str):
        self.app_id = app_id
        self.app_secret = app_secret
        self._session = requests.Session()
        self._session.trust_env = False

    def _get(self, url: str, token: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        response = self._session.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
            params=params,
            timeout=30,
        )
        return self._parse_response(response)

    def _post(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = self._session.post(
            url,
            headers={"Content-Type": "application/json; charset=utf-8"},
            json=payload,
            timeout=30,
        )
        return self._parse_response(response)

    @staticmethod
    def _parse_response(response: requests.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except Exception as exc:
            raise RuntimeError(f"Feishu API returned non-JSON response: HTTP {response.status_code}") from exc
        if payload.get("code") != 0:
            raise RuntimeError(f"Feishu API error {payload.get('code')}: {payload.get('msg')}")
        return payload.get("data") or {}

    def get_tenant_access_token(self) -> str:
        if not self.app_id or not self.app_secret:
            raise RuntimeError("FEISHU_APP_ID/FEISHU_APP_SECRET is not configured")
        response = self._session.post(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            headers={"Content-Type": "application/json; charset=utf-8"},
            json={"app_id": self.app_id, "app_secret": self.app_secret},
            timeout=30,
        )
        try:
            payload = response.json()
        except Exception as exc:
            raise RuntimeError(f"Feishu token API returned non-JSON response: HTTP {response.status_code}") from exc
        if payload.get("code") != 0:
            raise RuntimeError(f"Feishu token API error {payload.get('code')}: {payload.get('msg')}")
        token = payload.get("tenant_access_token")
        if not token:
            raise RuntimeError("Feishu tenant_access_token is empty")
        return str(token)

    def resolve_wiki_token(self, tenant_token: str, wiki_token: str) -> tuple[str | None, str | None]:
        data = self._get(
            "https://open.feishu.cn/open-apis/wiki/v2/spaces/get_node",
            tenant_token,
            {"token": wiki_token},
        )
        node = data.get("node") or {}
        return node.get("obj_type"), node.get("obj_token")

    def list_tables(self, tenant_token: str, app_token: str) -> list[dict[str, Any]]:
        url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables"
        return self._list_paginated(url, tenant_token)

    def list_fields(self, tenant_token: str, app_token: str, table_id: str) -> list[dict[str, Any]]:
        url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/fields"
        return self._list_paginated(url, tenant_token)

    def list_records(self, tenant_token: str, app_token: str, table_id: str) -> list[dict[str, Any]]:
        url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records"
        return self._list_paginated(url, tenant_token, page_size=500)

    def _list_paginated(
        self,
        url: str,
        tenant_token: str,
        *,
        page_size: int = 100,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        page_token: str | None = None
        while True:
            params: dict[str, Any] = {"page_size": page_size}
            if page_token:
                params["page_token"] = page_token
            data = self._get(url, tenant_token, params)
            items.extend(data.get("items") or [])
            if not data.get("has_more"):
                break
            page_token = data.get("page_token")
            if not page_token:
                logger.warning("Feishu pagination has_more=true but page_token is empty for %s", url)
                break
        return items
