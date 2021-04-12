
import copy
import config
import arduinoSend
from marvinglobal import marvinglobal as mg
from marvinglobal import skeletonClasses

#    def assign(self, requestQueue, servoName, initialPosition):
#        requestQueue.put({'cmd': 'assign', 'servoName': servoName, 'position': initialPosition})
def assign(request):
    arduinoSend.servoAssign(request['servoName'], request['position'])


def reassign(msg):
    # when servo definitions are changed through the gui the local
    # dict needs to use the new shared dict values
    servoName = msg['info']['servoName']
    sharedServoStatic = config.marvinShares.servoStaticDict.get(servoName)
    config.servoStaticDictLocal[servoName] = copy.deepcopy(sharedServoStatic)

    sharedServoDerived = config.marvinShares.servoDerivedDict.get(servoName)
    config.servoDerivedDictLocal[servoName] = copy.deepcopy(sharedServoDerived)

    currentPos = config.servoCurrentDictLocal.get(servoName).position
    arduinoSend.servoAssign(servoName, currentPos)

#    def stop(self, requestQueue, servoName):
#        requestQueue.put({'cmd': 'stop', 'servoName': servoName})
def stop(request):
    arduinoSend.requestServoStop(request['servoName'])

# move servo to position 0..180
def position(request):
    #config.log(f"{request=}")
    arduinoSend.requestServoPosition(request['servoName'], request['position'], request['duration'],request['sequential'])

# move servo to requested degrees
def requestDegrees(request):
    arduinoSend.requestServoDegrees(request['servoName'], request['degrees'], request['duration'], request['sequential'])

#    def setVerbose(self, requestQueue, servoName, verbose):
#        requestQueue.put({'cmd': 'setVerbose', 'servoName': servoName, 'verbose': verbose})
def setVerboseRequest(request):
    arduinoSend.setVerbose(request['servoName'], request['verboseOn'])

#    def allServoStop(self, requestQueue):
#        requestQueue.put({'cmd': 'allServoStop'})
def allServoStop(request):
    arduinoSend.requestAllServosStop()

#    def allServoRest(self, requestQueue):
#        requestQueue.put({'cmd': 'allServoRest'})
def allServoRest(request):
    arduinoSend.requestAllServosRest()

#    def setAutoDetach(self, requestQueue, servoName, duration):
#        requestQueue.put({'cmd': 'setAutoDetach', 'servoName': servoName, 'duration': duration})
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
    #msg = {'cmd': mg.SharedDataItems.SERVO_CURRENT, 'sender': config.processName,
    #       'info': {'servoName': servoName, 'data': servoCurrentLocal.__dict__}}
    #config.updateSharedDict(msg)
    arduinoSend.requestRest(servoName)

# test git 2