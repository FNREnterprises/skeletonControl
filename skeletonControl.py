
import os, sys
import time
import serial   # pip install pyserial
import threading
import simplejson as json
import queue

from marvinglobal import marvinglobal as mg
from marvinglobal import marvinShares
from marvinglobal import skeletonClasses

import config

import arduinoSend
import arduinoReceive
import skeletonRequests


def openSerial(arduinoIndex):
    #{'arduinoIndex', 'arduinoName', 'comPort', 'connected'}

    arduinoData = config.arduinoDictLocal[arduinoIndex]
    if arduinoData['comPort'] == "unassigned":
        return True
    conn = None
    try:
        conn = serial.Serial(arduinoData['comPort'])
        # try to reset the arduino
        conn.setDTR(False)
        time.sleep(0.2)
        conn.setDTR(True)
        time.sleep(0.2)
        conn.baudrate = 115200
        conn.writeTimeout = 0
        #config.log(f"serial connection with arduino {a['arduinoIndex']}, {a['arduinoName']} on {a['comPort']} initialized")

        config.log(f"serial connection with arduino {arduinoData['arduinoName']} set")
        config.arduinoConn[arduinoIndex] = conn

        return True

    except Exception as eSerial:
        config.log(f"exception on serial connect with arduino: {arduinoData['arduinoName']}, comPort: {arduinoData['comPort']}, {eSerial}, going down")
        if conn is not None:
            try:
                conn.close()
            except Exception as e2:
                config.log(f"conn.close failed, {e2}")
        sys.exit(5)



def assignServos(arduinoIndex):
    """
    servo definitions are stored in a json file
    for each servo handled by the <arduinoIndex> send the definitions to the arduino
    :param arduinoIndex:
    :return:
    """

    config.log(f"send servo definitions to arduino {arduinoIndex} and set current position to last persisted position")

    # send servo definition data to arduino
    for servoName, servoStatic in config.servoStaticDictLocal.items():

        if servoStatic.enabled and servoStatic.arduinoIndex == arduinoIndex:

            config.log(f"servo assign {servoName}, last persisted position: {config.servoCurrentDictLocal.get(servoName).position}")
            arduinoSend.servoAssign(servoName, config.servoCurrentDictLocal.get(servoName).position)
            time.sleep(0.2)     # add delay as arduino gets overwhelmed otherwise

    # then move the servos to the last persisted position
    for servoName, servoStatic in config.servoStaticDictLocal.items():

        if servoStatic.enabled and servoStatic.arduinoIndex == arduinoIndex:
            arduinoSend.requestServoPosition(servoName, config.servoCurrentDictLocal.get(servoName).position, 1000)


def saveServoPosition(servoName, position, maxDelay=10):
    '''
    save current servo position to json file if last safe time differs
    more than maxDelay seconds
    '''
    config.persistedServoPositionsLocal[servoName] = position
    config.servoPositionsChanged = True


def persistServoPositions():

    with open(mg.PERSISTED_SERVO_POSITIONS_FILE, 'w') as outfile:
        json.dump(config.persistedServoPositionsLocal, outfile, indent=2)


