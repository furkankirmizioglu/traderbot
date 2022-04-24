from binance import Client
from numpy import array
from scipy.stats import stats
import common
import database
from indicators import mavilimw_bullandbear, atr

PRICE_INTERVAL = Client.KLINE_INTERVAL_1HOUR


class Coin:
    pair = ""
    quantity = 0
    priceDec = 0
    qtyDec = 0
    candles = []
    lastPrice = 0
    prevPrice = 0
    atr = 0
    zScore = 0
    mavilimw = 0
    top = 0
    bottom = 0
    long = None
    short = None
    longHold = None
    shortHold = None
    hasLongOrder = None
    hasShortOrder = None

    def __init__(self, asset):
        self.pair = asset
        self.quantity = futures_database.get_quantity(asset=self.pair)
        self.priceDec, self.qtyDec = futures_database.get_precision(asset=self.pair)
        self.long = futures_database.get_long(asset=self.pair)
        self.short = futures_database.get_short(asset=self.pair)
        self.candles = futures_common.price_action(symbol=self.pair, interval=PRICE_INTERVAL)
        self.atr = atr(klines=self.candles)
        self.candles = array([float(x[4]) for x in self.candles])
        self.mavilimw, self.top, self.bottom = mavilimw_bullandbear(close=self.candles, truncate=4)
        self.zScore = futures_common.truncate(stats.zscore(a=self.candles, axis=0, nan_policy='omit')[-1], 4)
        self.lastPrice = self.candles[-1]
        self.prevPrice = self.candles[-2]
        self.longHold = futures_database.get_long_hold(asset=self.pair)
        self.shortHold = futures_database.get_short_hold(asset=self.pair)
        self.hasLongOrder = futures_database.get_hasLongOrder(asset=self.pair)
        self.hasShortOrder = futures_database.get_hasShortOrder(asset=self.pair)
        del self.candles
