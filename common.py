import configparser
import logging
import math
from datetime import datetime, timedelta
import tweepy
from binance.client import Client

from database import get_islong

BUSD = 'BUSD'
USDT = 'USDT'
OPEN_ORDER_LOG = "{0} - You already have a {2} order of {1}."
HAVE_ASSET_LOG = "You already purchased these assets: {0}"
MIN_USD = 12
MIN_AMOUNT_EXCEPTION_LOG = "{0} - Buy amount cannot be less than {2} USDT! {1} buy order is invalid and won't submit."
START_LOG = "{0} - TraderBot has started. Running for {1}"
CANCEL_ORDER_LOG = "{0} - Latest {2} order of {1} has been cancelled."
PROCESS_TIME_LOG = "This order has been processed in {} seconds."
UP = 'UP'
DOWN = 'DOWN'
config = configparser.ConfigParser()
config.read('BinanceBot.properties')
API_KEY = config.get('BinanceSignIn', 'apikey')
API_SECRET_KEY = config.get('BinanceSignIn', 'apisecretkey')
client = Client(api_key=API_KEY, api_secret=API_SECRET_KEY)
logging.basicConfig(level=logging.INFO)


# Truncates the given value.
def truncate(number, decimals):
    if not isinstance(decimals, int):
        raise TypeError("decimal places must be an integer.")
    elif decimals < 0:
        raise ValueError("decimal places has to be 0 or more.")
    elif decimals == 0:
        return math.trunc(number)

    factor = 10.0 ** decimals
    return math.trunc(number * factor) / factor


# Sets decimal values based on selected asset.
def decimal_place(asset):
    info = client.get_symbol_info(asset)
    min_price = str(info['filters'][0]['minPrice'])
    min_qty = str(info['filters'][2]['minQty'])
    start = '0.'
    end = '1'
    truncate_price = len(min_price[min_price.find(start) + len(start):min_price.rfind(end)]) + 1
    if min_qty.startswith('1.00'):
        truncate_qty = 0
    else:
        truncate_qty = len(min_qty[min_qty.find(start) + len(start):min_qty.rfind(end)]) + 1

    return truncate_price, truncate_qty


# Retrieves last 2000 of price movements.
def price_action(symbol, interval):
    first_set = client.get_klines(symbol=symbol, interval=interval, limit=1000)
    timestamp = first_set[0][0]
    timestampsec = datetime.fromtimestamp(timestamp / 1e3) - timedelta(hours=1)
    timestampsec = int(datetime.timestamp(timestampsec))
    exp = len(str(timestamp)) - len(str(timestampsec))
    timestampsec *= pow(10, exp)
    second_set = client.get_klines(symbol=symbol, interval=interval, limit=1000,endTime=timestampsec)
    joined_list = [*second_set, *first_set]
    return joined_list


# Fetches account's balance from Binance wallet.
def wallet(asset):
    if asset != BUSD:
        data = client.get_asset_balance(asset=asset.replace(BUSD, ""))
        return float(data['free']) + float(data['locked'])
    else:
        data = client.get_asset_balance(asset=asset)
        return float(data['free'])


# Checks if user has purchased the asset.
def position_control(asset):
    info = client.get_symbol_info(asset)
    min_qty = float(info['filters'][2]['minQty'])
    return True if wallet(asset=asset) > min_qty else False


# Checks if an order is already submitted.
def open_order_control(asset, order_side):
    position = client.get_open_orders(symbol=asset)
    if len(position) == 0:
        return False
    elif len(position) > 0:
        for x in position:
            if x['side'] == order_side:
                return True
            else:
                return False


# Cancels given order.
def cancel_order(asset, order_side):
    now = datetime.now().replace(microsecond=0)
    orders = client.get_open_orders(symbol=asset)
    order_id = orders[-1]['orderId']
    client.cancel_order(symbol=asset, orderId=order_id)
    logging.info(CANCEL_ORDER_LOG.format(now, asset, order_side))
    tweet(status=CANCEL_ORDER_LOG.format(now, asset, order_side))


# Sets amount of purchasing dynamically.
def usd_alloc(asset_list):
    priceDec, qtyDec = decimal_place(asset=BUSD + USDT)
    divider = 0
    for x in asset_list:
        has_asset = get_islong(x)
        has_order = open_order_control(asset=x, order_side=Client.SIDE_BUY)
        if not has_asset and not has_order:
            divider += 1
    return truncate(wallet(BUSD) / divider, priceDec) if divider > 0 else truncate(wallet(BUSD), priceDec)


# Sends tweet.
def tweet(status):
    auth = tweepy.OAuthHandler(config.get('TwitterAPI', 'consumer_key'),
                               config.get('TwitterAPI', 'consumer_secret_key'))
    auth.set_access_token(config.get('TwitterAPI', 'access_token'), config.get('TwitterAPI', 'access_secret_token'))
    twitter = tweepy.API(auth)
    twitter.update_status(status)
