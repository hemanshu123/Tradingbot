from packages.helpers import get_products, get_product_by_symbol, place_order, get_product_id_by_symbol
from packages.placeorder import buy, sell
from pprint import pprint


id = get_product_id_by_symbol("HUSD")
pprint(id)  


pprint(sell(product_id=id, size=1))
