#!/usr/bin/env python
import os
import sys
import redis
from osim.env.run import RunEnv
import numpy as np

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
SEED_MAP = sys.argv[10]
RENDER_LOGO = int(sys.argv[11]) == 1

SEED_MAP = [int(x) for x in SEED_MAP.split(",")]

os.environ["CROWDAI_SUBMISSION_ID"] = SUBMISSION_ID

print REDIS_HOST, REDIS_PORT, SUBMISSION_ID, CROWDAI_TOKEN, CROWDAI_URL, CROWDAI_CHALLENGE_ID
print "Current Working Directory : ", os.path.dirname(os.path.realpath(__file__))

CWD = os.path.dirname(os.path.realpath(__file__))

r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=1)

ACTIONS_QUERY = "CROWDAI::SUBMISSION::%s::actions" % SUBMISSION_ID

actions = r.lrange(ACTIONS_QUERY, 0, 10000)

## Generate Visualization
env = RunEnv(True)

import json

ACTIONS = []

for _action in actions:
        if _action == "start":
                pass
        elif _action == "reset":
                ACTIONS.append([])
        elif _action == "close":
                pass
        elif _action.startswith("CROWDAI_REPLAY_DATA_VERSION"):
                pass
        else:
                _action = np.array(eval(_action))
                ACTIONS[-1].append(_action)


print "Generating frames for the simulation...."

"""
THe first index will be "start"
the second index will be "reset"
the last index will be "close"

the simulation should stop at the 2nd index
"""

OBSERVATIONS = []
REWARDS = []

for idx, trial in enumerate(ACTIONS):
	if idx >= len(SEED_MAP):
		break
        observation = env.reset(difficulty=2, seed=SEED_MAP[idx-1])
	OBSERVATIONS.append("reset")
	REWARDS.append("reset")
	OBSERVATIONS.append(observation)
	for _action in trial:
		observation, reward, done, info = env.step(_action)
		print observation
		OBSERVATIONS.append(observation)
		REWARDS.append(reward)
		if done:
			break

print "Writing down Observation and rewards logs"
fp = open(CWD+"/data_dir/"+SUBMISSION_ID+"_observation.json", "w")
fp.write(json.dumps(OBSERVATIONS))
fp.close()
fp = open(CWD + "/data_dir/"+SUBMISSION_ID+"_rewards.json", "w")
fp.write(json.dumps(REWARDS))
fp.close()

##TODO :: Add Error Handling
print "Generating GIF from frames...."
os.system("convert -delay 5 -loop 1 "+CWD+"/../"+SUBMISSION_ID+"/*.png "+CWD+"/"+SUBMISSION_ID+".gif")
print "Generated GIF and saved at : ", CWD+"/"+SUBMISSION_ID+".gif"

print "Converting GIF to mp4..."

if RENDER_LOGO:
    target_filename_suffix="_wo_logo"
else:
    target_filename_suffix=""

os.system("ffmpeg -y -an -i "+CWD+"/"+SUBMISSION_ID+".gif -vcodec libx264 -pix_fmt yuv420p -profile:v baseline -level 3 "+CWD+"/"+SUBMISSION_ID+target_filename_suffix+".mp4")

if RENDER_LOGO:
	print "Adding crowdAI watermark..."
	os.system("ffmpeg -i "+CWD+"/"+SUBMISSION_ID+"_wo_logo.mp4 -i "+CWD+"/crowdai-logo.png -filter_complex overlay=10:10 -codec:a copy "+CWD+"/"+SUBMISSION_ID+".mp4")

print "Scaling down mp4 for creating thumbnail...."
os.system("ffmpeg -y -i "+CWD+"/"+SUBMISSION_ID+".mp4 -vf scale=268:200 -c:a copy "+CWD+"/"+SUBMISSION_ID+"_thumb.mp4")

print "Cleaning up frames directory...."
shutil.rmtree(CWD+"/../"+SUBMISSION_ID)
#Upload to S3
print "Uploading GIF to S3...."
FILE=CWD+"/"+SUBMISSION_ID+".gif"
upload_to_s3(S3_ACCESS_KEY, S3_SECRET_KEY, open(FILE, "rb"), S3_BUCKET, "challenge_"+str(CROWDAI_CHALLENGE_ID)+"/"+SUBMISSION_ID+".gif")
print "Cleaning up GIF...."
os.remove(FILE)
print "Uploading mp4 to S3"
FILE=CWD+"/"+SUBMISSION_ID+".mp4"
upload_to_s3(S3_ACCESS_KEY, S3_SECRET_KEY, open(FILE, "rb"), S3_BUCKET, "challenge_"+str(CROWDAI_CHALLENGE_ID)+"/"+SUBMISSION_ID+".mp4")
print "Cleaning up MP4...."
os.remove(FILE)
print "Uploading scaled mp4 to S3"
FILE=CWD+"/"+SUBMISSION_ID+"_thumb.mp4"
upload_to_s3(S3_ACCESS_KEY, S3_SECRET_KEY, open(FILE, "rb"), S3_BUCKET, "challenge_"+str(CROWDAI_CHALLENGE_ID)+"/"+SUBMISSION_ID+"_thumb.mp4")
print "Successfully uploaded media to S3..."
print "Cleaning up Scaled MP4...."
os.remove(FILE)
if RENDER_LOGO:
	FILE=CWD+"/"+SUBMISSION_ID+"_wo_logo.mp4"
	print "Cleaning up intial mp4"
	os.remove(FILE)


print "Submitting media to CrowdAI...."
#TODO: Make these configurable and deal with the changes in the API
headers = {
    'Accept': 'application/vnd.api+json',
    'Content-Type': 'application/vnd.api+json',
    'Authorization': 'Token token={}'.format(CROWDAI_TOKEN)
}

crowdai_internal_submission_id = r.hget("CROWDAI::INSTANCE_ID_MAP", SUBMISSION_ID)
# TODO: Make CROWDAI_URL configurable
CROWDAI_URL = "https://www.crowdai.org/api/external_graders/"+str(crowdai_internal_submission_id)

_payload = {
	"media_large" : "challenge_"+str(CROWDAI_CHALLENGE_ID)+"/"+SUBMISSION_ID+".mp4",
	"media_thumbnail" : "challenge_"+str(CROWDAI_CHALLENGE_ID)+"/"+SUBMISSION_ID+"_thumb.mp4",
	"media_content_type" : "video/mp4"
}
r = requests.patch(CROWDAI_URL, params=_payload, headers=headers,verify=False)
print r.text
if r.status_code == 200:
	print "Successfully Uploaded GIF to CrowdAI..."
else:
	print "Unable to upload GIF CrowdAI...."

import os
os.system("sudo reboot")
