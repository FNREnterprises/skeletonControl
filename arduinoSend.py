
import time
import config

from marvinglobal import skeletonClasses
from marvinglobal import marvinglobal as mg

import feedbackServo

lastSerialSend = [0.0, 0,0]


def sendArduinoCommand(arduinoIndex, msg):
    global lastSerialSend
    if msg[-1] != "\n":
        msg += "\n"
    conn = config.arduinoConn[arduinoIndex]
    if conn is not None:
        #config.log(f"send msg to arduino {arduinoIndex}: {msg}")
        # do not overload the arduino with too many requests
        while time.time() - lastSerialSend[arduinoIndex] < 0.05:
            time.sleep(0.01)
        conn.write(bytes(msg, 'ascii'))
        conn.flush()
        if msg != '1,24': config.log(f"msg to arduino {arduinoIndex}: {bytes(msg, 'ascii')}")   # do not log jaw
        lastSerialSend[arduinoIndex] = time.time()
    else:
        config.log(f"no connection with arduino {arduinoIndex}")


def servoAssign(servoName, lastPos):

    servoStatic = config.servoStaticDictLocal.get(servoName)
    servoType = config.servoTypeDictLocal.get(servoStatic.servoType)

    # send servo definitions to the arduino's
    # both servo and servoType have an inverted flag. for our servo inversion is given if either of them
    # are set, double inversion or no inversion means normal operation of the servo
    invertedFlag = (servoStatic.inverted != servoType.typeInverted)
    inverted = 1 if invertedFlag else 0
    msg = f"0,{servoName},{servoStatic.pin},{servoStatic.minPos},{servoStatic.maxPos},{servoStatic.autoDetach:.1f},{inverted},{lastPos},{servoStatic.powerPin},\n"

    sendArduinoCommand(servoStatic.arduinoIndex, msg)

    config.log(f"assign servo: {servoName:<20}, \
pin: {servoStatic.pin:2}, minPos: {servoStatic.minPos:3}, maxPos:{servoStatic.maxPos:3}, \
restDeg: {servoStatic.restDeg:3}, autoDetach: {servoStatic.autoDetach:4.0f}, inverted: {inverted}, lastPos: {lastPos:3}, powerPin: {servoStatic.powerPin}")


def servoFeedbackDefinitions(arduinoIndex, pin, servoFeedback):
    msg = f"8,{pin},{servoFeedback.i2cMultiplexerAddress},{servoFeedback.i2cMultiplexerChannel},"
    msg += f"{servoFeedback.speedACalcType},{servoFeedback.speedAFactor},{servoFeedback.speedAOffset},"
    msg += f"{servoFeedback.speedBCalcType},{servoFeedback.speedBFactor},{servoFeedback.speedBOffset},"
    msg += f"{servoFeedback.degPerPos},{servoFeedback.servoSpeedRange},\n"

    sendArduinoCommand(arduinoIndex, msg)

    config.log(f"feedback definitions sent: {servoFeedback}")

def requestServoPosition(servoName, newPosition, duration, sequential=True):
    """
    move servo in <duration> seconds from current position to <position>
    filter fast passed in requests
    """
    # command 1,<arduino>,<servo>,<position>,<duration>
    # e.g. servo=eyeX, position=50, duration=2500: 2,3,50,2500
    servoStatic = config.servoStaticDictLocal.get(servoName)
    if not servoStatic.enabled:
        config.log(f"servoPos {newPosition} requested but {servoName} is disabled")
        return

    servoDerived = config.servoDerivedDictLocal.get(servoName)
    servoCurrent = config.servoCurrentDictLocal.get(servoName)
    degrees = mg.evalDegFromPos(servoStatic, servoDerived, newPosition)

    # special case head.jaw, overwrite last move request as we can get lots of requests
    if servoName == "head.jaw":
        deltaPos = abs(config.lastRequestedJawPosition - newPosition)
        minDuration = servoDerived.msPerPos * deltaPos
        #config.log(f"jaw: {config.lastRequestedJawPosition}, {servoCurrent.position}, {sequential=}")
        config.lastRequestedJawPosition = newPosition
    else:
        deltaPos = abs(servoCurrent.position - newPosition)
        minDuration = servoDerived.msPerPos * deltaPos
        config.log(f"request servo position for {servoName}, arduino {servoStatic.arduinoIndex}, degrees: {degrees}, position: {newPosition:.0f}, duration: {duration:.0f}", publish=False)

    # verify duration
    if duration < minDuration:
        #config.log(f"{servoName}: duration increased, deltaPos: {deltaPos:.0f}, msPerPos: {servoDerived.msPerPos:.1f}, from: {duration:.0f} to: {minDuration:.0f}")
        duration = minDuration
    speed = minDuration/duration    # >0..1
    servoCurrent.timeOfLastMoveRequest = time.time()

    msg = f"1,{servoStatic.pin:02.0f},{newPosition:03.0f},{duration:04.0f}\n"

    # for sequential requests add the request to a list and run moves for a single servo in sequence
    if sequential:
        config.moveRequestBuffer.addMoveRequest(
            {'servoName': servoName,
             'arduino': servoStatic.arduinoIndex,
             'msg': msg,
             'speed': speed})
    else:
        # if servo is still moving arduino will terminate the current move and set the new target
        sendArduinoCommand(servoStatic.arduinoIndex, msg)



