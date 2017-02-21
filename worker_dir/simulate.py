#!/usr/bin/env python
import os
import sys
import redis
from osim.env import GaitEnv
import shutil
from utils import *
import requests
import json

REDIS_HOST = str(sys.argv[1])
REDIS_PORT = str(sys.argv[2])
SUBMISSION_ID = str(sys.argv[3])
CROWDAI_TOKEN = str(sys.argv[4])
CROWDAI_URL = str(sys.argv[5])
CROWDAI_CHALLENGE_ID = str(sys.argv[6])
S3_ACCESS_KEY = sys.argv[7]
S3_SECRET_KEY = sys.argv[8]
S3_BUCKET = sys.argv[9]

os.environ["CROWDAI_SUBMISSION_ID"] = SUBMISSION_ID

print REDIS_HOST, REDIS_PORT, SUBMISSION_ID, CROWDAI_TOKEN, CROWDAI_URL, CROWDAI_CHALLENGE_ID
print "Current Working Directory : ", os.path.dirname(os.path.realpath(__file__))

CWD = os.path.dirname(os.path.realpath(__file__))

r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT)

ACTIONS_QUERY = "CROWDAI::SUBMISSION::%s::actions" % SUBMISSION_ID

actions = r.lrange(ACTIONS_QUERY, 0, 1000)
assert actions[0] == "start"
assert actions[-1] == "close"

## Generate Visualization
env = GaitEnv(True)
observation = env.reset()

print "Generating frames for the simulation...."

for _action in actions[1:-1]:
    _action = _action[1:-1]
    _action = _action.split(",")
    _action = [float(x) for x in _action]
    observation, reward, done, info = env.step(_action)
    #print reward
    if done:
        break

##TODO :: Add Error Handling
print "Generating GIF from frames...."
os.system("convert -delay 5 -loop 1 "+CWD+"/../"+SUBMISSION_ID+"/*.png "+CWD+"/"+SUBMISSION_ID+".gif")
print "Generated GIF and saved at : ", CWD+"/"+SUBMISSION_ID+".gif"
print "Cleaning up frames directory...."
shutil.rmtree(CWD+"/../"+SUBMISSION_ID)
# Generate GIF
#Upload to S3
print "Uploading GIF to S3...."
FILE=CWD+"/"+SUBMISSION_ID+".gif"
upload_to_s3(S3_ACCESS_KEY, S3_SECRET_KEY, open(FILE, "rb"), S3_BUCKET, "challenge_"+str(CROWDAI_CHALLENGE_ID)+"/"+SUBMISSION_ID+".gif")
print "Successfully uploaded to S3..."
print "Cleaning up...."
os.remove(FILE)
print "Submitting GIF to CrowdAI...."
crowdai_internal_submission_id = r.hget("CROWDAI::INSTANCE_ID_MAP", SUBMISSION_ID)
headers = {'Authorization': 'Token token="%s"' % CROWDAI_TOKEN}
r = requests.patch(CROWDAI_URL + "%s?submission_id=%s&s3_key=%s" % (crowdai_internal_submission_id.split("___")[0],crowdai_internal_submission_id, "challenge_"+str(CROWDAI_CHALLENGE_ID)+"/"+SUBMISSION_ID+".gif"), headers=headers)
print json.loads(r.text)
if r.status_code == 200:
	print "Successfully Uploaded GIF to CrowdAI..."
else:
	print "Unable to upload GIF CrowdAI...."
