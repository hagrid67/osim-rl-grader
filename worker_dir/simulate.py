#!/usr/bin/env python
import os
import sys
import redis
from osim.env import GaitEnv

REDIS_HOST = sys.argv[1]
REDIS_PORT = sys.argv[2]
SUBMISSION_ID = sys.argv[3]

print REDIS_HOST, REDIS_PORT, SUBMISSION_ID

r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT)

ACTIONS_QUERY = "CROWDAI::SUBMISSION::%s::actions" % SUBMISSION_ID

actions = r.lrange(ACTIONS_QUERY, 0, 1000)
assert actions[0] == "start"
assert actions[-1] == "close"

## Generate Visualization
env = GaitEnv(True)
observation = env.reset()

for _action in actions[1:-1]:
    _action = _action[1:-1]
    _action = _action.split(",")
    _action = [float(x) for x in _action]
    observation, reward, done, info = env.step(_action)
    print reward
    if done:
        break

# Generate GIF
