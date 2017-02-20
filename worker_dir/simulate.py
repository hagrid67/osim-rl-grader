#!/usr/bin/env python
import os
import sys

REDIS_HOST = sys.argv[1]
REDIS_PORT = sys.argv[2]
SUBMISSION_ID = sys.argv[3]

print REDIS_HOST, REDIS_PORT, SUBMISSION_ID

r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT)