def initServoControl():

    def loadServoTypes():
        # servo types
        config.log(f"open servo types file {mg.SERVO_TYPE_DEFINITIONS_FILE}")
        try:
            with open(mg.SERVO_TYPE_DEFINITIONS_FILE, 'r') as infile:
                servoTypeDefinitions = json.load(infile)
            with open(mg.SERVO_TYPE_DEFINITIONS_FILE + ".bak", 'w') as outfile:
                json.dump(servoTypeDefinitions, outfile, indent=2)

        except Exception as e:
            config.log(f"missing {mg.SERVO_TYPE_DEFINITIONS_FILE} file, try using the backup file")
            os._exit(6)

        for servoTypeName, servoTypeData in servoTypeDefinitions.items():
            servoType = skeletonClasses.ServoType(servoTypeData)   # inst of servoTypeData class
            config.servoTypeDictLocal.update({servoTypeName: servoType})

            # add servoTypes to shared data
            #updStmt = (mg.SharedDataItem.SERVO_TYPE, servoTypeName, dict(servoType.__dict__))
            msg = {'cmd': mg.SharedDataItem.SERVO_TYPE, 'sender': config.processName,
                   'info': {'type': servoTypeName, 'data': dict(servoType.__dict__)}}
            config.updateSharedDict(msg)

        config.log(f"servoTypeDict loaded")


    def loadServoStaticDefinitions():

        try:
            with open(mg.SERVO_STATIC_DEFINITIONS_FILE, 'r') as infile:
                servoStaticDefinitions = json.load(infile)
            # if successfully read create a backup just in case
            with open(mg.SERVO_STATIC_DEFINITIONS_FILE + ".bak", 'w') as outfile:
                json.dump(servoStaticDefinitions, outfile, indent=2)

        except Exception as e:
            config.log(f"missing {mg.SERVO_STATIC_DEFINITIONS_FILE} file, try using the backup file")
            os._exit(7)

        for servoName in servoStaticDefinitions:
            servoStatic = skeletonClasses.ServoStatic(servoStaticDefinitions[servoName])
            servoType = config.servoTypeDictLocal[servoStatic.servoType]

            # data cleansing
            # BE AWARE: inversion is handled in the arduino only, maxPos > minPos is a MUST!
            # check for valid min/max position values in servo type definition
            if servoType.typeMaxPos < servoType.typeMinPos:
                config.log(f"wrong servo type values, typeMaxPos < typeMinPos, servo disabled")
                servoStatic.enabled = False

            # check for valid min/max degree values in servo definition
            if servoStatic.maxDeg < servoStatic.minDeg:
                config.log(f"wrong servo min/max values, maxDeg < minDeg for {servoName}, servo disabled")
                servoStatic.enabled = False

            # check for servo values in range of servo type definition
            if servoStatic.minPos < servoType.typeMinPos:
                config.log(f"servo min pos lower than servo type min pos for {servoName}, servo min pos adjusted")
                servoStatic.minPos = servoType.typeMinPos

            if servoStatic.maxPos > servoType.typeMaxPos:
                config.log(f"servo max pos higher than servo type max pos for {servoName}, servo max pos adjusted")
                servoStatic.maxPos = servoType.typeMaxPos

            # add object to the servoStaticDict
            config.servoStaticDictLocal.update({servoName: servoStatic})

            # populate the shared version of the dict
            #updStmt = (mg.SharedDataItem.SERVO_STATIC, servoName, dict(servoStatic.__dict__))
            msg = {'cmd': mg.SharedDataItem.SERVO_STATIC, 'sender': config.processName,
                   'info': {'servoName': servoName, 'data': dict(servoStatic.__dict__)}}
            config.marvinShares.updateSharedData(msg)

            #config.updateSharedDict(updStmt)

        config.log(f"shared servo data updated")


    def loadServoPositions():

        # global persistedServoPositions, servoCurrentDict

        config.log("load last known servo positions")
        if os.path.isfile(mg.PERSISTED_SERVO_POSITIONS_FILE):
            with open(mg.PERSISTED_SERVO_POSITIONS_FILE, 'r') as infile:
                config.persistedServoPositionsLocal = json.load(infile)
                if len(config.persistedServoPositionsLocal) != len(config.servoStaticDictLocal):
                    config.log(f"mismatch of servoDict and persistedServoPositions")
                    createPersistedDefaultServoPositions()
        else:
            createPersistedDefaultServoPositions()

        # check for valid persisted position
        for servoName in config.servoStaticDictLocal:

            servoStatic:skeletonClasses.ServoStatic = config.servoStaticDictLocal[servoName]

            # try to assign the persisted last known servo position
            try:
                p = config.persistedServoPositionsLocal[servoName]
            except KeyError:
                # in case we do not have a last known servo position use 90 as default
                p = 90

            # set current position to min or max if outside range
            if p < servoStatic.minPos:
                p = servoStatic.minPos
            if p > servoStatic.maxPos:
                p = servoStatic.maxPos

            # create ServoCurrent object
            servoCurrent = skeletonClasses.ServoCurrent()

            servoCurrent.position = p

            # set degrees from pos
            # servoCurrent.degrees = mg.evalDegFromPos(servoName, p)

            # add object to servoCurrentDict with key servoName
            config.servoCurrentDictLocal.update({servoName: servoCurrent})

            # add servoCurrent to shared data
            servoCurrentLocal = config.servoCurrentDictLocal[servoName]
            config.updateSharedServoCurrent(servoName, servoCurrentLocal)
            #msg = {'cmd': mg.SharedDataItem.SERVO_CURRENT, 'sender': config.processName,
            #       'info': {'servoName': servoName, 'data': dict(servoCurrent.__dict__)}}
            #config.updateSharedDict(msg)

        config.log("servoPositions loaded")

    loadServoTypes()
    loadServoStaticDefinitions()

    config.log(f"create servoDerivedDict")
    for servoName, servoStatic in config.servoStaticDictLocal.items():
        servoType = config.servoTypeDictLocal[servoStatic.servoType]
        servoDerived = skeletonClasses.ServoDerived(servoStatic, servoType)
        config.servoDerivedDictLocal.update({servoName: servoDerived})


    loadServoPositions()
    saveServoStaticDict()

    # create a dict to find servo name from arduino and pin (for messages from arduino)
    for servoName, servoStatic in config.servoStaticDictLocal.items():
        config.servoNameByArduinoAndPin.update({config.servoDerivedDictLocal[servoName].servoUniqueId: servoName})
    config.log(f"lookup list for servo by arduino and pin created")

    # assign servos
    #for servoName, servoStatic in config.servoStaticDictLocal.items():
    #    servoDerived:skeletonClasses.ServoDerived = config.servoDerivedDictLocal[servoName]
    #    position = mg.evalPosFromDeg(servoStatic, servoDerived, servoStatic.restDeg)
    #    arduinoSend.servoAssign(servoName, position)
    #    time.sleep(0.1)


