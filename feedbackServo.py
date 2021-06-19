
# feedback servo handling
# create a log of the movements
import config
import datetime
import simplejson as json
from pathlib import Path


def clearPositionList(servoName, speed):
    config.feedbackPositions.update({servoName: {'speed': speed, 'values': []}})

def addPosition(servoName, ms, requestedPosition, currentPosition):
    config.feedbackPositions[servoName]['values'].append([ms, requestedPosition, currentPosition])

def dumpPositionList(servoName):
    filename = f"feedbackData/{servoName}/{str(datetime.datetime.now())[:19]}.json"
    Path(f"feedbackData/{servoName}").mkdir(parents=True, exist_ok=True)
    with open(filename, 'w') as outFile:
        json.dump(config.feedbackPositions[servoName], outFile, indent=0)
    #clearPositionList(servoName)

if __name__ == "__main__":
    clearPositionList('servo', 0.5)
    addPosition('servo', 10, 8)
    addPosition('servo', 15,11)
    dumpPositionList('servo')

