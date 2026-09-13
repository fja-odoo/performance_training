{
    'name': "Performance Advanced",
    'summary': """
        Advanced performance training: load testing, pgBadger, EXPLAIN and speedscope
    """,
    'description': """
Five hands-on exercises about performance analysis on Odoo 19.

  1. Sales portal rush        -- locust + pgBadger + missing index
  2. Shop floor barcode storm -- locust + pgBadger + N+1 over RPC
  3. Manufacturing order      -- speedscope + ORM batching
  4. Customer aging balance   -- speedscope + EXPLAIN + partial index
  5. POS session closing      -- speedscope + pure Python algorithmics

The module ships the *slow* implementation on purpose. Solutions live in
exercises/, one markdown file per exercise, not in the code.
    """,
    'version': '1.0',
    'author': "Odoo S.A.",
    'category': 'Tools',
    'depends': [
        'sale_management',
        'stock',
        'account',
        'mrp',
        'point_of_sale',
    ],
    'data': [
        'security/ir.access.csv',
        'views/perf_advanced_views.xml',
        'views/sale_order_views.xml',
        'views/res_partner_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'OEEL-1',
}
