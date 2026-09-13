"""EXERCISE 1 -- write the load test of the customer portal.

Scenario to reproduce
---------------------
A marketing e-mail went out this morning with a "track my order" link.
Customers land on the portal and:

  * type their reference in the search box; the widget is debounced, so
    one RPC per ~300ms of typing, with a growing prefix of the reference
    ("CR", "CR-1", "CR-12", ...) -- weight 6.
    Keep the short prefixes: how many characters the customer has typed
    changes the query plan, and that is half of this exercise.
  * browse a page of their orders, sorted by customer reference -- weight 3
  * open one order to look at the details -- weight 1

Server side these are:

    sale.order.portal_find_by_reference(reference)
    sale.order.portal_recent_orders(offset, limit)
    sale.order.read(ids, fields)

Your job
--------
1. Fill in the TODOs below so that the script runs.
2. Start it against the training database and keep it running a few minutes:

       locust -f tools/locust_ex1_portal.py --headless -u 20 -r 2 -t 3m

3. While it runs, PostgreSQL logs every statement (see the pgBadger
   section of EXERCISES.md for the postgresql.conf settings).
   Build the report afterwards with pgbadger -- see the pgBadger
   section of EXERCISES.md for the settings and the command.
4. Answer, with numbers from the report:
     - which query spends the most time in total?
     - how many times is it executed, and how long does one execution take?
     - what does EXPLAIN (ANALYZE, BUFFERS) say about it?
     - time the search for 2, 4, 5 and 10 characters typed. The numbers
       are not monotonic -- explain the shape.
     - what would you change in perf_advanced/models/sale_order.py?
       (the answer is not only "add an index")

The solution is in exercises/01-customer-portal.md -- try first.
"""
import random
import string

from locust import task, between
from OdooLocust.OdooLocustUser import OdooLocustUser

ORDERS_PER_PAGE = 80


class PortalCustomer(OdooLocustUser):
    wait_time = between(0.3, 2)

    # TODO: point this at your training database / instance
    host = "localhost"
    port = 8069
    database = "perf_advanced"
    login = "admin"
    password = "b36030ee8079c96987bb0d4d27d6fa39d6b589e5"
    protocol = "json2"

    def on_start(self):
        super().on_start()
        self.so_model = self.client.get_model('sale.order')
        # A pool of real references, so the searches actually match something.
        # TODO: read ~200 existing customer_reference values here and keep them
        #       on `self.references`. Use search_read with a limit.
        self.references = [r['customer_reference'] for r in self.so_model.search_read(
            domain=[('state', 'in', ('sale', 'done'))],
            fields=['customer_reference'],
            limit=200
        )]
        # self.references = []
        self.order_count = self.so_model.search_count(domain=[('state', 'in', ('sale', 'done'))])

    def _partial_reference(self):
        """Return the prefix a customer would have typed so far."""
        if self.references and random.random() < 0.8:
            reference = random.choice(self.references)
            return reference[:random.randint(2, len(reference))]
        return ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))

    @task(6)
    def search_box_keystroke(self):
        # TODO: call portal_find_by_reference with self._partial_reference()
        self.so_model.portal_find_by_reference(self._partial_reference())

    @task(3)
    def browse_my_orders(self):
        # TODO: call portal_recent_orders on a random page
        #       (offset between 0 and order_count - ORDERS_PER_PAGE)
        offset = random.randint(0, max(0, self.order_count - ORDERS_PER_PAGE))
        self.so_model.portal_recent_orders(limit=ORDERS_PER_PAGE, offset=offset)

    @task(1)
    def open_one_order(self):
        # TODO: pick one order id and read
        #       ['name', 'customer_reference', 'amount_total', 'partner_id']
        order_id = random.randint(1, self.order_count)
        self.so_model.read([order_id], ['name', 'customer_reference', 'amount_total', 'partner_id'])
