
import time
import config
import arduinoSend
import feedbackServo
#from marvinglobal import marvinglobal as mg

class MoveRequestBuffer:

    def __init__(self, verbose:bool=False):
        self.servoRequestList = []
        self.servoActiveList = []
        self.verbose = verbose
        self.superVerbose = False
        self.excludedServos = ['head.jaw']

    def clearServoActiveList(self):
        if self.verbose: config.log(f"cleared servoActiveList {self.servoActiveList=}")
        self.servoActiveList.clear()

    def setServoActive(self, servoName):
        if servoName in self.excludedServos:
            if self.verbose: config.log(f"set request for servo that is in the exclude list")
            return

        self.servoActiveList.append(servoName)

        if self.verbose: config.log(f"added {servoName} to servoActive list")
        if self.superVerbose: config.log(f"{self.servoActiveList=}")

    def isServoActive(self, servoName):
        return servoName in self.servoActiveList

    def setServoInactive(self, servoName):
        if servoName in self.excludedServos:
            if self.superVerbose: config.log(f"set inactive request for servo that is in the exclude list")
            return

        if servoName not in self.servoActiveList:
            if self.verbose: config.log(f"servoActiveList: remove servo {servoName} failed, not in list")
        else:
            self.servoActiveList.remove(servoName)
            if self.verbose: config.log(f"removed {servoName} from servoActive list")
            if self.superVerbose: config.log(f"{self.servoActiveList=}")

            # check for more requests in request list for this servo
            if self.verbose: config.log(f"{self.servoRequestList=}")
            moreRequests = any(request['servoName'] for request in self.servoRequestList if request['servoName'] == servoName)
            if not moreRequests:
                servoCurrentLocal = config.servoCurrentDictLocal[servoName]
                servoCurrentLocal.inRequestList = False
                config.updateSharedServoCurrent(servoName, servoCurrentLocal)


    def clearBuffer(self):
        self.servoRequestList.clear()


    def isRequestListEmpty(self):
        return len(self.servoRequestList) == 0


    def printRequestList(self):
        config.log(f"{self.servoRequestList=}")


    def addMoveRequest(self, request):

        servoName = request['servoName']
        if servoName in self.excludedServos:
            if self.verbose: config.log(f"add request for servo that is in the moveRequestBuffer exclude list")

            config.log(f"send request directly to arduino {request=}")
            arduinoSend.sendArduinoCommand(request['arduino'], request['msg'])

            return

        self.servoRequestList.append(request)
        servoCurrentLocal = config.servoCurrentDictLocal[servoName]
        servoCurrentLocal.inRequestList = True
        config.updateSharedServoCurrent(servoName, servoCurrentLocal)
        if self.verbose: config.log(f"addMoveToRequestList {request} ")


    def removeServoFromRequestList(self, servoName):
        """
        clear servo from buffered requests because a stop was requested
        :param servoName:
        :return:
        """
        if servoName in self.excludedServos:
            if self.verbose: config.log(f"remove request for servo that is in the moveRequestBuffer exclude list")
            return

        if self.verbose: config.log(f"remove servo from moveRequestBuffer {servoName:20s}, {self.servoRequestList=}")

        for index, item in enumerate(self.servoRequestList):
            if item['servoName'] == servoName:
                self.servoRequestList.pop(index)
                if self.verbose: config.log(f"request removed {index=}: {self.servoRequestList=}")

        self.setServoInactive(servoName)
        if self.verbose: config.log(f"{self.servoActiveList=}")


    def checkForExecutableRequests(self):
        """
        sequential move requests are dequeued from the buffered list when servo is not moving
        :return:
        """
        if self.superVerbose: config.log(f"check for executable request")

        listChanged = True
        while listChanged:
            listChanged = False
            for index, item in enumerate(self.servoRequestList):

                # if more than 1 request for servo in list use only the first one
                if not self.isServoActive(item['servoName']):
                    self.setServoActive(item['servoName'])
                    config.log(f"send request to arduino {item=}")
                    arduinoSend.sendArduinoCommand(item['arduino'], item['msg'])
                    config.log(f"{len(self.servoRequestList)=}, {index=}")

                    # check for feedback servo
                    if item['servoName'] in config.servoFeedbackDictLocal:
                        feedbackServo.clearPositionList(item['servoName'], item['fromPos'], item['toPos'], item['speed'])

                    try:
                        self.servoRequestList.pop(index)
                    except Exception as e:
                        config.log(f"exception in servoRequestList")
                    listChanged = True
                    if self.superVerbose: config.log(f"remaining requests: {self.servoRequestList=}")
                    break


def monitorMoveRequestBuffer():
    while True:
        config.moveRequestBuffer.checkForExecutableRequests()
        time.sleep(0.1)