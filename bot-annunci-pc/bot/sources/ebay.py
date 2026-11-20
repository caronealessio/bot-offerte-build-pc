"""eBay.it tramite l'API ufficiale Browse (serve un account sviluppatore gratuito)."""
from __future__ import annotations

import base64
import os

from ..common import Annuncio, Http

TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"

_token: str | None = None


def configurato() -> bool:
    return bool(os.getenv("EBAY_CLIENT_ID") and os.getenv("EBAY_CLIENT_SECRET"))


def _get_token(http: Http) -> str:
    global _token
    if _token:
        return _token
    cred = f"{os.environ['EBAY_CLIENT_ID']}:{os.environ['EBAY_CLIENT_SECRET']}"
    r = http.post(
        TOKEN_URL,
        headers={
            "Authorization": "Basic " + base64.b64encode(cred.encode()).decode(),
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={"grant_type": "client_credentials", "scope": "https://api.ebay.com/oauth/api_scope"},
    )
    _token = r.json()["access_token"]
    return _token


def parse(data: dict) -> list[Annuncio]:
    out: list[Annuncio] = []
    for it in data.get("itemSummaries", []) or []:
        price = it.get("price") or {}
        if price.get("currency") not in (None, "EUR"):
            continue
        try:
            prezzo = float(price.get("value"))
        except (TypeError, ValueError):
            continue
        sped = None
        for opt in it.get("shippingOptions", []) or []:
            cost = (opt.get("shippingCost") or {}).get("value")
            if cost is not None:
                c = float(cost)
                sped = c if sped is None else min(sped, c)
        seller = it.get("seller") or {}
        loc = it.get("itemLocation") or {}
        pct = seller.get("feedbackPercentage")
        out.append(Annuncio(
            fonte="eBay",
            id=it.get("itemId", ""),
            titolo=it.get("title", ""),
            prezzo=prezzo,
            spedizione=sped,
            url=it.get("itemWebUrl", ""),
            luogo=", ".join(x for x in [loc.get("city"), loc.get("country")] if x),
            venditore=seller.get("username", ""),
            feedback=seller.get("feedbackScore"),
            feedback_pct=float(pct) if pct not in (None, "") else None,
            condizione=it.get("condition", ""),
            descrizione=" ".join(it.get("buyingOptions", []) or []),
        ))
    return out


def cerca(http: Http, query: str) -> list[Annuncio]:
    token = _get_token(http)
    r = http.get(
        SEARCH_URL,
        params={
            "q": query,
            "limit": "50",
            "sort": "newlyListed",
            # solo "Compralo subito", spedizione in Italia
            "filter": "buyingOptions:{FIXED_PRICE},deliveryCountry:IT,itemLocationCountry:IT",
        },
        headers={
            "Authorization": f"Bearer {token}",
            "X-EBAY-C-MARKETPLACE-ID": "EBAY_IT",
            "Accept-Language": "it-IT",
        },
    )
    return parse(r.json())
