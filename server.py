import sys
from twisted.python import log
from twisted.internet import reactor
import base64
import finnhub
from autobahn.twisted.websocket import WebSocketServerProtocol, WebSocketServerFactory, listenWS
from threading import Thread
import yfinance as yf
import concurrent.futures
import asyncio
from datetime import timezone
import datetime
import json
import random
from pymongo import MongoClient
import bson.json_util as json_util
from bson.objectid import ObjectId
import os
from google.cloud import pubsub_v1

# CONFIG VARIABLES (CUSTOMIZATION IS NEEDED)
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = 'ADDRESS-OF-YOUR-GCP-KEY.JSON-FILE'
MONGOURI = "YOUR-MONGODB-URI"
client = MongoClient(MONGOURI)
db = client["YOUR-MONGO-DB-NAME"]
sym_list = ["AAPL", "AMZN", "F", "WBD", "AMD",
            "NVDA", "BABA", "GOOGL", "T", "TSLA"]
PUBSUB_PRICE = 'YOUR-PUBSUB-NAME'
subscription_id = f'{PUBSUB_PRICE}-sub-{random.randint(0,10000)}'
GOOGLE_PROJECT_ID = 'YOUR-GOOGLE-PROJECT-ID'
ws_url = f"ws://127.0.0.1:9000"
FINNHUB_API_KEY = "YOUR-FINNHUB-KEY"
t_sleep = 15
t_diff = 21