def requestServoDegrees(servoName, degrees, duration, sequential=True):
    servoStatic: skeletonClasses.ServoStatic = config.servoStaticDictLocal.get(servoName)
    servoDerived: skeletonClasses.ServoDerived = config.servoDerivedDictLocal.get(servoName)
    position = mg.evalPosFromDeg(servoStatic, servoDerived, degrees)
    config.log(f"request servo degrees for {servoName}, {degrees=}, {position=}, {duration=:.0f}", publish=False)
    requestServoPosition(servoName, position, duration, sequential)


def requestServoStop(servoName):
    servoStatic: skeletonClasses.ServoStatic = config.servoStaticDictLocal.get(servoName)
    servoCurrentLocal: skeletonClasses.ServoCurrent = config.servoCurrentDictLocal.get(servoName)

    # clear all buffered requests for the servo
    config.moveRequestBuffer.removeServoFromRequestList(servoName)

    # send stop request to arduino
    msg = f"2,{servoStatic.pin}\n"
    sendArduinoCommand(servoStatic.arduinoIndex, msg)

    if servoCurrentLocal.swiping:
        servoCurrentLocal.swiping = False
        config.updateSharedServoCurrent(servoName, servoCurrentLocal)


def requestAllServosStop():
    config.log(f"all servos stop requested")
    config.moveRequestBuffer.clearBuffer()
    config.moveRequestBuffer.clearServoActiveList()
    msg = f"3\n"
    for i in range(config.numArduinos):
        if config.arduinoConn[i] is not None:
            sendArduinoCommand(i, msg)
    time.sleep(1)   # allow some time to stop


def requestServoStatus(servoName: str):
    servoStatic = config.servoStaticDictLocal.get(servoName)
    msg = f"4,{servoStatic.pin}\n"
    sendArduinoCommand(servoStatic.arduinoIndex, msg)


def setAutoDetach(servoName: str, milliseconds: int):
    servoStatic = config.servoStaticDictLocal.get(servoName)
    msg = f"5,{servoStatic.pin},{milliseconds}\n"
    sendArduinoCommand(servoStatic.arduinoIndex, msg)


def setPosition(servoName: str, newPos: int):
    servoStatic = config.servoStaticDictLocal.get(servoName)
    #servoControl.setPowerPin([servoStatic.powerPin])
    msg = f"6,{servoStatic.pin},{newPos}\n"
    sendArduinoCommand(servoStatic.arduinoIndex, msg)


def setVerbose(servoName: str, state: bool):
    config.log(f"setVerbose through servoName: {servoName} verbose set to {state}")
    servoStatic = config.servoStaticDictLocal.get(servoName)
    servoCurrent = config.servoCurrentDictLocal.get(servoName)
    verboseState = 1 if state else 0
    msg = f"7,{servoStatic.pin},{verboseState},\n"
    sendArduinoCommand(servoStatic.arduinoIndex, msg)

    servoCurrent.verbose = state
    config.updateSharedServoCurrent(servoName, servoCurrent)


def requestRest(servoName: str):
    servoStatic: skeletonClasses.ServoStatic = config.servoStaticDictLocal.get(servoName)
    servoDerived: skeletonClasses.ServoDerived = config.servoDerivedDictLocal.get(servoName)
    if servoStatic.enabled:
        pos = mg.evalPosFromDeg(servoStatic, servoDerived, servoStatic.restDeg)
        requestServoPosition(servoName, pos, 1500)
        time.sleep(0.1)


def requestAllServosRest():
    config.log(f"all servos rest requested")
    for servoName, servoStatic in config.servoStaticDictLocal.items():
        if servoStatic.enabled:
            servoDerived = config.servoDerivedDictLocal.get(servoName)
            pos = mg.evalPosFromDeg(servoStatic, servoDerived, servoStatic.restDeg)
            requestServoPosition(servoName, pos, 1500)
            time.sleep(0.1)
            #config.log(f"rest position for {servoName}, pos: {pos}")


def pinHigh(pinList):
    pins = "".join(c for c in str(pinList) if c not in '[ ]')
    msg = f"h,{pins}\n"
    config.log(f"arduino send pinHigh {msg}", publish=False)
    sendArduinoCommand(0, msg)


def pinLow(pinList):
    pins = "".join(c for c in str(pinList) if c not in '[ ]')
    msg = f"l,{pins}\n"
    config.log(f"arduino send pinLow {msg}", publish=False)
    sendArduinoCommand(0, msg)