def saveServoStaticDict():
    '''
    servoStaticDict is a dict of cServoStatic objects by servoName
    to store it in json revert the objects back to dictionaries
    :return:
    '''
    servoStaticDefinitions = {}
    for servoName, servoObject in config.servoStaticDictLocal.items():
        servoStaticDefinitions.update({servoName: servoObject.__dict__})

    with open(mg.SERVO_STATIC_DEFINITIONS_FILE, 'w') as outfile:
        json.dump(servoStaticDefinitions, outfile, indent=2)

    config.log(f"servoStaticDict saved")


def createPersistedDefaultServoPositions():
    '''
    initialize default servo positions in case of missing or differing json file
    :return:
    '''
    config.persistedServoPositionsLocal = {}
    for servoName in config.servoStaticDictLocal:
        servoStatic = config.servoStaticDictLocal.get(servoName)
        servoDerived = config.servoDerivedDictLocal.get(servoName)
        restPos = mg.evalPosFromDeg(servoStatic, servoDerived, servoStatic.restDeg)
        config.persistedServoPositionsLocal.update({servoName: restPos})
    persistServoPositions()


def connectWithArduinos():

    # add items to the local arduino dict
    # in windows make sure with device manager, port settings, advanced
    # to assign the device to the correct COM port
    config.arduinoDictLocal.update(
        {0: {'arduinoName': 'left, lower arduino', 'comPort': 'COM7', 'connected': False}})
    config.arduinoDictLocal.update(
        {1: {'arduinoName': 'right, upper arduino', 'comPort': 'COM6', 'connected': False}})

    # update the shared copy to be available for other interested processes
    for arduinoIndex, arduinoDict in config.arduinoDictLocal.items():
        #updStmt = (mg.SharedDataItem.ARDUINO, arduinoIndex, arduinoDict)
        msg = {'cmd': mg.SharedDataItem.ARDUINO, 'sender': config.processName,
               'info': {'arduinoIndex': arduinoIndex, 'data': config.arduinoDictLocal[arduinoIndex]}}
        config.updateSharedDict(msg)

    # try to open comm ports
    for arduinoIndex, arduinoData in config.arduinoDictLocal.items():
        if not openSerial(arduinoIndex):
            config.log(f"could not open serial port {arduinoIndex['comPort']}, going down")
            os._exit(8)

    # start serial port receiving threads
    for arduinoIndex,arduinoData in config.arduinoDictLocal.items():

        serialReadThread = threading.Thread(target=arduinoReceive.readMessages, args={arduinoIndex})
        serialReadThread.name = f"arduinoRead_{arduinoIndex}"
        serialReadThread.start()

    # verify connection by requesting a first response from Arduino
    time.sleep(0.5)
    for arduinoIndex, arduinoData in config.arduinoDictLocal.items():
        arduinoSend.requestArduinoReady(arduinoIndex)

    # wait for response from arduinos
    for i in range(100):
        if config.arduinoDictLocal.get(0)['connected'] and config.arduinoDictLocal.get(1)['connected']:
            break
        time.sleep(0.1)

    # check for successful connection with both arduinos
    for arduinoIndex, arduinoData in config.arduinoDictLocal.items():
        if not arduinoData['connected']:
            config.log(f"could not receive serial response from arduino {arduinoData['arduinoName']}, {arduinoData['comPort']}")
            os._exit(9)


    # allow arduinos to report their status
    time.sleep(0.2)