class TradeAppServerProtocol(WebSocketServerProtocol):
    def __init__(self):
        super().__init__()
        self.userid = ""

    def pricesub(self, x):
        try:
            if x["action"] == "subscribe":
                self.factory.subscribe_on_price(self)
            elif x["action"] == "unsubscribe":
                self.factory.unsubscribe_on_price(self)
            return {'result': price, 'message': 'successful', 'kind': 'prices'}
        except Exception as e:
            return {'message': 'failed', 'kind': 'prices'}

    def usersdb(self, x):
        col_name = x["resource"]
        trade_col = db[col_name]
        if x["action"] == "post":
            res = trade_col.insert_one(x["payload"])
            if res.acknowledged:
                self.userid = res.inserted_id
                return {"result": res.inserted_id, "message": "Ok."}
            else:
                return {"message": "Error in POST."}
        elif x["action"] == "get":
            ob_id = list(x["payload"].items())
            key = ob_id[0][0]
            value = ob_id[0][1]
            if key == "_id":
                if value == "all":
                    res = list(trade_col.find())
                    for i in range(len(res)):
                        user_basket_result = self.basketsdb({"action": "get", "resource": "baskets", "payload": {
                                                            "userId": str(res[i]["_id"])}})['result']
                        res_share_value = 0
                        for st_bas in user_basket_result:
                            res_share_value += st_bas["amount"] * \
                                st_bas["orderPrice"]
                        if "balance" not in res[i]:
                            res[i]["balance"] = 0
                        res_total_value = res_share_value + res[i]["balance"]
                        res[i]['shareValue'] = res_share_value
                        res[i]['totalValue'] = res_total_value
                else:
                    self.userid = value
                    res = list(trade_col.find({'_id': ObjectId(value)}))
                    user_basket_result = self.basketsdb(
                        {"action": "get", "resource": "baskets", "payload": {"userId": value}})['result']
                    res_share_value = 0
                    for st_bas in user_basket_result:
                        res_share_value += st_bas["amount"] * \
                            st_bas["orderPrice"]
                    res_total_value = res_share_value + res[0]["balance"]
                    res[0]['shareValue'] = res_share_value
                    res[0]['totalValue'] = res_total_value
            else:
                res = list(trade_col.find({key: value}))
            return {"result": res, "message": "Ok."}
        elif x["action"] == "patch":
            ob_id = x["payload"]["_id"]
            del x["payload"]["_id"]
            res = trade_col.update_one({'_id': ObjectId(ob_id)}, {
                                       "$set": x["payload"]}, upsert=False)
            if res.acknowledged:
                user_data = self.usersdb(
                    {"action": "get", "resource": "users", "payload": {"_id": ob_id}})["result"]
                return {"result": user_data, "message": "Ok."}
            else:
                return {"message": "Error in PATCH."}
        else:
            return {"message": "Error, invalid action."}

    def basketsdb(self, x):
        col_name = x["resource"]
        trade_col = db[col_name]
        if x["action"] == "post":
            res = trade_col.insert_one(x["payload"])
            if res.acknowledged:
                user_data = self.usersdb({"action": "get", "resource": "users", "payload": {
                                         "_id": x["payload"]["userId"]}})["result"]
                user_basket_result = self.basketsdb(
                    {"action": "get", "resource": "baskets", "payload": {"userId": x["payload"]["userId"]}})
                res_share_value = 0
                for st_bas in user_basket_result['result']:
                    res_share_value += st_bas["amount"]*st_bas["orderPrice"]
                res_total_value = res_share_value + user_data[0]["balance"]
                user_data = self.usersdb({"action": "patch", "resource": "users", "payload": {
                                         "_id": x["payload"]["userId"], "shareValue": res_share_value, "totalValue": res_total_value}})
                return {"result": res.inserted_id, "message": "Ok."}
            else:
                return {"message": "Error in POST."}
        elif x["action"] == "get":
            ob_id = list(x["payload"].items())
            key = ob_id[0][0]
            value = ob_id[0][1]
            updating = 0
            if key == "_id":
                if value == "all":
                    res = list(trade_col.find())
                else:
                    res = list(trade_col.find({'_id': ObjectId(value)}))
                    updating = 1
            else:
                res = list(trade_col.find({key: value}))
                updating = 1
            if updating == 1:
                if price == []:
                    new_prices = self.factory.mainPriceProvider()
                else:
                    new_prices = price
                for bas in res:
                    for prc in new_prices:
                        if bas["stockName"] == prc["sym"]:
                            bas["orderPrice"] = prc["price"]
            return {"result": res, "message": "Ok."}
        elif x["action"] == "patch":
            ob_id = x["payload"]["_id"]
            del x["payload"]["_id"]
            if x["payload"]["amount"] == 0:
                res = trade_col.delete_one({'_id': ObjectId(ob_id)})
            else:
                res = trade_col.update_one({'_id': ObjectId(ob_id)}, {
                                           "$set": x["payload"]}, upsert=False)
            if res.acknowledged:
                user_data = self.usersdb({"action": "get", "resource": "users", "payload": {
                                         "_id": x["payload"]["userId"]}})["result"]
                user_basket_result = self.basketsdb(
                    {"action": "get", "resource": "baskets", "payload": {"userId": x["payload"]["userId"]}})
                res_share_value = 0
                for st_bas in user_basket_result['result']:
                    res_share_value += st_bas["amount"]*st_bas["orderPrice"]
                res_total_value = res_share_value + user_data[0]["balance"]
                user_data = self.usersdb({"action": "patch", "resource": "users", "payload": {
                                         "_id": x["payload"]["userId"], "shareValue": res_share_value, "totalValue": res_total_value}})
                return {"result": ob_id, "message": "Ok."}
            else:
                return {"message": "Error in PATCH."}
        else:
            return {"message": "Error, invalid action."}

    def cardsdb(self, x):
        col_name = x["resource"]
        trade_col = db[col_name]
        if x["action"] == "post":
            res = trade_col.insert_one(x["payload"])
            if res.acknowledged:
                return {"result": res.inserted_id, "message": "Ok."}
            else:
                return {"message": "Error in POST."}
        elif x["action"] == "get":
            ob_id = list(x["payload"].items())
            key = ob_id[0][0]
            value = ob_id[0][1]
            if key == "_id":
                if value == "all":
                    res = list(trade_col.find())
                else:
                    res = list(trade_col.find({'_id': ObjectId(value)}))
            else:
                res = list(trade_col.find({key: value}))
            return {"result": res, "message": "Ok."}
        elif x["action"] == "patch":
            ob_id = x["payload"]["_id"]
            del x["payload"]["_id"]
            res = trade_col.update_one({'_id': ObjectId(ob_id)}, {
                                       "$set": x["payload"]}, upsert=False)
            if res.acknowledged:
                return {"result": ob_id, "message": "Ok."}
            else:
                return {"message": "Error in PATCH."}
        else:
            return {"message": "Error, invalid action."}

    def transactionsdb(self, x):
        col_name = x["resource"]
        trade_col = db[col_name]
        if x["action"] == "post":
            card_data = self.cardsdb({"action": "get", "resource": "cards", "payload": {
                                     "cardNumber": x["payload"]["cardNumber"]}})["result"]
            user_data = self.usersdb({"action": "get", "resource": "users", "payload": {
                                     "_id": x["payload"]["userId"]}})["result"]
            if x["payload"]["amount"] > 0:
                if x["payload"]["amount"] > card_data[0]["balance"]:
                    return {"message": "Invalid amount."}
            if x["payload"]["amount"] < 0:
                if -x["payload"]["amount"] > user_data[0]["balance"]:
                    return {"message": "Invalid amount."}
            card_update_result = self.cardsdb({"action": "patch", "resource": "cards", "payload": {
                                              "_id": card_data[0]["_id"], "balance": card_data[0]["balance"]-x["payload"]["amount"]}})
            user_update_result = self.usersdb({"action": "patch", "resource": "users", "payload": {
                                              "_id": user_data[0]["_id"], "balance": user_data[0]["balance"]+x["payload"]["amount"]}})
            res = trade_col.insert_one(x["payload"])
            if res.acknowledged:
                return {"result": res.inserted_id, "message": "Ok."}
            else:
                return {"message": "Error in POST."}
        elif x["action"] == "get":
            ob_id = list(x["payload"].items())
            key = ob_id[0][0]
            value = ob_id[0][1]
            if key == "_id":
                if value == "all":
                    res = list(trade_col.find())
                else:
                    res = list(trade_col.find({'_id': ObjectId(value)}))
            else:
                res = list(trade_col.find({key: value}))
            return {"result": res, "message": "Ok."}
        else:
            return {"message": "Error, invalid action."}

    def ordersdb(self, x):
        col_name = x["resource"]
        trade_col = db[col_name]
        if x["action"] == "post":
            user_data = self.usersdb({"action": "get", "resource": "users", "payload": {
                                     "_id": x["payload"]["userId"]}})["result"]
            ttl_val = x["payload"]["amount"]*x["payload"]["orderPrice"]
            if x["payload"]["type"] == "buy":
                if user_data[0]["balance"] < ttl_val:
                    return {"message": "Invalid amount."}
                user_update_result = self.usersdb({"action": "patch", "resource": "users", "payload": {
                                                  "_id": user_data[0]["_id"], "balance": user_data[0]["balance"]-(x["payload"]["amount"]*x["payload"]["orderPrice"])}})
                x["payload"]["status"] = "closed"
                user_basket_result = self.basketsdb(
                    {"action": "get", "resource": "baskets", "payload": {"userId": x["payload"]["userId"]}})
                print(user_basket_result)
                selected_stock = "None"
                for st_bas in user_basket_result['result']:
                    if st_bas["stockName"] == x["payload"]["stockName"]:
                        selected_stock = st_bas
                if selected_stock == "None":
                    basket_post_result = self.basketsdb({"action": "post", "resource": "baskets", "payload": {
                                                        "stockName": x["payload"]["stockName"], "amount": x["payload"]["amount"], "orderPrice": x["payload"]["orderPrice"], "userId": x["payload"]["userId"], "WACC": x["payload"]["orderPrice"]}})
                else:
                    basket_patch_result = self.basketsdb({"action": "patch", "resource": "baskets", "payload": {"_id": selected_stock["_id"], "amount": x["payload"]["amount"]+selected_stock["amount"], "orderPrice": x["payload"]["orderPrice"], "userId": x["payload"]["userId"], "WACC": (
                        ((x["payload"]["orderPrice"]*x["payload"]["amount"])+(selected_stock["amount"]*selected_stock["WACC"]))/(x["payload"]["amount"]+selected_stock["amount"]))}})
            elif x["payload"]["type"] == "sell":
                user_update_result = self.usersdb({"action": "patch", "resource": "users", "payload": {
                                                  "_id": user_data[0]["_id"], "balance": user_data[0]["balance"]+(x["payload"]["amount"]*x["payload"]["orderPrice"])}})
                x["payload"]["status"] = "closed"
                user_basket_result = self.basketsdb(
                    {"action": "get", "resource": "baskets", "payload": {"userId": x["payload"]["userId"]}})
                selected_stock = "None"
                for st_bas in user_basket_result['result']:
                    if st_bas["stockName"] == x["payload"]["stockName"]:
                        selected_stock = st_bas
                if selected_stock == "None":
                    return {"message": "Stock not available in the basket."}
                else:
                    basket_patch_result = self.basketsdb({"action": "patch", "resource": "baskets", "payload": {"_id": selected_stock["_id"], "amount": selected_stock[
                                                         "amount"]-x["payload"]["amount"], "orderPrice": selected_stock["orderPrice"], "userId": x["payload"]["userId"], "WACC": selected_stock["WACC"]}})
            else:
                return {"message": "Invalid order type."}
            res = trade_col.insert_one(x["payload"])
            if res.acknowledged:
                return {"result": res.inserted_id, "message": "Ok."}
            else:
                return {"message": "Error in POST."}
        elif x["action"] == "get":
            ob_id = list(x["payload"].items())
            key = ob_id[0][0]
            value = ob_id[0][1]
            if key == "_id":
                if value == "all":
                    res = list(trade_col.find())
                else:
                    res = list(trade_col.find({'_id': ObjectId(value)}))
            else:
                res = list(trade_col.find({key: value}))
            return {"result": res, "message": "Ok."}
        elif x["action"] == "patch":
            ob_id = x["payload"]["_id"]
            del x["payload"]["_id"]
            res = trade_col.update_one({'_id': ObjectId(ob_id)}, {
                                       "$set": x["payload"]}, upsert=False)
            if res.acknowledged:
                return {"result": ob_id, "message": "Ok."}
            else:
                return {"message": "Error in PATCH."}
        else:
            return {"message": "Error, invalid action."}

    def ranksdb(self, x):
        if x["action"] == "get":
            res = self.usersdb(
                {"action": "get", "resource": "users", "payload": {"_id": "all"}})["result"]
            res = [x for x in res if "totalValue" in x.keys()]
            res = sorted(res, key=lambda d: d['totalValue'], reverse=True)
            return {"result": res, "message": "Ok."}
        else:
            return {"message": "Error, invalid action."}

    def chartsdb(self, x):
        if x["action"] == "get":
            tickerSymbol = x["payload"]["stockName"]
            tickerData = yf.Ticker(tickerSymbol)
            tickerDf = tickerData.history(
                interval='5m', start=x["payload"]["start"], end=x["payload"]["end"])
            tickerDfClose = tickerDf.Close.to_json()
            return {"result": tickerDfClose, "stockName": tickerSymbol, "message": "Ok."}
        else:
            return {"message": "Error, invalid action."}

    def onMessage(self, payload, isBinary):
        print(payload)
        if not isBinary:
            x = json.loads(payload.decode('utf8'))
            try:
                col_name = x["resource"]
                if col_name == "users":
                    res = self.usersdb(x)
                elif col_name == "baskets":
                    res = self.basketsdb(x)
                elif col_name == "cards":
                    res = self.cardsdb(x)
                elif col_name == "transactions":
                    res = self.transactionsdb(x)
                elif col_name == "orders":
                    res = self.ordersdb(x)
                elif col_name == 'prices':
                    res = self.pricesub(x)
                elif col_name == 'ranks':
                    res = self.ranksdb(x)
                elif col_name == 'charts':
                    res = self.chartsdb(x)
                else:
                    res = {"message": "Error, invalid resource."}
                res["kind"] = col_name
            except Exception as e:
                self.sendClose(1000, "Exception raised: {0}".format(e))
            else:
                self.sendMessage(json_util.dumps(res).encode('utf8'))
        else:
            res = {"message": "unspported req."}
            self.sendMessage(json_util.dumps(res).encode('utf8'))

    def onOpen(self):
        print("Client connecting: ")
        self.factory.register(self)
        res = {"message": "Connected."}
        self.sendMessage(json_util.dumps(res).encode('utf8'))

    def onClose(self, wasClean, code, reason):
        print("WebSocket connection closed: {0}".format(reason))


