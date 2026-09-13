from locust import task, between
from OdooLocust.OdooLocustUser import OdooLocustUser


class Seller(OdooLocustUser):
    wait_time = between(0.1, 3)
    host = "localhost"
    database = "perf_training_final_2"
    login = "admin"
    password = "e557901ef72d8817507098c6e9acf84a0cbe53e3"
    port = 8069
    protocol = "json2"

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
