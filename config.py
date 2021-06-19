
import os
import time, datetime
import logging

from marvinglobal import marvinglobal as mg
from marvinglobal import marvinShares
import moveRequestBuffer

numArduinos = 2
arduinoConn = [None] * numArduinos

processName = 'skeletonControl'
marvinShares = None   # shared data

# skeleton control updates its sharedDict's in marvinData
# the dicts owned by the skeleton control itself get updated and queried locally
arduinoDictLocal = {}            # local version of arduinoDict
servoTypeDictLocal = {}
servoStaticDictLocal = {}
servoDerivedDictLocal = {}
servoCurrentDictLocal = {}
servoFeedbackDictLocal = {}

persistedServoPositionsLocal = {}
servoPositionsChanged = False

servoNameByArduinoAndPin = {}   # a dictionary to access servos by Arduino and Id

moveRequestBuffer = moveRequestBuffer.MoveRequestBuffer(verbose=False)

feedbackPositions = {}

# special case jaw servo, keep track of last requested position
lastRequestedJawPosition = 80

def startLogging():
    logging.basicConfig(
        filename=f"log/skeletonControl.log",
        level=logging.INFO,
        format='%(message)s',
        filemode="w")


def log(msg, publish=True):

    logtime = str(datetime.datetime.now())[11:23]
    logging.info(f"{logtime} - {msg}")
    print(f"{logtime} - {msg}")


def updateSharedDict(msg):
    #log(f"updateSharedDict, {msg=}")
    if not marvinShares.updateSharedData(msg):

        log(f"connection with shared data lost, going down") # connection to marvinData lost, try to reconnect
        os._exit(1)

def updateSharedServoCurrent(servoName, servoCurrentLocal):
    msg = {'msgType': mg.SharedDataItems.SERVO_CURRENT, 'sender':processName,
           'info': {'servoName': servoName, 'data': dict(servoCurrentLocal.__dict__)}}
    updateSharedDict(msg)
