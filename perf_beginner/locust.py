import random

from locust import task, between
from OdooLocust.OdooLocustUser import OdooLocustUser

PARTNER_LIST_SIZE = 80
PARTNER_LIST_FIELDS = ['display_name', 'email', 'phone', 'country_id']


class Seller(OdooLocustUser):
    wait_time = between(0.1, 3)
    host = "localhost"
    database = "perf_training_final_2"
    login = "admin"
    password = "e557901ef72d8817507098c6e9acf84a0cbe53e3"
    port = 8069
    protocol = "json2"

    def on_start(self):
        super().on_start()
        self.partner_count = self.client.get_model('res.partner').search_count(domain=[])

    @task(5)
    def create_so(self):
        prod_model = self.client.get_model('product.product')
        cust_model = self.client.get_model('res.partner')
        so_model = self.client.get_model('sale.order')

        cust_id = cust_model.search([], limit=1)[0]
        prod_ids = prod_model.search([])

        order_ids = so_model.create({
            'partner_id': cust_id,
            'order_line': [(0, 0, {'product_id': prod_ids[0],
                                   'product_uom_qty': 1}),
                           (0, 0, {'product_id': prod_ids[1],
                                   'product_uom_qty': 2}),
                          ]
        })
        so_model.action_confirm(order_ids)

    @task(3)
    def view_partner_total_amount_on_so(self):
        cust_model = self.client.get_model('res.partner')

        # list view of 80 partners, taken at a random page
        offset = random.randint(0, max(self.partner_count - PARTNER_LIST_SIZE, 0))
        partners = cust_model.search_read(domain=[],
                                          fields=PARTNER_LIST_FIELDS,
                                          offset=offset,
                                          limit=PARTNER_LIST_SIZE)
        if not partners:
            return

        # open one of them and read the computed total
        partner_id = random.choice(partners)['id']
        cust_model.read(ids=[partner_id], fields=['total_amount_on_so'])
