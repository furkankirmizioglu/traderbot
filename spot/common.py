import os
from logging import basicConfig, INFO, info
from math import trunc
from datetime import datetime
import tweepy
from binance.client import Client
from firebase_admin import messaging, credentials, initialize_app
import constants
import database
from smtplib import SMTP

path = os.path.dirname(__file__)
firebase = path + "/data/firebase.json"
firebase_cred = credentials.Certificate(firebase)
firebase_app = initialize_app(firebase_cred)

client = Client(api_key=constants.API_KEY, api_secret=constants.API_SECRET_KEY)
basicConfig(level=INFO)


def Now():
    return datetime.now().strftime('%d/%m/%Y %H:%M:%S')


# Truncates the given value.
def truncate(number, decimals):
    if not isinstance(decimals, int):
        raise TypeError("decimal places must be an integer.")
    elif decimals < 0:
        raise ValueError("decimal places has to be 0 or more.")
    elif decimals == 0:
        return trunc(number)

    factor = 10.0 ** decimals
    return trunc(number * factor) / factor


# Sets decimal values based on selected asset.
def decimal_place(asset):
    symbolInfo = client.get_symbol_info(asset)
    min_price = str(symbolInfo['filters'][0]['minPrice'])
    min_qty = str(symbolInfo['filters'][2]['minQty'])
    start = '0.'
    end = '1'
    truncate_price = len(min_price[min_price.find(start) + len(start):min_price.rfind(end)]) + 1
    if min_qty.startswith('1.00'):
        truncate_qty = 0
    else:
        truncate_qty = len(min_qty[min_qty.find(start) + len(start):min_qty.rfind(end)]) + 1

    return truncate_price, truncate_qty


# Retrieves last 1000 of price movements.
def priceActions(symbol, interval):
    first_set = client.get_klines(symbol=symbol, interval=interval, limit=1000)
    return first_set


# Fetches account's balance from Binance wallet.
def wallet(asset):
    if asset != constants.BUSD:
        data = client.get_asset_balance(asset=asset.replace(constants.BUSD, ""))
        return float(data['free']) + float(data['locked'])
    else:
        data = client.get_asset_balance(asset=asset)
        return float(data['free'])


def getMinimumQuantity(asset):
    qty_info = client.get_symbol_info(asset)
    min_qty = float(qty_info['filters'][2]['minQty'])
    return min_qty


# Checks if user has purchased the asset.
def checkPosition(asset):
    min_qty = database.getMinimumQuantity(asset=asset)
    if wallet(asset=asset) > min_qty:
        database.setIsLong(asset=asset, isLong=True)
        return True
    else:
        database.setIsLong(asset=asset, isLong=False)
        return False


# Checks if an order is already submitted.
def checkOpenOrder(asset):
    openOrdersList = client.get_open_orders(symbol=asset)
    if len(openOrdersList) == 0:
        database.setHasBuyOrder(asset=asset, hasBuyOrder=False)
        database.setHasSellOrder(asset=asset, hasSellOrder=False)
        return False, False
    elif len(openOrdersList) > 0:
        for x in openOrdersList:
            if x['side'] == constants.SIDE_BUY:
                database.setHasBuyOrder(asset=asset, hasBuyOrder=True)
                database.setHasSellOrder(asset=asset, hasSellOrder=False)
                return True, False
            elif x['side'] == constants.SIDE_SELL:
                database.setHasBuyOrder(asset=asset, hasBuyOrder=False)
                database.setHasSellOrder(asset=asset, hasSellOrder=True)
                return False, True


# Cancels given order.
def cancelOrder(asset, order_side):
    order_id = database.getLatestOrder(pair=asset)
    client.cancel_order(symbol=asset, orderId=order_id)
    database.removeOrderLog(orderId=order_id)
    log = constants.CANCEL_ORDER_LOG.format(Now(), asset, order_side.upper())
    info(log)
    notifier(logText=constants.NOTIFIER_CANCEL_ORDER_LOG.format(order_side.lower(), asset))
    tweet(status=log)


# Sets amount of purchasing dynamically.
def USD_ALLOCATOR(pairList):
    priceDec, qtyDec = database.getDecimalValues(asset=constants.BUSD + constants.USDT)
    divider = 0
    for x in pairList:
        has_asset = database.getIsLong(x)
        has_order = database.getHasBuyOrder(asset=x)
        if not has_asset and not has_order:
            divider += 1
    return truncate(wallet(constants.BUSD) / divider, priceDec) if divider > 0 else truncate(wallet(constants.BUSD),
                                                                                             priceDec)


def initializer(pairList):
    database.initDB(asset=constants.BUSD + constants.USDT)
    for pair in pairList:
        database.initDB(asset=pair)


def mailSender(exceptionMessage):
    try:
        smtpConn = SMTP('smtp.gmail.com', 587)
        smtpConn.starttls()
        smtpConn.login(constants.SENDER_EMAIL, constants.EMAIL_PASSWORD)
        exceptionMessage = constants.EMAIL_FORMAT.format(constants.EMAIL_SUBJECT, exceptionMessage)
        smtpConn.sendmail(constants.SENDER_EMAIL, constants.RECEIVER_EMAIL, exceptionMessage)
        smtpConn.quit()
    except Exception as ex:
        info(ex)
        pass


# Sends tweet.
def tweet(status):
    auth = tweepy.OAuthHandler(constants.TWITTER_API_KEY, constants.TWITTER_API_SECRET_KEY)
    auth.set_access_token(constants.TWITTER_ACCESS_TOKEN, constants.TWITTER_ACCESS_SECRET_TOKEN)
    twitter = tweepy.API(auth)
    twitter.update_status(status)


def notifier(logText):
    # See documentation on defining a message payload.
    notification = messaging.Notification(
        title=constants.NOTIFIER_TITLE,
        body=logText
    )
    message = messaging.Message(
        token=constants.FIREBASE_DEVICE_KEY,
        notification=notification
    )
    # Send a message to the device corresponding to the provided
    # registration token.
    messaging.send(message)
