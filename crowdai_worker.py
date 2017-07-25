#!/usr/bin/env python
from localsettings import CROWDAI_TOKEN, CROWDAI_URL, CROWDAI_CHALLENGE_ID
from localsettings import S3_ACCESS_KEY, S3_SECRET_KEY, S3_BUCKET
from localsettings import REDIS_HOST, REDIS_PORT
from localsettings import DISPLAY
from localsettings import DEBUG_MODE
from localsettings import SEED_MAP
import os
import time
import sys
import redis

def worker(submission_id):
    submission_id = str(submission_id)
    print "Processing : ", submission_id
    COMMAND = ""
    #COMMAND += " DISPLAY="+DISPLAY
    COMMAND += " "+os.getcwd()+"/worker_dir/simulate.py "
    COMMAND += REDIS_HOST+" "
    COMMAND += str(REDIS_PORT)+" "
    COMMAND += submission_id + " "
    COMMAND += CROWDAI_TOKEN + " "
    COMMAND += CROWDAI_URL + " "
    COMMAND += str(CROWDAI_CHALLENGE_ID) + " "
    COMMAND += S3_ACCESS_KEY + " "
    COMMAND += S3_SECRET_KEY + " "
    COMMAND += S3_BUCKET + " "
    COMMAND += str(SEED_MAP[0])
    #Execute Command
    result_count = 0
    while True:
        result = os.system(COMMAND)
        if result != 0:
	    print "Error in generating and uploading GIF :: ", submission_id
	    f = open("error.log", "a")
	    f.write("Error in generating and uploading GIF :: " + submission_id+"\n")
	    print "Attempting again..."
	    f.write("Attempting Again.....")## In case of simbody-visualizer crashes, it usually works out in the second try
	    time.sleep(10)
	    f.close()
            result_count += 1
        else:
            break

        if result_count >= 1:
            break
    #Run Simulation as a system call
    #Generate Gif
    #Send request to CrowdAI Server
    # Cleanup your own mess
    # Append entry to a worker_log

show_action_map = False
if __name__ == '__main__':
	_arg = sys.argv[1]
	data = "instance_id"
	try:
		i = int(_arg)
		data = "submission_id"
	except:
		pass

	if data=="instance_id":
		instance_id = _arg
	else:
		r = redis.Redis(REDIS_HOST, REDIS_PORT, db=1)
		instance_id_map = r.hgetall("CROWDAI::INSTANCE_ID_MAP")
		print "Available Instance IDs for this submission are : "
		found = False
		for _key in instance_id_map:
			if instance_id_map[_key] == _arg:
				print _key
				found = True
				
				if show_action_map:
					ACTIONS_QUERY = "CROWDAI::SUBMISSION::%s::trial_1_actions" % _key
					actions = r.lrange(ACTIONS_QUERY, 0, 10000)
					print actions		
		if found == False:
			print "Sorry no instance_ids found for this submission..."
		else:
			print "Please execute again with the instance_id as a parameter"
		exit(0)

	# TO-DO: Handle case of one instance_id mapping to multiple submission ids	
	internal_submission_id = str(sys.argv[1])
	try:
		submission_id = internal_submission_id
		worker(submission_id)
	except:
		print "Unable to find data for submission id...", internal_submission_id
	#worker(sys.argv[1])	
