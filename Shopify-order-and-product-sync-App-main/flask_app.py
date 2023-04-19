import os
import random
import uuid
import json
import logging
import helpers
from datetime import datetime
from time import sleep as s
from shopify_client import ShopifyStoreClient, MYPOSConnectClient
from flask import Flask, redirect, request, render_template
from config import WEBHOOK_APP_UNINSTALL_URL, WEBHOOK_APP_ORDER_DONE_URL, WEBHOOK_APP_PRODUCTS_UPDATE_URL, WEBHOOK_APP_PRODUCTS_DELETE_URL, SERVER_HOST

app = Flask(__name__)
TOKEN_FILE = "shopify_token.txt"
TOKEN_FILE2 = "mypos_token.txt"
CURRENT_DIR = os.getcwd () + f"/{SERVER_HOST}"
ACCESS_TOKEN = ""
NONCE = None
ACCESS_MODE = []  # Defaults to offline access mode if left blank or omitted. https://shopify.dev/concepts/about-apis/authentication#api-access-modes
SCOPES = ['write_products','read_products','read_locations','read_inventory','read_orders','write_inventory',]  # https://shopify.dev/docs/admin-api/access-scopes


#Test hello page
@app.route('/')
def hello_world():
    return 'Hello there!'

@app.route('/app/overview', methods=['GET'])
@app.route('/app_launched', methods=['GET'])
@helpers.verify_web_call
def app_launched():
    shop = request.args.get('shop')
    global NONCE
    with open(f'{CURRENT_DIR}/{TOKEN_FILE}',"r") as token_file:
        ACCESS_TOKEN = token_file.read()
    with open(f'{CURRENT_DIR}/data/settings/settings.json',"r") as file:
        settings = json.load(file)
    if ACCESS_TOKEN:
        #shopify_client = ShopifyStoreClient(shop=shop, access_token=ACCESS_TOKEN)
        #requestNewScope = shopify_client.requestNewScope(SCOPES)
        requestNewScope = False
    if ACCESS_TOKEN and not requestNewScope and settings['firstLoad']:
        #return render_template('index.html',shop=shop)
        return render_template('index.html',shop=shop)
    if ACCESS_TOKEN and not requestNewScope:
        #return render_template('index.html',shop=shop)
        return render_template('post_install.html',shop=shop,settings=settings)

    # The NONCE is a single-use random value we send to Shopify so we know the next call from Shopify is valid (see #app_installed)
    #   https://en.wikipedia.org/wiki/Cryptographic_nonce
    NONCE = uuid.uuid4().hex
    print("NONCE Created:",NONCE)
    redirect_url = helpers.generate_install_redirect_url(shop=shop, scopes=SCOPES, nonce=NONCE, access_mode=ACCESS_MODE)
    if ACCESS_TOKEN and requestNewScope:
        return render_template('reinstall.html',redirect_url=redirect_url)
    return redirect(redirect_url, code=302)