class TradeAppServerFactory(WebSocketServerFactory):
    def __init__(self, url):
        WebSocketServerFactory.__init__(self, url)
        self.clients = []
        self.price_subscribers = []

        global price
        price = []
        # print("calling broadcast ...")
        t = Thread(target=self.start_background_loop, args=(
            self.broadcast_price_every_2_sec(),), daemon=True)

        global latest_stock_price_data
        latest_stock_price_data = None
        t.start()
        t = Thread(target=self.start_background_loop,
                   args=(self.pullPubsub(),), daemon=True)
        t.start()

    def pushPubsub(self,price):
        # Instantiates a Pub/Sub client
        publisher = pubsub_v1.PublisherClient()
        topic_path = publisher.topic_path(GOOGLE_PROJECT_ID, PUBSUB_PRICE)
        current_timestamp = datetime.datetime.now(timezone.utc).timestamp()
        message_json = json.dumps(
            {'data': {'price': price, 'timestamp': current_timestamp}})
        message_bytes = message_json.encode('utf-8')
        # Publishes a message
        try:
            publish_future = publisher.publish(topic_path, data=message_bytes)
            publish_future.result()  # Verify the publish succeeded
            return 'Message published.'
        except Exception as e:
            return (e, 500)


    def priceDecoder(self,event, context):
        event_data = event['data']
        try:
            event_data = base64.b64decode(event_data).decode('utf-8')
        except Exception as e:
            pass
        stock_price_data = json.loads(event_data)['data']
        return stock_price_data


    async def pullPubsub(self):
        # Number of seconds the subscriber should listen for messages
        # timeout = 100000
        subscriber = pubsub_v1.SubscriberClient()
        subscription_path = subscriber.subscription_path(
            GOOGLE_PROJECT_ID, subscription_id)
        topic_path = subscriber.topic_path(GOOGLE_PROJECT_ID, PUBSUB_PRICE)
        # NUM_MESSAGES = 10000

        def callback(message: pubsub_v1.subscriber.message.Message) -> None:
            global latest_stock_price_data
            data_str = message.data.decode("utf-8")
            data_dict = json.loads(data_str)
            attributes_dict = dict(message.attributes)
            message_dict = {'data': json.dumps(
                data_dict), 'attributes': attributes_dict}
            stock_price_data = self.priceDecoder(message_dict, None)
            if latest_stock_price_data:
                if stock_price_data['timestamp'] > latest_stock_price_data['timestamp']:
                    latest_stock_price_data = stock_price_data
            else:
                latest_stock_price_data = stock_price_data
            with subscriber:
                subscription = subscriber.create_subscription(
                    request={
                        "name": subscription_path,
                        "topic": topic_path,
                    }
                )
                streaming_pull_future = subscriber.subscribe(
                    subscription_path, callback=callback)
                # Wrap subscriber in a 'with' block to automatically call close() when done.
                # with subscriber:
                try:
                    # When `timeout` is not set, result() will block indefinitely,
                    # unless an exception is encountered first.
                    streaming_pull_future.result()
                except Exception as e:
                    print('Exception:', e)



    def onlinePrice(self,symbol):
        try:
            finnhub_client = finnhub.Client(
                api_key=FINNHUB_API_KEY)
            current_price = finnhub_client.quote(symbol)["c"]
            return (current_price, None, None, symbol)
        except Exception as e:
            return (None, None, None, None)


    def getMultiplePrices(self):
        result = []
        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = {executor.submit(self.onlinePrice, sym): sym for sym in sym_list}
            for future in concurrent.futures.as_completed(futures):
                rmp, sn, pr, sym = future.result()
                if rmp:
                    result.append({"sym": sym, "price": rmp})
        return result


    def mainPriceProvider(self):
        global latest_stock_price_data
        if latest_stock_price_data:
            current_timestamp = datetime.datetime.now(timezone.utc).timestamp()
            if latest_stock_price_data['timestamp'] > current_timestamp - t_diff:
                return latest_stock_price_data['price']
        self.pushPubsub([])
        api_price = self.getMultiplePrices()
        if len(api_price) == len(sym_list):
            self.pushPubsub(api_price)
        return api_price

    @staticmethod
    def start_background_loop(fn) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        task = loop.create_task(fn)
        try:
            loop.run_until_complete(task)
        except asyncio.CancelledError:
            pass

    def register(self, client):
        if client not in self.clients:
            print("registered client {}".format(client.peer))
            self.clients.append(client)

    def unregister(self, client):
        if client in self.clients:
            print("unregistered client {}".format(client.peer))
            self.clients.remove(client)
            self.price_subscribers.remove(client)

    def broadcast(self, msg):
        for c in self.clients:
            c.sendMessage(msg.encode('utf-8'))

    def subscribe_on_price(self, client):
        if client not in self.price_subscribers:
            print("subscribe client on price {}".format(client.peer))
            self.price_subscribers.append(client)
            # self.broadcast_price({"message":"hey!"})

    def unsubscribe_on_price(self, client):
        if client in self.price_subscribers:
            print("unsubscribe client on price {}".format(client.peer))
            self.price_subscribers.remove(client)

    async def broadcast_price(self, msg):
        from twisted.internet import reactor
        for c in self.price_subscribers:
            try:
                reactor.callFromThread(
                    c.sendMessage, json_util.dumps(msg).encode('utf8'))
            except Exception as e:
                print("Exception raised: {0}".format(e))

    async def broadcast_price_every_2_sec(self):
        while True:
            global price
            price = self.mainPriceProvider()
            print(price)
            await self.broadcast_price({"result": price, "kind": "prices", "message": "Ok."})
            await asyncio.sleep(t_sleep)


if __name__ == '__main__':
    log.startLogging(sys.stdout)
    factory = TradeAppServerFactory(ws_url)
    factory.protocol = TradeAppServerProtocol
    factory.setProtocolOptions(
        allowedOrigins="*"
    )
    listenWS(factory)
    reactor.run()
