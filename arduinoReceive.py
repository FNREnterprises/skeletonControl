
import os
import sys
import time

import config
from marvinglobal import marvinglobal as mg
from marvinglobal import skeletonClasses

import arduinoSend
import feedbackServo
import skeletonControl


#####################################
# readMessages runs in its own THREAD
#####################################
def readMessages(arduinoIndex):

    config.log(f"arduinoReceive, start readMessages for arduino: {arduinoIndex}")

    msg = {'msgType': mg.SharedDataItems.ARDUINO, 'sender': config.processName,
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

                # check for existing shared data connection
                if config.marvinShares is None:
                    continue

                try:
                    # special case status messages, as these can be very frequently
                    # a compressed format is used
                    if (recvB[0] & 0xC0) == 0xC0:     # marker for compressed servo status message
                        config.log(f"status msg: {len(recvB)=}, {recvB[0]:#04x},{recvB[1]:#b},{recvB[2]:#04x}")
                        # extract data from binary message
                        pin = recvB[0] & 0x3f               # mask out marker bits
                        newAssigned = recvB[1] & 0x01 > 0
                        newMoving = recvB[1] & 0x02 > 0
                        newAttached = recvB[1] & 0x04 > 0
                        newAutoDetach = recvB[1] & 0x08 > 0
                        newServoVerbose = recvB[1] & 0x10 > 0
                        newTargetReached = recvB[1] & 0x20 > 0  # sent only once when target reached
                        currentPosition = int(recvB[2] - 0x10)  # to prevent value seen as lf 16 is added by the arduino
                        servoWritePosition = currentPosition
                        wantedPosition = currentPosition
                        ms = 0
                        isFeedbackStatus = False
                        if len(recvB) > 4:      # feedback servo message
                            isFeedbackStatus = True
                            ms = (recvB[3] << 8) + recvB[4] - 4096 - 16
                            servoWritePosition = (recvB[5] - 0x10)
                            wantedPosition = (recvB[6] - 0x10)
                            config.log(f"feedback pos: {currentPosition=}, {ms=},{servoWritePosition=},{wantedPosition=}")
                        servoUniqueId = (arduinoIndex * 100) + pin
                        servoName = config.servoNameByArduinoAndPin[servoUniqueId]

                        if newServoVerbose:
                            config.log(f"servo update {servoName}, {recvB[0]:#04x},{recvB[1]:#04x},{recvB[2]:#04x}, arduino: {arduinoIndex},"
                                       f" pin: {pin:2}, pos {currentPosition:3}, assigned: {newAssigned}, moving {newMoving},"
                                       f" attached {newAttached}, autoDetach: {newAutoDetach}, verbose: {newServoVerbose}")

                        prevCurrentDict = config.servoCurrentDictLocal.get(servoName)
                        servoStatic = config.servoStaticDictLocal.get(servoName)
                        servoDerived: skeletonClasses.ServoDerived = config.servoDerivedDictLocal.get(servoName)

                        servoCurrentLocal = config.servoCurrentDictLocal[servoName]
                        servoCurrentLocal.assigned = newAssigned
                        servoCurrentLocal.moving = newMoving
                        servoCurrentLocal.attached = newAttached
                        servoCurrentLocal.autoDetach = newAutoDetach
                        servoCurrentLocal.verbose = newServoVerbose
                        servoCurrentLocal.millisAfterMoveStart = ms
                        servoCurrentLocal.currentPosition = currentPosition
                        servoCurrentLocal.servoWritePosition = servoWritePosition
                        servoCurrentLocal.wantedPosition = wantedPosition
                        servoCurrentLocal.swiping = prevCurrentDict.swiping
                        servoCurrentLocal.timeOfLastMoveRequest = prevCurrentDict.timeOfLastMoveRequest
                        config.updateSharedServoCurrent(servoName, servoCurrentLocal)

                        if servoName != "head.jaw":
                            skeletonControl.saveServoPosition(servoName, currentPosition)

                        # check for feedback status and moving and add to move log
                        if isFeedbackStatus and servoCurrentLocal.moving:
                            feedbackServo.addPosition(servoName, ms, currentPosition, servoWritePosition, wantedPosition)
                            config.log(f"feedbackServo: {servoName=}, {ms=}, {servoWritePosition=}, {currentPosition=}")

                         # update ik if running
                        if "stickFigure" in config.marvinShares.processDict.keys():
                            if currentPosition != prevCurrentDict.currentPosition:
                                config.marvinShares.ikUpdateQueue.put({'msgType': 'update'})
                            #config.log(f"update sent to stickFigure")

                        # check for move target postition reached
                        if newTargetReached:

                            if servoName != 'head.jaw': config.log(f"target reached: {servoName=}, {currentPosition=}")
                            config.moveRequestBuffer.setServoInactive(servoName)

                            # check for feedback servo
                            if servoName in config.servoFeedbackDictLocal:
                                config.log(f"targetReached, feedbackPositions: {len(config.feedbackPositions[servoName]['values'])}")
                                if len(config.feedbackPositions[servoName]['values']) > 5:
                                    feedbackServo.dumpPositionList(servoName)

                            # handle special case in swipe mode
                            #config.log(f"{servoName}: not moving and attached, swiping: {prevCurrentDict.swiping}")
                            if prevCurrentDict.swiping:
                                nextPos = 0
                                if abs(currentPosition - servoStatic.minPos) < 3:
                                    nextPos = servoStatic.maxPos
                                if abs(currentPosition - servoStatic.maxPos) < 3:
                                    nextPos = servoStatic.minPos
                                swipeMoveDuration = servoDerived.posRange * servoDerived.msPerPos * 1.5
                                arduinoSend.requestServoPosition(servoName, nextPos, swipeMoveDuration)

                        continue

                except Exception as e:
                    config.log(f"serial message, unexpected format: {recvB}, ignored, {e=}")
                    continue

                # now process all other messages starting with first byte < 0xC0
                try:
                    recv = recvB.decode()
                except:
                    config.log(f"problem with decoding arduino msg '{recvB}'")
                    continue

                # config.log(f"line read {recv}")
                # msgID = recvB[0:3].decode()
                config.log(f"<-I{arduinoIndex} " + recv[:-1], publish=False)