@app.route('/app_installed', methods=['GET'])
@helpers.verify_web_call
def app_installed():
    state = request.args.get('state')
    global NONCE
    # Shopify passes our NONCE, created in #app_launched, as the `state` parameter, we need to ensure it matches!
    print("state:",state," NONCE:",NONCE)
    if state != NONCE:
        return "Invalid `state` received", 400
    NONCE = None

    # Ok, NONCE matches, we can get rid of it now (a nonce, by definition, should only be used once)
    # Using the `code` received from Shopify we can now generate an access token that is specific to the specified `shop` with the
    #   ACCESS_MODE and SCOPES we asked for in #app_installed
    shop = request.args.get('shop')
    code = request.args.get('code')
    ACCESS_TOKEN = ShopifyStoreClient.authenticate(shop=shop, code=code)
    with open(f'{CURRENT_DIR}/{TOKEN_FILE}',"w") as token_file:
        token_file.write(ACCESS_TOKEN)
    # We have an access token! Now let's register a webhook so Shopify will notify us if/when the app gets uninstalled
    # NOTE This webhook will call the #app_uninstalled function defined below
    shopify_client = ShopifyStoreClient(shop=shop, access_token=ACCESS_TOKEN)
    shopify_client.create_webook(address=WEBHOOK_APP_UNINSTALL_URL, topic="app/uninstalled")
    s(0.5)
    shopify_client.create_webook(address=WEBHOOK_APP_ORDER_DONE_URL, topic="orders/fulfilled")
    s(0.5)
    shopify_client.create_webook(address=WEBHOOK_APP_PRODUCTS_UPDATE_URL, topic="products/create")
    s(0.5)
    shopify_client.create_webook(address=WEBHOOK_APP_PRODUCTS_UPDATE_URL, topic="products/update")
    s(0.5)
    shopify_client.create_webook(address=WEBHOOK_APP_PRODUCTS_DELETE_URL, topic="products/delete")
    redirect_url = helpers.generate_post_install_redirect_url(shop=shop)
    return redirect(redirect_url, code=302)

@app.route('/app_syncOverview', methods=['POST'])
@helpers.verify_web_call
def app_syncOverview():
    return "OK!"

@app.route('/app_getSettings', methods=['POST'])
@helpers.verify_web_call
def app_getSettings():
    with open(f'{CURRENT_DIR}/data/settings/settings.json',"r") as file:
        settings = json.load(file)
    return json.dumps(settings)

@app.route('/app_changeSettings', methods=['POST'])
@helpers.verify_web_call
def app_changeSettings(params = {}):
    if params:
        data = params
    else :
        data = request.form
    with open(f'{CURRENT_DIR}/data/settings/settings.json',"r") as file:
        settings = json.load(file)
    if 'turnSyncOn' in data:
        settings['turnSyncOn'] = json.loads(data['turnSyncOn'])
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

@app.route('/app_loadProducts', methods=['POST'])
@helpers.verify_web_call
def app_loadProducts():
    data = request.form
    shop = data['shop']
    with open(f'{CURRENT_DIR}/{TOKEN_FILE}',"r") as token_file:
        ACCESS_TOKEN = token_file.read()
    shopify_client = ShopifyStoreClient(shop=shop, access_token=ACCESS_TOKEN)
    settings = json.loads(app_getSettings())
    if settings['loadActive']:
        loadedProducts = shopify_client.count_loaded_products()
        with open(f'{CURRENT_DIR}/data/products/count.json',"r") as file:
            countJson = json.load(file)
        productsInTotal = countJson['count']
        loadStatus = {'loadedProducts':loadedProducts,'productsInTotal':productsInTotal}
        return json.dumps(loadStatus)
    else :
        with open(f'{CURRENT_DIR}/data/settings/settings.json',"r") as file:
            settings = json.load(file)

        settings['loadActive'] = True
        with open(f'{CURRENT_DIR}/data/settings/settings.json',"w") as file:
            json.dump(settings,file,indent=3)

        shopify_client.load_all_products()
        s(0.5)
        loadedProducts = shopify_client.count_loaded_products()
        productsInTotal = shopify_client.get_products_count()
        countJson = {'count':productsInTotal}
        with open(f'{CURRENT_DIR}/data/products/count.json',"w") as file:
            json.dump(countJson,file,indent=3)
        s(0.5)
        loadStatus = {'loadedProducts':loadedProducts,'productsInTotal':productsInTotal}
        return json.dumps(loadStatus)

