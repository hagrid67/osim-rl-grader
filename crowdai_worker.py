#!/usr/bin/env python
from localsettings import CROWDAI_TOKEN, CROWDAI_URL, CROWDAI_CHALLENGE_ID
from localsettings import S3_ACCESS_KEY, S3_SECRET_KEY, S3_BUCKET
from localsettings import REDIS_HOST, REDIS_PORT
from localsettings import DISPLAY
from localsettings import DEBUG_MODE
import os
import time

def worker(submission_id):
    submission_id = str(submission_id)
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
    COMMAND += S3_SECRET_KEY + " "
    COMMAND += S3_BUCKET
    #Execute Command
    result = os.system(COMMAND)
    if result != 0:
	print "Error in generating and uploading GIF :: ", submission_id
	f = open("error.log", "a")
	f.write("Error in generating and uploading GIF :: " + submission_id+"\n")
	print "Attempting again..."
	f.write("Attempting Again.....")## In case of simbody-visualizer crashes, it usually works out in the second try
	time.sleep(10)
	result = os.system(COMMAND)
	if result != 0:
		print "Error in generating and uploading GIF in the second attempt...", submission_id
		f.write("Error in generating and uploading GIF in the second attempt..." + submission_id+"\n")	
	f.close()
    #Run Simulation as a system call
    #Generate Gif
    #Send request to CrowdAI Server
    # Cleanup your own mess
    # Append entry to a worker_log
