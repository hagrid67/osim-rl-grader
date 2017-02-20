#!/usr/bin/env python
from localsettings import CROWDAI_TOKEN, CROWDAI_URL, CROWDAI_CHALLENGE_ID
from localsettings import REDIS_HOST, REDIS_PORT

def worker(submission_id):
    R = redis.Redis(host=REDIS_HOST, port=REDIS_PORT))
    print "Processing : ", submission_id
    #Run Simulation as a system call
    #Generate Gif
    #Send request to CrowdAI Server
    # Cleanup your own mess
    # Append entry to a worker_log
