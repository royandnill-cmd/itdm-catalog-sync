import os
import json
import time
import urllib.parse
from datetime import datetime, timezone

import requests

BASE = "https://api.al-style.kz"
TOKEN = os.environ.get("ALSTYLE_TOKEN")

if not TOKEN:
    raise SystemExit("Missing ALSTYLE_TOKEN env var")

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "it-industry.kz catalog sync/1.0"})

RATE_SLEEP = 5.2  # лимит 1 запрос / 5 секунд (с запасом)

def get(url, params=None):
    if params is None:
        params = {}
    # в доке встречается access-token / access_token, но чаще access-token
    params["access-token"] = TOKEN
    r = SESSION.get(url, params=params, timeout=60)
    r.raise_for_status()
    return r.json()

def fetch_all_products():
    # Берем товары постранично, сразу с нужными доп. полями
    # additional_fields: images, url, brand, warranty, weight, warehouses, marketplaceArticles и т.д.
    # Мы начнем с images+url+brand для витрины.
    additional_fields = "images,url,brand"
    limit = 250
    offset = 0
    all_items = []

    while True:
        data = get(f"{BASE}/api/elements-pagination", {
            "limit": limit,
            "offset": offset,
            "additional_fields": additional_fields,
            # "exclude_missing": True,  # если хочешь скрывать нулевые остатки
        })
        elements = data.get("elements") or []
        all_items.extend(elements)

        pag = data.get("pagination") or {}
        total = int(pag.get("totalCount") or 0)
        offset += limit

        time.sleep(RATE_SLEEP)

        if offset >= total or not elements:
            break

    return all_items

def fetch_qty_price_all():
    # В доке: если не указывать article — вернет все товары
    # Это может быть большим ответом, но удобно для слияния цен/остатков.
    data = get(f"{BASE}/api/quantity-price", {
        # "exclude_missing": True,
    })
    time.sleep(RATE_SLEEP)
    return data

def normalize_qty(q):
    # quantity может быть числом или строкой вида ">50" / ">100" :contentReference[oaicite:8]{index=8}
    if isinstance(q, (int, float)):
        return int(q)
    s = str(q).strip()
    if s.startswith(">"):
        # сделаем условно 999 для сортировки, а отображать будем как есть
        return 999
    try:
        return int(s)
    except:
        return 0

def main():
    products = fetch_all_products()
    qp = fetch_qty_price_all()

    # qp приходит объектом: { "37454": {quantity, price1, price2, ...}, ... } :contentReference[oaicite:9]{index=9}
    out = []
    for p in products:
        article = str(p.get("article"))
        qp_row = qp.get(article) or {}

        item = {
            "supplier": "Al-Style",
            "article": p.get("article"),
            "article_pn": p.get("article_pn"),
            "name": p.get("name"),
            "full_name": p.get("full_name"),
            "category": p.get("category"),
            "price1": qp_row.get("price1", p.get("price1")),
            "price2": qp_row.get("price2", p.get("price2")),
            "quantity_raw": qp_row.get("quantity", p.get("quantity")),
            "quantity_sort": normalize_qty(qp_row.get("quantity", p.get("quantity"))),
            "discountPrice": qp_row.get("discountPrice"),
            "discount": qp_row.get("discount"),
            "warehouse": qp_row.get("warehouse"),
            "url": p.get("url"),
            "images": p.get("images") or [],
            "isnew": p.get("isnew", 0),
            "updatedAt": datetime.now(timezone.utc).isoformat(),
        }
        out.append(item)

    # Сортировка: сначала в наличии, потом по имени
    out.sort(key=lambda x: (-int(x["quantity_sort"] > 0), str(x["name"] or "")))

    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "count": len(out),
        "items": out
    }

    with open("catalog-alstyle.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print("OK:", payload["count"])

if __name__ == "__main__":
    main()
