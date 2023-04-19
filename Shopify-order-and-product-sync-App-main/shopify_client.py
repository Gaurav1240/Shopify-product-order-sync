import random
import pytz
import os
import math
import json
import logging
from time import sleep as s
from typing import List
from datetime import datetime

import requests
from requests.exceptions import HTTPError

from config import SHOPIFY_SECRET, SHOPIFY_API_KEY, MYPOS_USER, MYPOS_PASS, MYPOS_SERVER, SERVER_HOST

CURRENT_DIR = os.getcwd () + f"/{SERVER_HOST}"

SHOPIFY_API_VERSION = "2020-10"

REQUEST_METHODS = {
    "GET": requests.get,
    "POST": requests.post,
    "PUT": requests.put,
    "DEL": requests.delete
}

#set the date and time format
date_format = "%m-%d-%Y %H:%M:%S"

class ShopifyStoreClient():

    def __init__(self, shop: str, access_token: str):
        self.shop = shop
        self.base_url = f"https://{shop}/admin/api/{SHOPIFY_API_VERSION}/"
        self.oauth_url = f"https://{shop}/admin/oauth/"
        self.access_token = access_token

    @staticmethod
    def authenticate(shop: str, code: str) -> str:
        url = f"https://{shop}/admin/oauth/access_token"
        payload = {
            "client_id": SHOPIFY_API_KEY,
            "client_secret": SHOPIFY_SECRET,
            "code": code
        }
        try:
            response = requests.post(url, json=payload)
            response.raise_for_status()
            return response.json()['access_token']
        except HTTPError as ex:
            logging.exception(ex)
            return None

    def get_timezone(self,headers: dict = {}) -> str:
        call_path = "shop.json"
        url = f"{self.oauth_url}{call_path}"
        method = 'GET'
        request_func = REQUEST_METHODS[method]
        headers['X-Shopify-Access-Token'] = self.access_token
        timezone_response = self.authenticated_shopify_call(call_path=call_path, method=method)
        if not timezone_response:
                return None
        return timezone_response['shop']['iana_timezone']

    def authenticated_shopify_call(self, call_path: str, method: str, params: dict = None, payload: dict = None, headers: dict = {}) -> dict:
        url = f"{self.base_url}{call_path}"
        request_func = REQUEST_METHODS[method]
        headers['X-Shopify-Access-Token'] = self.access_token
        try:
            response = request_func(url, params=params, json=payload, headers=headers)
            response.raise_for_status()
            logging.debug(f"authenticated_shopify_call response:\n{json.dumps(response.json(), indent=4)}")
            return response.json()
        except HTTPError as ex:
            logging.exception(ex)
            return None

    def response_shopify_call(self, call_path: str, method: str, params: dict = None, payload: dict = None, headers: dict = {}) -> dict:
        url = f"{self.base_url}{call_path}"
        request_func = REQUEST_METHODS[method]
        headers['X-Shopify-Access-Token'] = self.access_token
        try:
            response = request_func(url, params=params, json=payload, headers=headers)
            response.raise_for_status()
            logging.debug(f"authenticated_shopify_call response:\n{json.dumps(response.json(), indent=4)}")
            return response
        except HTTPError as ex:
            logging.exception(ex)
            return None

    def get_access_scopes(self,headers: dict = {}):
        call_path = "access_scopes.json"
        url = f"{self.oauth_url}{call_path}"
        method = 'GET'
        request_func = REQUEST_METHODS[method]
        headers['X-Shopify-Access-Token'] = self.access_token
        try:
            access_scopes_response = request_func(url,headers=headers)
            access_scopes_response.raise_for_status()
            logging.debug(f"get access scopes response:\n{json.dumps(access_scopes_response.json(), indent=4)}")
            scopes = access_scopes_response.json()['access_scopes']
            return [scope['handle'] for scope in scopes]
        except HTTPError as ex:
            logging.exception(ex)
            return None

    def requestNewScope(self,new_access_scopes):
        old_access_scopes = self.get_access_scopes()
        requestNewScope = len([scope for scope in new_access_scopes if scope not in old_access_scopes])>0
        return requestNewScope

    def get_shop(self) -> dict:
        call_path = 'shop.json'
        method = 'GET'
        shop_response = self.authenticated_shopify_call(call_path=call_path, method=method)
        if not shop_response:
            return None
        # The myshopify_domain value is the one we'll need to listen to via webhooks to determine an uninstall
        return shop_response['shop']

    def get_mypos_collection(self):
        params = {'title':'MYPOS','fields':'id,rules'}
        smart_collections = self.get_smart_collections(params)
        if not smart_collections:
            return None
        elif len(smart_collections) == 1:
            rules = smart_collections[0]['rules']
            if rules == [{"column": "tag","relation": "equals","condition": "mypos"}]:
                return smart_collections[0]['id']
        else:
            return None

    def get_inventory_levels(self,params = None) -> dict:
        call_path = 'inventory_levels.json'
        method = 'GET'
        inventory_levels_response = self.authenticated_shopify_call(call_path=call_path, params=params, method=method)
        if not inventory_levels_response:
            return None
        return inventory_levels_response['inventory_levels']

    def post_inventory_level(self, payload: dict = {}, params = None) -> dict:
        call_path = 'inventory_levels/set.json'
        method = 'POST'
        inventory_levels_response = self.authenticated_shopify_call(call_path=call_path, params=params, method=method, payload=payload)
        if not inventory_levels_response:
                return None
        return len(payload)

    def post_inventory_levels(self, payloads: list = [], params = None) -> dict:
        call_path = 'inventory_levels/set.json'
        method = 'POST'
        print('Updating',len(payloads),'levels... Expecting',len(payloads),'sec to complete')
        for payload in payloads:
            s(0.5)
            inventory_levels_response = self.authenticated_shopify_call(call_path=call_path, params=params, method=method, payload=payload)
            if not inventory_levels_response:
                return None
        return len(payloads)

    def delete_product(self,product):
        path = f"{CURRENT_DIR}/data/products/"
        fileName = f"{product['id']}"
        productFile = os.path.isfile(f"{path}{fileName}.json")
        os.remove(f"{path}{fileName}.json")

    def load_product(self,product):
        variants = product['variants']
        path = f"{CURRENT_DIR}/data/products/"
        fileName = f"{product['id']}"
        productFile = os.path.isfile(f"{path}{fileName}.json")
        productJson = {product['id']:variants}

        with open(f"{path}{fileName}.json","w") as file:
            json.dump(productJson,file,indent=3)

    def count_loaded_products(self):
        path = f"{CURRENT_DIR}/data/products"
        files = os.listdir(f'{path}')
        return len(files)

    def count_synced_products(self):
        path = f"{CURRENT_DIR}/data/status"
        files = os.listdir(f'{path}')
        return len(files)

    def load_all_products(self,pageSize=250):
        #timezone = self.get_timezone()

        Previous = ' rel="previous"'
        Next = ' rel="next"'

        productsTotal = self.get_products_count()
        pagesTotal = math.ceil(productsTotal/pageSize)
        call_path = 'products.json'

        for i in range(pagesTotal):
            s(0.5)
            response = self.response_shopify_call(call_path=call_path,method='GET',params={'limit':pageSize})
            print(response.headers)
            if 'Link' in response.headers:
                linkHeaders = response.headers['Link']
                pageLinks = linkHeaders.replace(';',',').replace('<','').replace('>','').split(',')
            else:
                break

            products = response.json()['products']

            for product in products:
                self.load_product(product)

            if Next in pageLinks:
                NextPage = pageLinks[pageLinks.index(Next)-1]
                cutPosition = NextPage.find('products.json')
                call_path = NextPage[cutPosition:]
            else:
                NextPage = ''
                break
        with open(f'{CURRENT_DIR}/data/settings/settings.json',"r") as file:
            settings = json.load(file)

        settings['firstLoad'] = True
        settings['loadActive'] = False
        with open(f'{CURRENT_DIR}/data/settings/settings.json',"w") as file:
            json.dump(settings,file,indent=3)

    def sync_products(self,mypos_client):
        with open(f'{CURRENT_DIR}/data/settings/settings.json',"r") as file:
            settings = json.load(file)

        settings['syncActive'] = True
        with open(f'{CURRENT_DIR}/data/settings/settings.json',"w") as file:
            json.dump(settings,file,indent=3)

        load_path = f"{CURRENT_DIR}/data/products"
        save_path = f"{CURRENT_DIR}/data/status"

        files = os.listdir(f'{load_path}.')
        for file in files:
            with open(f'{load_path}/{file}',"r") as f:
                productJson = json.load(f)
                productId = file.replace('.json','')
                variants = productJson[productId]
                for variant in variants:
                    s(0.5)
                    if variant['sku']:
                        quantity = mypos_client.get_stock(productCode=variant['sku'])
                        print("quantity:",quantity)
                        if type(quantity) == int or type(quantity) == float:
                            params = {'inventory_item_ids':variant['inventory_item_id']}
                            inventory_levels = self.get_inventory_levels(params=params)
                            inventory_level = inventory_levels[0]
                            inventory_level['available'] = int(quantity)
                            self.post_inventory_level(payload = inventory_level)
                            variant['error'] = False
                            variant['warning'] = False
                            variant['message'] = "Synced"
                        else:
                            variant['error'] = True
                            variant['warning'] = False
                            variant['message'] = "Product stock not found in MYPOS"
                    else:
                        variant['error'] = False
                        variant['warning'] = True
                        variant['messsage'] = "SKU is not defined"

                with open(f'{save_path}/{file}',"w") as file:
                    json.dump(productJson,file,indent=3)

        with open(f'{CURRENT_DIR}/data/settings/settings.json',"r") as file:
            settings = json.load(file)

        settings['syncActive'] = False
        with open(f'{CURRENT_DIR}/data/settings/settings.json',"w") as file:
            json.dump(settings,file,indent=3)

        return "OK"
    def get_products_count(self):
        call_path = f'products/count.json'
        method = 'GET'
        products_count_response = self.authenticated_shopify_call(call_path=call_path, method=method)
        if not products_count_response:
            return None
        return products_count_response['count']

    def get_products(self,params = None) -> dict:
        call_path = 'products.json'
        method = 'GET'
        products_response = self.authenticated_shopify_call(call_path=call_path, params=params, method=method)
        if not products_response:
            return None
        return products_response['products']

    def get_smart_collections(self,params = None) -> dict:
        call_path = 'smart_collections.json'
        method = 'GET'
        smart_collections_response = self.authenticated_shopify_call(call_path=call_path, params=params, method=method)
        if not smart_collections_response:
            return None
        return smart_collections_response['smart_collections']

    def get_product(self,product_id,params = None) -> dict:
        call_path = f'products/{product_id}.json'
        method = 'GET'
        product_response = self.authenticated_shopify_call(call_path=call_path, params=params, method=method)
        if not product_response:
            return None
        return product_response['product']

    def create_product(self,product_id,params = None, payload: dict = {}) -> dict:
        call_path = f'products.json'
        method = 'POST'
        product_response = self.authenticated_shopify_call(call_path=call_path, params=params, method=method, payload=payload)
        if not product_response:
            return None
        return product_response['product']

    def get_smart_collection(self, smart_collection_id, params = None) -> dict:
        call_path = 'smart_collections/{smart_collection_id}.json'
        method = 'GET'
        smart_collection_response = self.authenticated_shopify_call(call_path=call_path, params=params, method=method)
        if not smart_collection_response:
            return None
        return smart_collection_response['smart_collection']


    def get_script_tags(self) -> List:
        call_path = 'script_tags.json'
        method = 'GET'
        script_tags_response = self.authenticated_shopify_call(call_path=call_path, method=method)
        if not script_tags_response:
            return None
        return script_tags_response['script_tags']

    def get_script_tag(self, id: int) -> dict:
        call_path = f'script_tags/{id}.json'
        method = 'GET'
        script_tag_response = self.authenticated_shopify_call(call_path=call_path, method=method)
        if not script_tag_response:
            return None
        return script_tag_response['script_tag']

    def update_script_tag(self, id: int, src: str, display_scope: str = None) -> bool:
        call_path = f'script_tags/{id}.json'
        method = 'PUT'
        payload = {"script_tag": {"id": id, "src": src}}
        if display_scope:
            payload['script_tag']['display_scope'] = display_scope
        script_tags_response = self.authenticated_shopify_call(call_path=call_path, method=method, payload=payload)
        if not script_tags_response:
            return None
        return script_tags_response['script_tag']

    def create_script_tag(self, src: str, event: str = 'onload', display_scope: str = None) -> int:
        call_path = f'script_tags.json'
        method = 'POST'
        payload = {'script_tag': {'event': event, 'src': src}}
        if display_scope:
            payload['script_tag']['display_scope'] = display_scope
        script_tag_response = self.authenticated_shopify_call(call_path=call_path, method=method, payload=payload)
        if not script_tag_response:
            return None
        return script_tag_response['script_tag']

    def delete_script_tag(self, script_tag_id: int) -> int:
        call_path = f'script_tags/{script_tag_id}.json'
        method = 'DEL'
        script_tag_response = self.authenticated_shopify_call(call_path=call_path, method=method)
        if script_tag_response is None:
            return False
        return True

    def create_usage_charge(self, recurring_application_charge_id: int, description: str, price: float) -> dict:
        call_path = f'recurring_application_charges/{recurring_application_charge_id}/usage_charges.json'
        method = 'POST'
        payload = {'usage_charge': {'description': description, 'price': price}}
        usage_charge_response = self.authenticated_shopify_call(call_path=call_path, method=method, payload=payload)
        if not usage_charge_response:
            return None
        return usage_charge_response['usage_charge']

    def get_recurring_application_charges(self) -> List:
        call_path = 'recurring_application_charges.json'
        method = 'GET'
        recurring_application_charges_response = self.authenticated_shopify_call(call_path=call_path, method=method)
        if not recurring_application_charges_response:
            return None
        return recurring_application_charges_response['recurring_application_charges']

    def delete_recurring_application_charges(self, recurring_application_charge_id: int) -> bool:
        # Broken currently,authenticated_shopify_call expects JSON but this returns nothing
        call_path = f'recurring_application_charges/{recurring_application_charge_id}.json'
        method = 'DEL'
        delete_recurring_application_charge_response = self.authenticated_shopify_call(call_path=call_path, method=method)
        if delete_recurring_application_charge_response is None:
            return False
        return True

    def activate_recurring_application_charge(self, recurring_application_charge_id: int) -> dict:
        call_path = f'recurring_application_charges/{recurring_application_charge_id}/activate.json'
        method = 'POST'
        payload = {}
        recurring_application_charge_activation_response = self.authenticated_shopify_call(call_path=call_path, method=method, payload=payload)
        if not recurring_application_charge_activation_response:
            return None
        return recurring_application_charge_activation_response['recurring_application_charge']

    def create_webook(self, address: str, topic: str) -> dict:
        call_path = f'webhooks.json'
        method = 'POST'
        payload = {
            "webhook": {
                "topic": topic,
                "address": address,
                "format": "json"
            }
        }
        webhook_response = self.authenticated_shopify_call(call_path=call_path, method=method, payload=payload)
        if not webhook_response:
            return None
        return webhook_response['webhook']

    def get_webhooks_count(self, topic: str):
        call_path = f'webhooks/count.json?topic={topic}'
        method = 'GET'
        webhook_count_response = self.authenticated_shopify_call(call_path=call_path, method=method)
        if not webhook_count_response:
            return None
        return webhook_count_response['count']

