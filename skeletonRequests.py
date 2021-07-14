
import copy
import config
import arduinoSend
from marvinglobal import marvinglobal as mg
from marvinglobal import skeletonClasses
import feedbackServo

#    def assign(self, requestQueue, servoName, initialPosition):
#        requestQueue.put({'msgType': 'assign', 'servoName': servoName, 'position': initialPosition})
def assign(request):
    arduinoSend.servoAssign(request['servoName'], request['position'])


def reassign(msg):
    # when servo definitions are changed through the gui the local
    # dict needs to use the new shared dict values
    servoName = msg['info']['servoName']
    servoStaticDict = config.marvinShares.servoDict.get(mg.SharedDataItems.SERVO_STATIC)
    sharedServoStatic = servoStaticDict.get(servoName)
    config.servoStaticDictLocal[servoName] = copy.deepcopy(sharedServoStatic)
    servoDerivedDict = config.marvinShares.servoDict.get(mg.SharedDataItems.SERVO_DERIVED)
    sharedServoDerived = servoDerivedDict.get(servoName)
    config.servoDerivedDictLocal[servoName] = copy.deepcopy(sharedServoDerived)

    currentPos = config.servoCurrentDictLocal.get(servoName).currentPosition
    arduinoSend.servoAssign(servoName, currentPos)

#    def stop(self, requestQueue, servoName):
#        requestQueue.put({'msgType': 'stop', 'servoName': servoName})
def stop(request):
    arduinoSend.requestServoStop(request['servoName'])

# move servo to position 0..180
def position(request):
    #config.log(f"{request=}")
    if "sequential" in request:
        arduinoSend.requestServoPosition(request['servoName'], request['position'], request['duration'],request['sequential'])
    else:
        arduinoSend.requestServoPosition(request['servoName'], request['position'], request['duration'], False)

# move servo to requested degrees
def requestDegrees(request):
    if "sequential" in request:
        arduinoSend.requestServoDegrees(request['servoName'], request['degrees'], request['duration'], request['sequential'])
    else:
        arduinoSend.requestServoDegrees(request['servoName'], request['degrees'], request['duration'], False)

#    def setVerbose(self, requestQueue, servoName, verbose):
#        requestQueue.put({'msgType': 'setVerbose', 'servoName': servoName, 'verbose': verbose})
def requestVerboseState(request):
    arduinoSend.setVerbose(request['servoName'], request['verboseOn'])

#    def allServoStop(self, requestQueue):
#        requestQueue.put({'msgType': 'allServoStop'})
def allServoStop(request):
    arduinoSend.requestAllServosStop()

#    def allServoRest(self, requestQueue):
#        requestQueue.put({'msgType': 'allServoRest'})
def allServoRest(request):
    arduinoSend.requestAllServosRest()

#    def setAutoDetach(self, requestQueue, servoName, duration):
#        requestQueue.put({'msgType': 'setAutoDetach', 'servoName': servoName, 'duration': duration})
def setAutoDetach(request):
    arduinoSend.setAutoDetach(request['servoName'], request['duration']/1000)

# random moves is a separate process
#def startRandomMoves(request):
#    config.log(f"tbd: startRandomMoves requested")

def stopRandomMoves(request):
    # remove process from running process list
    config.marvinShares.removeProcess('randomMoves')

def stopGesture(request):
    # remove process from running process list
    config.marvinShares.removeProcess('playGesture')


def startSwipe(request):
    config.log(f"startSwipe requested")
    servoName = request['servoName']
    servoStatic:skeletonClasses.ServoStatic = config.servoStaticDictLocal.get(servoName)
    servoDerived:skeletonClasses.ServoDerived = config.servoDerivedDictLocal.get(servoName)
    servoCurrentLocal:skeletonClasses.ServoCurrent = config.servoCurrentDictLocal.get(servoName)
    servoCurrentLocal.swiping = True
    config.updateSharedServoCurrent(servoName, servoCurrentLocal)

    minPos = servoStatic.minPos
    swipeMoveDuration = servoDerived.msPerPos * servoDerived.posRange * 2

    arduinoSend.requestServoPosition(servoName, minPos, swipeMoveDuration)
    # continuation of swipe is handled with the end move message in arduinoReceive
    # swiping stop is triggered by button or servo stop/rest request


def stopSwipe(request):
    config.log(f"stopSwipe requested")
    servoName = request['servoName']
    servoCurrentLocal:skeletonClasses.ServoCurrent = config.servoCurrentDictLocal.get(servoName)
    servoCurrentLocal.swiping = False
    config.updateSharedServoCurrent(servoName, servoCurrentLocal)
    #msg = {'msgType': mg.SharedDataItems.SERVO_CURRENT, 'sender': config.processName,
    #       'info': {'servoName': servoName, 'data': servoCurrentLocal.__dict__}}
    #config.updateSharedDict(msg)
    arduinoSend.requestRest(servoName)


def updatePIDValues(request):
    servoName = request['servoName']
    feedbackServo.updatePIDValues(servoName, request['kp'], request['ki'], request['kd'])

# test git 2