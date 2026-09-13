"""EXERCISE 2 -- write the load test of the warehouse barcode scanner.

Scenario to reproduce
---------------------
Twelve operators are picking, each of them scans a barcode roughly every
two seconds. For every single scan the mobile client makes three RPCs:

    product.product.scanner_identify(barcode)
    product.product.scanner_stock_per_location(product_id, location_id)
    product.product.scanner_last_moves(product_id, limit=5)

The second one gives the operator the breakdown per shelf: they need to
know *where* to walk, not just how many exist somewhere in the building.

Your job
--------
1. Fill in the TODOs so that one locust task = one complete scan (the
   three calls in a row, using the result of the previous one).
2. Run it:

       locust -f tools/locust_ex2_scanner.py --headless -u 12 -r 2 -t 3m

3. Produce the pgBadger report: rotate the log, run the test, then run
   pgbadger on it (setup and command in the pgBadger section of
   EXERCISES.md).
4. Do NOT start from the query durations: every single query in this run
   is under a millisecond, and sorting a pgBadger report by time will
   tell you, correctly and uselessly, that nothing is slow.

   Start from these instead:
     - locust's own median / p95, and the scans per second you ACTUALLY
       get versus the 6/s you asked for;
     - pgBadger "Overall statistics": the total number of queries;
     - divide it by the number of scans locust performed.

   Then:
     - which of the three RPCs is responsible for practically all of them?
     - what does that count depend on? It is not the number of products,
       nor the amount of stock. Find what it is.
     - rewrite that method so the query count stops depending on it --
       then check it still returns exactly the same bins as before.
       This one has a trap in it.

The solution is in exercises/02-barcode-scanner.md -- try first.
"""
import random

from locust import task, between
from OdooLocust.OdooLocustUser import OdooLocustUser

BARCODE_POOL_SIZE = 300


class WarehouseOperator(OdooLocustUser):
    wait_time = between(1, 3)

    # TODO: point this at your training database / instance
    host = "localhost"
    port = 8069
    database = "perf_advanced"
    login = "admin"
    password = "<your api key or password>"
    protocol = "json2"

    def on_start(self):
        super().on_start()
        self.product_model = self.client.get_model('product.product')
        self.warehouse_model = self.client.get_model('stock.warehouse')

        # The blueprint populates a single warehouse and hangs every shelf
        # under its stock location, so this is all the setup you need.
        warehouse = self.warehouse_model.search_read(
            domain=[], fields=['lot_stock_id'], limit=1)[0]
        self.location_id = warehouse['lot_stock_id'][0]

        products = self.product_model.search_read(
            domain=[('barcode', '!=', False)],
            fields=['barcode'],
            limit=BARCODE_POOL_SIZE,
        )
        self.barcodes = [product['barcode'] for product in products]

    @task
    def scan_one_product(self):
        barcode = random.choice(self.barcodes)

        # TODO 1: identify the product from the barcode (scanner_identify)
        # TODO 2: ask for the stock breakdown per shelf in self.location_id
        #         (scanner_stock_per_location)
        # TODO 3: ask for the last 5 moves (scanner_last_moves)
        raise NotImplementedError