@app.route('/app_syncProducts', methods=['POST'])
@helpers.verify_web_call
def app_syncProducts():
    data = request.form
    shop = data['shop']
    date_format = "%m-%d-%Y %H:%M:%S"
    with open(f'{CURRENT_DIR}/{TOKEN_FILE2}',"r") as token_file:
        try:
            MYPOS_TOKEN = json.load(token_file)
        except:
            MYPOS_TOKEN = {}

    if MYPOS_TOKEN:
        bearerToken = MYPOS_TOKEN['bearerToken']
        time_fore = datetime.strptime(MYPOS_TOKEN['lastLoginTime'],date_format)
        time_now = datetime.now()
        diff = time_now - time_fore
        days = diff.days
        days_to_hours = days * 24
        diff_btw_two_times = (diff.seconds) / 3600
        overall_hours = days_to_hours + diff_btw_two_times
        if overall_hours > 1:
            with open(f'{CURRENT_DIR}/{TOKEN_FILE2}',"w") as token_file:
                MYPOS_TOKEN = {}
                bearerToken = MYPOSConnectClient.authenticate()
                MYPOS_TOKEN['bearerToken'] = bearerToken
                MYPOS_TOKEN['lastLoginTime'] = time_now.strftime(date_format)
                json.dump(MYPOS_TOKEN,token_file)
    else:
        with open(f'{CURRENT_DIR}/{TOKEN_FILE2}',"w") as token_file:
            MYPOS_TOKEN = {}
            time_now = datetime.now()
            bearerToken = MYPOSConnectClient.authenticate()
            MYPOS_TOKEN['bearerToken'] = bearerToken
            MYPOS_TOKEN['lastLoginTime'] = time_now.strftime(date_format)
            json.dump(MYPOS_TOKEN,token_file)


    with open(f'{CURRENT_DIR}/{TOKEN_FILE}',"r") as token_file:
        ACCESS_TOKEN = token_file.read()
    shopify_client = ShopifyStoreClient(shop=shop, access_token=ACCESS_TOKEN)
    mypos_client = MYPOSConnectClient(bearerToken)
    settings = json.loads(app_getSettings())
    if settings['syncActive']:
        s(0.5)
        syncedProducts = shopify_client.count_synced_products()
        productsInTotal = shopify_client.get_products_count()
        syncStatus = {'syncedProducts':syncedProducts,'productsInTotal':productsInTotal}
        return json.dumps(syncStatus)
    else :
        shopify_client.sync_products(mypos_client)
        syncedProducts = shopify_client.count_synced_products()
        productsInTotal = shopify_client.get_products_count()
        syncStatus = {'syncedProducts':syncedProducts,'productsInTotal':productsInTotal}
        return json.dumps(syncStatus)

@app.route('/products_update', methods=['POST'])
@helpers.verify_webhook_call
def products_update():
    shop = request.args.get('shop')
    product = request.json
    with open(f'{CURRENT_DIR}/{TOKEN_FILE}',"r") as token_file:
        ACCESS_TOKEN = token_file.read()
    shopify_client = ShopifyStoreClient(shop=shop, access_token=ACCESS_TOKEN)
    print("Into product update", product)
    file1 = open("./logs.txt","w")
    file1.write("Hello \n")

    shopify_client.load_product(product)
    return "OK"

@app.route('/products_delete', methods=['POST'])
@helpers.verify_webhook_call
def products_delete():
    shop = request.args.get('shop')
    product = request.json
    with open(f'{CURRENT_DIR}/{TOKEN_FILE}',"r") as token_file:
        ACCESS_TOKEN = token_file.read()
    shopify_client = ShopifyStoreClient(shop=shop, access_token=ACCESS_TOKEN)
    shopify_client.delete_product(product)
    return "OK"

