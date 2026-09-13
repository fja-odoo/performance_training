#!/usr/bin/env python3
"""Populate N distinct partners, each with M sale orders, using Odoo's
JSON-2 RPC API (POST /json/2/<model>/<method>, bearer-token auth), for perf
testing.

The JSON-2 API requires an API key (Authorization: Bearer <key>). If none is
supplied via --api-key, one is minted automatically for the given user via
the standard identity-check flow (POST /web/session/authenticate +
/web/dataset/call_kw) -- that bootstrap step is unavoidable since minting a
key is itself a check_identity-protected action, but every actual data
operation (partner/product/sale order creation) goes through /json/2.

Records are created in batches (single `create` call with many `vals_list`
entries) rather than one HTTP call per record, so this stays practical for
seeding thousands of partners/orders -- e.g. to dilute the proportion any
single pre-existing record would represent before running `odoo-bin
populate` on top of this seed data.

Usage:
    python3 populate_partner_sales.py [options]

Example (defaults match the perf_training test database):
    python3 populate_partner_sales.py \
        --url http://localhost:8069 --db perf_training \
        --username admin --password admin \
        --partner-name "Perf Test Partner" \
        --partner-count 100 --orders-per-partner 50 --confirm

Reuse an existing API key instead of minting a new one each run:
    python3 populate_partner_sales.py --api-key <key> ...
"""
import argparse
import itertools
import json
import random
import urllib.error
import urllib.request


def parse_args():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--url", default="http://localhost:8069")
    parser.add_argument("--db", default="perf_training")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default="admin")
    parser.add_argument("--api-key", default=None, help="Reuse an existing API key instead of minting one")
    parser.add_argument("--partner-name", default="Perf Test Partner", help="Base name / prefix for created partners")
    parser.add_argument("--partner-count", type=int, default=1, help="Number of distinct partners to create")
    parser.add_argument("--orders-per-partner", type=int, default=50, help="Sale orders to create per partner")
    parser.add_argument("--lines-per-order", type=int, default=3, help="Order lines per sale order")
    parser.add_argument(
        "--confirm", action="store_true",
        help="Confirm the sale orders (action_confirm) instead of leaving them as quotations",
    )
    parser.add_argument(
        "--batch-size", type=int, default=500,
        help="Max records per create()/action_confirm() call (single HTTP request)",
    )
    parser.add_argument(
        "--use-proxy", action="store_true",
        help="Honor the system HTTP(S)_PROXY env vars instead of talking to --url directly",
    )
    return parser.parse_args()


def chunked(iterable, size):
    it = iter(iterable)
    while batch := list(itertools.islice(it, size)):
        yield batch


class OdooSession:
    """Minimal client for Odoo's classic JSON-RPC (/web/...) used only to
    bootstrap an API key, and for the JSON-2 API (/json/2/<model>/<method>)
    used for all actual data operations."""

    def __init__(self, url, use_proxy=False):
        self.url = url.rstrip("/")
        self.cookies = {}
        self.api_key = None
        handlers = [] if use_proxy else [urllib.request.ProxyHandler({})]
        self.opener = urllib.request.build_opener(*handlers)

    def _post(self, path, body, headers):
        req = urllib.request.Request(
            f"{self.url}{path}", data=json.dumps(body).encode(), headers=headers, method="POST"
        )
        try:
            with self.opener.open(req) as resp:
                for header, value in resp.getheaders():
                    if header.lower() == "set-cookie":
                        k, _, rest = value.partition("=")
                        self.cookies[k] = rest.split(";", 1)[0]
                return json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            payload = exc.read().decode()
            raise RuntimeError(f"HTTP {exc.code} calling {path}: {payload}") from None

    def jsonrpc(self, path, params):
        headers = {"Content-Type": "application/json"}
        if self.cookies:
            headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in self.cookies.items())
        data = self._post(path, {"jsonrpc": "2.0", "method": "call", "params": params}, headers)
        if data.get("error"):
            raise RuntimeError(json.dumps(data["error"], indent=2))
        return data["result"]

    def call_kw(self, model, method, args, kwargs=None):
        return self.jsonrpc(
            "/web/dataset/call_kw",
            {"model": model, "method": method, "args": args, "kwargs": kwargs or {}},
        )

    def json2(self, model, method, **kwargs):
        assert self.api_key, "api_key must be set before calling json2()"
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"}
        return self._post(f"/json/2/{model}/{method}", kwargs, headers)

    def login(self, db, username, password):
        result = self.jsonrpc(
            "/web/session/authenticate", {"db": db, "login": username, "password": password}
        )
        if not result.get("uid"):
            raise SystemExit(f"Authentication failed for {username!r} on db {db!r}")
        return result["uid"]

    def mint_api_key(self, uid, password, name="perf script"):
        """Mint a fresh API key for `uid`, going through the mandatory
        identity-check flow (password re-entry), then switch this session
        over to using it for all subsequent /json/2 calls."""
        action = self.call_kw("res.users", "api_key_wizard", [[uid]])
        check_id = action["res_id"]
        self.call_kw(
            "res.users.identitycheck", "run_check", [[check_id]], {"context": {"password": password}}
        )
        descr_id = self.call_kw("res.users.apikeys.description", "create", [{"name": name}])
        show_action = self.call_kw("res.users.apikeys.description", "make_key", [[descr_id]])
        self.api_key = show_action["context"]["default_key"]
        return self.api_key


