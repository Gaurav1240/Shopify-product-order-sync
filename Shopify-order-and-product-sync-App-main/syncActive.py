import json
import os
from shopify_client import ShopifyStoreClient, MYPOSConnectClient
from config import SERVER_HOST
shop = "teststore.myshopify.com/"
TOKEN_FILE = "shopify_token.txt"

CURRENT_DIR = os.getcwd () + f"/{SERVER_HOST}"
bearerToken = MYPOSConnectClient.authenticate()
mypos_client = MYPOSConnectClient(bearerToken)

with open(f'{CURRENT_DIR}/{TOKEN_FILE}',"r") as token_file:
    ACCESS_TOKEN = token_file.read()

if ACCESS_TOKEN:

    def app_getSettings():
        with open(f'{CURRENT_DIR}/data/settings/settings.json',"r") as file:
            settings = json.load(file)
        return json.dumps(settings)

    def app_changeSettings(params = {}):
        if params:
            data = params
        with open(f'{CURRENT_DIR}/data/settings/settings.json',"r") as file:
            settings = json.load(file)
        if 'syncActive' in data:
            settings['syncActive'] = json.loads(data['syncActive'])
        if 'loadActive' in data:
            settings['loadActive'] = json.loads(data['loadActive'])
        if 'firstSync' in data:
            settings['firstSync'] = json.loads(data['firstSync'])
        if 'firstLoad' in data:
            settings['firstLoad'] = json.loads(data['firstLoad'])

        with open(f'{CURRENT_DIR}/data/settings/settings.json',"w") as file:
            json.dump(settings,file,indent=3)
        return json.dumps(settings)





    shopify_client = ShopifyStoreClient(shop=shop, access_token=ACCESS_TOKEN)
    settings = json.loads(app_getSettings())
    if settings['syncActive']:
        syncedProducts = shopify_client.count_synced_products()
        productsInTotal = shopify_client.get_products_count()
        syncStatus = {'syncedProducts':syncedProducts,'productsInTotal':productsInTotal}
        print (json.dumps(syncStatus))
    elif settings['turnSyncOn'] :
        shopify_client.sync_products(mypos_client)
