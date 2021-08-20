
# feedback servo handling
# create a log of the movements
import os
import time
import config
import datetime
import simplejson as json
import csv
from marvinglobal import marvinglobal as mg
from marvinglobal import skeletonClasses
import arduinoSend

createCsv = True


def loadServoFeedbackDefinitions():
    # feedback definitions
    config.log(f"open servo feedback definition file {mg.SERVO_FEEDBACK_DEFINITIONS_FILE}")
    try:
        with open(mg.SERVO_FEEDBACK_DEFINITIONS_FILE, 'r') as infile:
            servoFeedbackDefinitions = json.load(infile)
        with open(mg.SERVO_FEEDBACK_DEFINITIONS_FILE + ".bak", 'w') as outfile:
            json.dump(servoFeedbackDefinitions, outfile, indent=2)

    except Exception as e:
        config.log(f"problem loading {mg.SERVO_FEEDBACK_DEFINITIONS_FILE} file, try using the backup file, {e}")
        os._exit(6)

    for servoName, servoFeedbackData in servoFeedbackDefinitions.items():
        servoFeedback = skeletonClasses.ServoFeedback()  # inst of servoFeedbackData class
        servoFeedback.updateValues(servoFeedbackData)
        config.servoFeedbackDictLocal.update({servoName: servoFeedback})

        # add servoFeedback to shared data
        # updStmt = (mg.SharedDataItems.SERVO_TYPE, servoTypeName, dict(servoType.__dict__))
        msg = {'msgType': mg.SharedDataItems.SERVO_FEEDBACK, 'sender': config.processName,
               'info': {'servoName': servoName, 'data': dict(servoFeedback.__dict__)}}
        config.updateSharedDict(msg)

    config.log(f"servoFeedbackDict loaded")



def saveServoFeedbackDefinitions():
    # feedback definitions
    config.log(f"save feedback definitions to file {mg.SERVO_FEEDBACK_DEFINITIONS_FILE}")
    servoFeedbackDefinitions = {}
    for servoName, feedbackDefinition in config.servoFeedbackDictLocal.items():
        servoFeedbackDefinitions.update({servoName: feedbackDefinition.__dict__})

    try:
        with open(mg.SERVO_FEEDBACK_DEFINITIONS_FILE, 'w') as outfile:
            json.dump(servoFeedbackDefinitions, outfile, indent=2)

    except Exception as e:
        config.log(f"problem updating {mg.SERVO_FEEDBACK_DEFINITIONS_FILE} file, {e}")
        os._exit(6)

    config.log(f"servoFeedbackDict saved to disk")

def updatePIDValues(servoName, newKp, newKi, newKd):
    servoStatic = config.servoStaticDictLocal[servoName]
    servoFeedback = config.servoFeedbackDictLocal[servoName]
    servoFeedback.kp = newKp
    servoFeedback.ki = newKi
    servoFeedback.kd = newKd
    arduinoSend.servoFeedbackDefinitions(servoStatic.arduinoIndex, servoStatic.pin, servoFeedback)
    saveServoFeedbackDefinitions()

def updateFeedbackMagnetOffset(servoName, newFeedbackMagnetOffset):
    servoStatic = config.servoStaticDictLocal[servoName]
    servoFeedback = config.servoFeedbackDictLocal[servoName]
    servoFeedback.feedbackMagnetOffset = newFeedbackMagnetOffset
    arduinoSend.servoFeedbackDefinitions(servoStatic.arduinoIndex, servoStatic.pin, servoFeedback)
    saveServoFeedbackDefinitions()

def setupFeedbackServos(arduinoIndex):
    """
    feedback servo definitions are stored in a json file
    for each servo handled by the <arduinoIndex> send the definitions to the arduino
    :param arduinoIndex:
    :return:
    """

    config.log(f"send feedback servo definitions to arduino {arduinoIndex}")

    # send servo feedback definitions to arduino
    for servoName, servoFeedback in config.servoFeedbackDictLocal.items():
        servoStatic = config.servoStaticDictLocal[servoName]
        if servoStatic.enabled and servoStatic.arduinoIndex == arduinoIndex:

            config.log(f"servo feedback definitions {servoName}")
            arduinoSend.servoFeedbackDefinitions(arduinoIndex, servoStatic.pin, servoFeedback)
            time.sleep(0.2)     # add delay as arduino gets overwhelmed otherwise


def clearPositionList(servoName, fromPos, toPos, speedRate):
    config.feedbackPositions.update({servoName: {'fromPos': fromPos, 'toPos': toPos, 'speedRate': speedRate, 'values': []}})

def addPosition(servoName, ms, currentPosition, servoWritePosition, plannedPosition):
    config.feedbackPositions[servoName]['values'].append([ms, currentPosition, servoWritePosition, plannedPosition])

def dumpPositionList(servoName):
    fromPos = config.feedbackPositions[servoName]['fromPos']
    toPos = config.feedbackPositions[servoName]['toPos']
    speedRate = config.feedbackPositions[servoName]['speedRate']
    basename = f"feedbackData/{servoName}/{str(datetime.datetime.now())[:10]}"
    os.makedirs(basename, exist_ok=True)
    filename = f"{basename}/{str(datetime.datetime.now())[11:19]}_{fromPos}_{toPos}_{speedRate:.2f}"
    with open(filename + ".json", 'w') as outFile:
        json.dump(config.feedbackPositions[servoName], outFile, indent=0)

    if createCsv:
        with open(filename + '.csv', 'w') as outFile:
            writer = csv.writer(outFile)
            header = ["ms","current","servoWrite","planned"]
            writer.writerow(header)
            for row in config.feedbackPositions[servoName]['values']:
                writer.writerow(row)


if __name__ == "__main__":
    clearPositionList('servo', 90, 100, 0.5)
    addPosition('servo', 10, 8, 20, 7, 6)
    addPosition('servo', 15,11, 21, 6, 7)
    dumpPositionList('servo')