def get_or_create_partners(session, base_name, count, batch_size):
    names = [base_name] if count == 1 else [f"{base_name} {i}" for i in range(1, count + 1)]

    existing = {}
    for name_chunk in chunked(names, batch_size):
        for rec in session.json2(
            "res.partner", "search_read", domain=[["name", "in", name_chunk]], fields=["id", "name"]
        ):
            existing.setdefault(rec["name"], rec["id"])

    missing = [n for n in names if n not in existing]
    if missing:
        print(f"Creating {len(missing)} new partner(s)...")
        for name_chunk in chunked(missing, batch_size):
            vals_list = [{"name": n, "email": f"{n.lower().replace(' ', '.')}@example.com"} for n in name_chunk]
            ids = session.json2("res.partner", "create", vals_list=vals_list)
            existing.update(zip(name_chunk, ids))
    else:
        print("All target partners already exist, reusing them")

    partner_ids = [existing[n] for n in names]
    print(f"Using {len(partner_ids)} partner(s): {partner_ids[:5]}{'...' if len(partner_ids) > 5 else ''}")
    return partner_ids


def get_or_create_products(session, count=5):
    product_ids = session.json2(
        "product.product", "search", domain=[["sale_ok", "=", True]], limit=count
    )
    if product_ids:
        print(f"Reusing {len(product_ids)} existing saleable product(s)")
        return product_ids

    print("No saleable products found, creating some for the demo data")
    vals_list = [
        {
            "name": f"Perf Test Product {i}",
            "type": "service",
            "sale_ok": True,
            "list_price": round(random.uniform(10, 500), 2),
        }
        for i in range(1, count + 1)
    ]
    product_ids = session.json2("product.product", "create", vals_list=vals_list)
    print(f"Created products: {product_ids}")
    return product_ids


def make_order_vals(partner_id, product_ids, lines_per_order):
    order_lines = [
        [0, 0, {"product_id": random.choice(product_ids), "product_uom_qty": random.randint(1, 10)}]
        for _ in range(lines_per_order)
    ]
    return {"partner_id": partner_id, "order_line": order_lines}


def create_sale_orders(session, partner_ids, product_ids, orders_per_partner, lines_per_order, batch_size):
    total = len(partner_ids) * orders_per_partner
    order_vals = (
        make_order_vals(partner_id, product_ids, lines_per_order)
        for partner_id in partner_ids
        for _ in range(orders_per_partner)
    )

    order_ids = []
    for vals_chunk in chunked(order_vals, batch_size):
        order_ids.extend(session.json2("sale.order", "create", vals_list=vals_chunk))
        print(f"Created {len(order_ids)}/{total} sale orders...")
    return order_ids


def confirm_sale_orders(session, order_ids, batch_size):
    print("Confirming sale orders...")
    for i, ids_chunk in enumerate(chunked(order_ids, batch_size), 1):
        session.json2("sale.order", "action_confirm", ids=ids_chunk)
        print(f"Confirmed {min(i * batch_size, len(order_ids))}/{len(order_ids)} sale orders...")


def main():
    args = parse_args()
    session = OdooSession(args.url, use_proxy=args.use_proxy)

    uid = session.login(args.db, args.username, args.password)
    print(f"Authenticated as {args.username!r} (uid={uid}) on db {args.db!r}")

    if args.api_key:
        session.api_key = args.api_key
        print("Using provided API key")
    else:
        session.mint_api_key(uid, args.password)
        print(f"Minted API key: {session.api_key}")

    partner_ids = get_or_create_partners(session, args.partner_name, args.partner_count, args.batch_size)
    product_ids = get_or_create_products(session)

    order_ids = create_sale_orders(
        session, partner_ids, product_ids, args.orders_per_partner, args.lines_per_order, args.batch_size
    )

    if args.confirm:
        confirm_sale_orders(session, order_ids, args.batch_size)

    print(
        f"Done: {len(partner_ids)} partner(s) now have {len(order_ids)} sale order(s) total "
        f"({args.orders_per_partner} each)"
    )


if __name__ == "__main__":
    main()