class MYPOSConnectClient():

    def __init__(self, access_token: str):
        self.base_url = f"https://{MYPOS_SERVER}"
        self.access_token = access_token

    @staticmethod
    def authenticate():
        url = f"https://{MYPOS_USER}:{MYPOS_PASS}@{MYPOS_SERVER}auth/token"
        try:
            response = requests.post(url)
            response.raise_for_status()
            return response.json()['bearerToken']
        except HTTPError as ex:
            logging.exception(ex)
            return None

    def authenticated_mypos_call(self, call_path: str, method: str, params: dict = None, payload: dict = None, headers: dict = {}) -> dict:
        url = f"{self.base_url}{call_path}"
        request_func = REQUEST_METHODS[method]
        headers['Authorization'] =  'Bearer ' + self.access_token
        if call_path == "saleitems":
            try:
                response = request_func(url, params=params, json=payload, headers=headers)
                print('Response Body: ',response.content)
                response.raise_for_status()
                #logging.debug(f"authenticated_mypos_call response:\n{json.dumps(response.json(), indent=4)}")
                if response.status_code == 200 or response.status_code == 202:
                    return payload["items"][0]['receiptId']
                else:
                    return None
            except HTTPError as ex:
                logging.exception(ex)
                return None
        else:
            try:
                response = request_func(url, params=params, json=payload, headers=headers)
                response.raise_for_status()
                logging.debug(f"authenticated_mypos_call response:\n{json.dumps(response.json(), indent=4)}")
                return response.json()
            except HTTPError as ex:
                logging.exception(ex)
                return None


    def get_product(self, productCode, params: dict = None) -> dict:
        call_path = f'products/{productCode}'
        method = 'GET'
        product_response = self.authenticated_mypos_call(call_path=call_path, method=method, params=params)
        if not product_response:
            return None
        return product_response

    def get_products(self, params: dict = None) -> dict:
        call_path = f'products'
        method = 'GET'
        products_response = self.authenticated_mypos_call(call_path=call_path, method=method, params=params)
        if not products_response:
            return None
        return products_response

    def get_stock(self, productCode, params: dict = None, payload: dict = None, headers={}) -> dict:
        product_response = {}
        stock_name ="EARLY LEARNING CENTRE TEST"
        call_path = f"products/{productCode}"
        url = f"{self.base_url}{call_path}"
        headers['Authorization'] =  'Bearer ' + self.access_token
        response = requests.get(url, headers=headers)
        if response.status_code == 200 or response.status_code == 202:
            product_response = response.json()
        if not product_response:
            return None
        if product_response['storeStocks']:
            if stock_name:
                for stock in product_response['storeStocks']:
                     if stock['name'] == stock_name:
                         return stock['quantity']
        return None


    def get_saleitem(self, identifier, params: dict = None) -> dict:
        call_path = f'saleitems/{identifier}'
        method = 'GET'
        saleitem_response = self.authenticated_mypos_call(call_path=call_path, method=method, params=params)
        if not saleitem_response:
            return None
        return saleitem_response

    def get_saleitems(self, params: dict = None) -> dict:
        call_path = 'saleitems/receipts'
        method = 'GET'
        saleitems_response = self.authenticated_mypos_call(call_path=call_path, method=method, params=params)
        if not saleitems_response:
            return None
        return saleitems_response

    def create_saleitem(self, params: dict = None, payload: dict = None) -> dict:
        call_path = 'saleitems'
        method = 'POST'
        saleitem_response = self.authenticated_mypos_call(call_path=call_path, method=method, params=params, payload=payload)
        if not saleitem_response:
            return None
        return saleitem_response

    def create_customer(self, params: dict = None, payload: dict = None) -> dict:
        call_path = 'customers'
        method = 'POST'
        customer_response = self.authenticated_mypos_call(call_path=call_path, method=method, params=params, payload=payload)
        if not customer_response:
            return None
        return customer_response

    def update_product(self, productCode, params: dict = None, payload: dict = None) -> dict:
        call_path = f'products/{productCode}'
        method = 'PUT'
        product_response = self.authenticated_mypos_call(call_path=call_path, method=method, params=params, payload=payload)
        if not product_response:
            return None
        return product_response['products']