@app.route('/order_fullfilled', methods=['POST'])
@helpers.verify_webhook_call
def order_fullfilled():
    customerJson = {}
    bearerToken = MYPOSConnectClient.authenticate()
    mypos_client = MYPOSConnectClient(bearerToken)

    #Add customer
    customerJson['firstName'] = request.json['customer']['first_name']
    customerJson['lastName'] = request.json['customer']['last_name']
    customerJson['address'] = None
    customerJson['city'] = None
    customerJson['region'] = None
    customerJson['postalCode'] = None
    customerJson['country'] = None
    customerJson['phoneNumber'] = None
    customerJson['emailAddress'] = None
    customerJson['active'] = True
    customerJson['specificPrices'] = []

    customer = mypos_client.create_customer(payload=customerJson)


    #print(request.json)
    #print("Into product fullfilment", product)
    file1 = open("logs.txt","w")
    file1.write("Hellooooo \n")

    payload = {"items":[]}
    line_items = request.json['line_items']

    #Same for all items
    creationDate = request.json['created_at'][:-6]+'.00'
    OrderId = request.json['order_number']
    SessionId = uuid.uuid4().hex
    sessionCode = 'SY-' + creationDate[:10]

    # Check for tax lines in parent wrapper
    if 'tax_lines' in request.json:
        if request.json['tax_lines']:
            TaxHead = request.json['tax_lines'][0]
            Tax = TaxHead
        else:
            TaxHead = None
    else:
        Tax = None

    #Specific for all items
    for item in line_items:
        s(0.5)
        #MYPOS_check1, MYPOS_check2 = False, False
        SKU = item['sku']
        mypos = mypos_client.get_product(productCode=SKU)
        if mypos:

            # Check for tax lines in item wrapper
            if not TaxHead:
                if item['tax_lines']:
                    Tax = item['tax_lines'][0]
                else:
                    Tax = {'price':0,'rate':0}
            TaxValue = Tax['price']
            TaxRate = Tax['rate']*100
            Price = item['price']
            Quantity = item['quantity']
            load = {}
            load['creationUser'] = "Taj Test"
            load['creationDate'] = creationDate
            load['creationDevice'] = "Shopify MYPOS Connector App"
            load['effectiveDate'] = creationDate
            load['sessionId'] = SessionId
            load['sessionCode'] = sessionCode
            load['itemDescription'] = mypos['longDescription']
            load['itemShortDescription'] = mypos['shortDescription']
            load['promotionCode'] = ""
            load['rewardPoints'] = None

            load['itemPrice'] = float(Price)
            load['itemValue'] = float(Price)
            load['itemCurValue'] = float(Price)
            load['overrideValue'] = None

            load['reasonCodeType'] = ""
            load['isTransferred'] = True
            load['transferDate'] = creationDate
            load['posted'] = 'X'
            load['printed'] = 1

            load['taxRate'] = float(TaxRate)
            load['taxValue'] = float(TaxValue)
            load['taxCode'] = f'{int(TaxRate)}%'
            load['isTaxable'] = item['taxable']

            load['commissionValue'] = 0.00000
            load['commissionType'] = None
            load['bacsId'] = None
            load['paymentAttempts'] = None
            load['currencyCode'] = "GBP"
            load['itemCode'] = SKU
            load['productId'] = mypos['productId']
            load['quantity'] = Quantity
            load['stockQuantity'] = None
            load['stockAdjustmentId'] = None
            load['printSort'] = 0
            load['modifierGroup'] = ""
            load['cardTransactionInfo01'] = None
            load['cardTransactionInfo02'] = None
            load['linkedPurchaseOrderItemId'] = None
            load['itemSubType'] = None
            load['linkedSaleItemId'] = "00000000-0000-0000-0000-000000000000"


            load['cC_001'] = ""
            load['cC_002'] = ""
            load['cC_003'] = ""
            load['cC_004'] = ""
            load['cC_005'] = ""
            load['cC_006'] = None
            load['cC_007'] = None
            load['cC_008'] = None
            load['cC_009'] = None
            load['cC_010'] = None

            load['receiptId'] = ''
            load['receiptCode'] = ''
            load['itemType'] = 'P'

            payload["items"].append(load)

            #Add out-balancing item
            load = {}
            load['creationUser'] = "Taj Test"
            load['creationDate'] = creationDate
            load['creationDevice'] = "Shopify MYPOS Connector App"
            load['effectiveDate'] = creationDate
            load['sessionId'] = SessionId
            load['sessionCode'] = sessionCode
            load['itemDescription'] = "Payment made on Shopify"
            load['itemShortDescription'] = "Payment Shopify"
            load['promotionCode'] = ""
            load['rewardPoints'] = None

            load['itemPrice'] = -float(Price)
            load['itemValue'] = -float(Price)
            load['itemCurValue'] = -float(Price)
            load['overrideValue'] = None

            load['reasonCodeType'] = ""
            load['isTransferred'] = True
            load['transferDate'] = creationDate
            load['posted'] = 'X'
            load['printed'] = 1

            load['taxRate'] = float(TaxRate)
            load['taxValue'] = float(TaxValue)
            load['taxCode'] = f'{int(TaxRate)}%'
            load['isTaxable'] = item['taxable']

            load['commissionValue'] = 0.00000
            load['commissionType'] = None
            load['bacsId'] = None
            load['paymentAttempts'] = None
            load['currencyCode'] = "GBP"
            load['itemCode'] = "Shopify"
            load['quantity'] = Quantity
            load['stockQuantity'] = None
            load['stockAdjustmentId'] = None
            load['printSort'] = 0
            load['modifierGroup'] = ""
            load['cardTransactionInfo01'] = None
            load['cardTransactionInfo02'] = None
            load['linkedPurchaseOrderItemId'] = None
            load['itemSubType'] = None
            load['linkedSaleItemId'] = "00000000-0000-0000-0000-000000000000"


            load['cC_001'] = ""
            load['cC_002'] = ""
            load['cC_003'] = ""
            load['cC_004'] = ""
            load['cC_005'] = ""
            load['cC_006'] = None
            load['cC_007'] = None
            load['cC_008'] = None
            load['cC_009'] = None
            load['cC_010'] = None

            load['receiptId'] = ''
            load['receiptCode'] = ''
            load['itemType'] = 'R'

            payload["items"].append(load)

        else:
            print("Not in MYPOS")

    for i in range(5):
        s(0.5)
        customerId = customer['customerId']
        receiptId = uuid.uuid4().hex
        XX = random.randint(10, 99)
        receiptCode = f'SY{XX}-{OrderId}'
        line_items = payload["items"]
        for item in line_items:
            item['customerId'] = customerId
            item['receiptId'] = receiptId
            item['receiptCode'] = receiptCode

        saleitem = mypos_client.create_saleitem(payload=payload)#If response, break else try again max 5 times with new numbers
        if saleitem:
            logging.info(f'saleitem:{saleitem}')
            break
    webhook_topic = request.headers.get('X-Shopify-Topic')
    webhook_payload = request.get_json()
    logging.info(f"webhook call received {webhook_topic}:\n{json.dumps(webhook_payload, indent=3)}")
    return "OK"

@app.route('/app_uninstalled', methods=['POST'])
@helpers.verify_webhook_call
def app_uninstalled():
    # https://shopify.dev/docs/admin-api/rest/reference/events/webhook?api[version]=2020-10
    # Someone uninstalled your app, clean up anything you need to
    # NOTE the shop ACCESS_TOKEN is now void!
    ACCESS_TOKEN = ""
    with open(f'{CURRENT_DIR}/{TOKEN_FILE}',"w") as token_file:
        token_file.write(ACCESS_TOKEN)

    webhook_topic = request.headers.get('X-Shopify-Topic')
    webhook_payload = request.get_json()
    logging.error(f"webhook call received {webhook_topic}:\n{json.dumps(webhook_payload, indent=3)}")

    return "OK"

@app.route('/data_removal_request', methods=['POST'])
@helpers.verify_webhook_call
def data_removal_request():
    # https://shopify.dev/tutorials/add-gdpr-webhooks-to-your-app
    # Clear all personal information you may have stored about the specified shop
    return "OK"

if __name__ == "__main__":
    app.run(debug=True)