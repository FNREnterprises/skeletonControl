
import os
import sys
import time

import config
from marvinglobal import marvinglobal as mg
from marvinglobal import skeletonClasses

import arduinoSend
import skeletonControl


#####################################
# readMessages runs in its own THREAD
#####################################
def readMessages(arduinoIndex):

    config.log(f"arduinoReceive, start readMessages for arduino: {arduinoIndex}")

    msg = {'cmd': mg.SharedDataItems.ARDUINO, 'sender': config.processName,
           'info': {'arduinoIndex': arduinoIndex, 'data': config.arduinoDictLocal[arduinoIndex]}}
    config.updateSharedDict(msg)

    while True:
        if config.arduinoConn[arduinoIndex] is None:
            time.sleep(0.1)
            continue

        conn = config.arduinoConn[arduinoIndex]

        while conn.is_open:
            bytesAvailable = 0
            try:
                bytesAvailable = conn.in_waiting
            except Exception as e:
                config.log(f"exception in arduino: Is 6V power on?")
                os._exit(2)

            #config.log(f"waiting for arduino message {arduino}, {bytesAvailable=}")
            if bytesAvailable == 0:
                time.sleep(0.1)
                continue
            else:

                recvB = conn.readline()

                #config.log(f"from arduino {arduino}: {recvB}")

                # check for existing shared data connection
                if config.marvinShares is None:
                    continue

                # special case status messages, as these can be very frequently
                # a compressed format is used
                if len(recvB) == 8:
                    s1 = int(recvB[0:2], 16)
                    s2 = int(recvB[2:4], 16)
                    s3 = int(recvB[4:6], 16)

                    # extract data from binary message
                    pin          = s1 & 0x7f
                    newPosition     = s2 - 40           # to prevent value seen as lf 40 is added by the arduino
                    newAssigned     = s3 & 0x01 > 0
                    newMoving       = s3 & 0x02 > 0
                    newAttached     = s3 & 0x04 > 0
                    newAutoDetach   = s3 & 0x08 > 0
                    newServoVerbose = s3 & 0x10 > 0
                    newTargetReached= s3 & 0x20 > 0    # sent only once when target reached


                    servoUniqueId = (arduinoIndex * 100) + pin
                    servoName = config.servoNameByArduinoAndPin[servoUniqueId]

                    if newServoVerbose:
                        config.log(f"servo update {servoName}, {s1:02X},{s2:02X},{s3:02X}, arduino: {arduinoIndex},"
                                   f" pin: {pin:2}, pos {newPosition:3}, assigned: {newAssigned}, moving {newMoving},"
                                   f" attached {newAttached}, autoDetach: {newAutoDetach}, verbose: {newServoVerbose}")

                    prevCurrentDict = config.servoCurrentDictLocal.get(servoName)
                    servoStatic = config.servoStaticDictLocal.get(servoName)
                    servoDerived: skeletonClasses.ServoDerived = config.servoDerivedDictLocal.get(servoName)
                    newDegrees = mg.evalDegFromPos(servoStatic, servoDerived, newPosition)

                    servoCurrentLocal = config.servoCurrentDictLocal[servoName]
                    servoCurrentLocal.assigned = newAssigned
                    servoCurrentLocal.moving = newMoving
                    servoCurrentLocal.attached = newAttached
                    servoCurrentLocal.autoDetach = newAutoDetach
                    servoCurrentLocal.verbose = newServoVerbose
                    servoCurrentLocal.position = newPosition
                    servoCurrentLocal.degrees = newDegrees
                    servoCurrentLocal.swiping = prevCurrentDict.swiping
                    servoCurrentLocal.timeOfLastMoveRequest = prevCurrentDict.timeOfLastMoveRequest
                    config.updateSharedServoCurrent(servoName, servoCurrentLocal)

                     # update ik if running
                    if "stickFigure" in config.marvinShares.processDict.keys():
                        if newPosition != prevCurrentDict.position:
                            config.marvinShares.ikUpdateQueue.put({'msgType': 'update'})
                        #config.log(f"update sent to stickFigure")

                    # check for move target postition reached
                    if newTargetReached:

                        skeletonControl.saveServoPosition(servoName, newPosition)

                        config.log(f"target reached: {servoName=}, {recvB=}")
                        config.moveRequestBuffer.setServoInactive(servoName)

                        # handle special case in swipe mode
                        #config.log(f"{servoName}: not moving and attached, swiping: {prevCurrentDict.swiping}")
                        if prevCurrentDict.swiping:
                            nextPos = 0
                            if abs(newPosition - servoStatic.minPos) < 3:
                                nextPos = servoStatic.maxPos
                            if abs(newPosition - servoStatic.maxPos) < 3:
                                nextPos = servoStatic.minPos
                            swipeMoveDuration = servoDerived.posRange * servoDerived.msPerPos * 2
                            arduinoSend.requestServoPosition(servoName, nextPos, swipeMoveDuration)

                    continue


                # now process all other messages not starting with 0x80 byte
                try:
                    recv = recvB.decode()
                except:
                    config.log(f"problem with decoding arduino msg '{recvB}'")
                    continue

                # config.log(f"line read {recv}")
                # msgID = recvB[0:3].decode()
                config.log(f"<-I{arduinoIndex} " + recv[:-1], publish=False)

                """
                if msgID == "!A0":  # "arduino ready"
                    # lower arduino, index 0, COM7 should reply with !A0
                    config.log(f"!A0 response from {arduinoIndex=}")

                    if arduinoIndex == 1:
                        config.log(f"has left arduino, arduinoIndex 0, a GND connection on Pin 50?")
                        config.log(f"if so, the system has a wrong device/COM-Port assignment")
                        config.log(f"wrong arduino assignment, change in connectWithArduinos, going down")
                        os._exit(3)

                    #config.share.arduinoDict.get(arduino)['connected'] = True
                    config.log(f"ready message from arduino {config.arduinoDictLocal[arduinoIndex]['arduinoName']} received")
                    config.arduinoDictLocal[arduinoIndex]['connected'] = True
                    #updStmt = (mg.SharedDataItems.ARDUINO, arduinoIndex, config.arduinoDictLocal[arduinoIndex])
                    msg = {'cmd': mg.SharedDataItems.ARDUINO, 'sender': config.processName,
                            'info': {'arduinoIndex': arduinoIndex, 'data': config.arduinoDictLocal[arduinoIndex]}}
                    config.updateSharedDict(msg)

                elif msgID == "!A1":  # "arduino ready" from upper arduino
                    # upper arduino, index 1, COM6 should reply with !A1

                    config.log(f"!A1 response from arduino A{arduinoIndex}")

                    if arduinoIndex == 0:
                        config.log(f"has left arduino, arduinoIndex 0, a GND connection on Pin 50?")
                        config.log(f"if so, the system has a wrong device/COM-Port assignment")
                        config.log(f"wrong arduino assignment, change in connectWithArduino, going down")
                        os._exit(4)

                    # config.share.arduinoDict.get(arduino)['connected'] = True
                    config.log(
                        f"ready message from arduino {config.arduinoDictLocal[arduinoIndex]['arduinoName']} received")
                    config.arduinoDictLocal[arduinoIndex]['connected'] = True
                    #updStmt = (mg.SharedDataItems.ARDUINO, arduinoIndex, config.arduinoDictLocal[arduinoIndex])
                    msg = {'cmd': mg.SharedDataItems.ARDUINO, 'sender': config.processName,
                           'info': {'arduinoIndex': arduinoIndex, 'data': config.arduinoDictLocal[arduinoIndex]}}
                    config.updateSharedDict(msg)

                else:
                    try:
                        config.log(f"<-I{arduinoIndex} " + recv[:-1], publish=False)
                    except:
                        config.log(f"Unexpected error on reading messages: {sys.exc_info()[0]}")
                """
