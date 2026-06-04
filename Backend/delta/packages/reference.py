from helpers import get_products, get_product_by_symbol, place_order, get_product_id_by_symbol
from pprint import pprint
from placeorder import buy, sell


id = get_product_id_by_symbol("HUSD")
pprint(id)  


pprint(sell(product_id=id, size=1))