if __name__ == "__main__":

    #config.startLogging()

    config.marvinShares = marvinShares.MarvinShares()
    if not config.marvinShares.sharedDataConnect(config.processName):
        config.log(f"could not connect with marvinData")
        os._exit(10)


    # add own process to shared process list
    config.marvinShares.updateProcessDict(config.processName)

    connectWithArduinos()

    initServoControl()

    # assign servos and move servos to last known persisted position
    for arduinoIndex, arduinoData in config.arduinoDictLocal.items():
        config.log(f"assign servos to arduino {arduinoIndex}, {arduinoData['arduinoName']=}, {arduinoData['comPort']=}")
        assignServos(arduinoIndex)


    # set verbose mode for servos to report more details
    arduinoSend.setVerbose('rightArm.bicep', True)

    config.log(f"skeletonControl ready, waiting for skeleton requests")
    config.log(f"---------------")
    request = {}
    # wait for move requests or timeout
    while True:

        if config.servoPositionsChanged:
            persistServoPositions()
            config.servoPositionsChanged = False

        # check for bufferend servo move requests
        config.moveRequestBuffer.checkForExecutableRequests()

        try:
            config.marvinShares.updateProcessDict(config.processName)
            request = config.marvinShares.skeletonRequestQueue.get(block=True, timeout=1)
        except queue.Empty: # in case of empty queue update processDict only
            continue
        except TimeoutError: # in case of timeout update processDict only
            continue
        except Exception as e:
            config.log(f"exception in waiting for skeleton request, {e=}, going down")
            config.marvinShares.removeProcess(config.processName)
            os._exit(11)

        #config.log(f"skeletonRequestQueue, request received: {request}")

        try:
            if 'servoName' in request.keys():
                # do not log head.jaw requests as they are very frequent
                if request['servoName'] != 'head.jaw':
                    config.log(f"skeletonRequestQueue, request received: {request}")
        except Exception as e:
            config.log(f"invalid request received: {request}")

        # try to call the servo method in module skeletonRequests
        try:
            methodName = request['cmd']
            getattr(skeletonRequests, methodName, lambda: 'unknown')(request)   #skeletonRequests.cmd

        except Exception as e:
            config.log(f"unknown command or failure in function, request [{request}], {e}")


