#!/usr/bin/env python
from localsettings import CROWDAI_TOKEN, CROWDAI_URL, CROWDAI_CHALLENGE_ID
from localsettings import S3_ACCESS_KEY, S3_SECRET_KEY
from localsettings import REDIS_HOST, REDIS_PORT
from localsettings import DISPLAY
import os

def worker(submission_id):
    print "Processing : ", submission_id
    COMMAND = ""
    COMMAND += " DISPLAY="+DISPLAY
    COMMAND += " "+os.getcwd()+"/worker_dir/simulate.py "
    COMMAND += REDIS_HOST+" "
    COMMAND += str(REDIS_PORT)+" "
    COMMAND += submission_id + " "
    COMMAND += CROWDAI_TOKEN + " "
    COMMAND += CROWDAI_URL + " "
    COMMAND += str(CROWDAI_CHALLENGE_ID) + " "
    COMMAND += S3_ACCESS_KEY + " "
    COMMAND += S3_SECRET_KEY
    #Execute Command
    print os.system(COMMAND)
    #Run Simulation as a system call
    #Generate Gif
    #Send request to CrowdAI Server
    # Cleanup your own mess
    # Append entry to a worker_log
