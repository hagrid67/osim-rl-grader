from flask import Flask, request, jsonify
from functools import wraps
import uuid
import gym
import numpy as np
import six
import argparse
import sys
import requests
import pkg_resources
from gym.wrappers.monitoring import Monitor #, _Monitor
from osim.env import RunEnv
from gym.wrappers.time_limit import TimeLimit
from gym import error

from localsettings import CROWDAI_TOKEN, CROWDAI_URL, CROWDAI_CHALLENGE_ID
from localsettings import REDIS_HOST, REDIS_PORT
from localsettings import DEBUG_MODE
from localsettings import SEED_MAP
from localsettings import CROWDAI_REPLAY_DATA_VERSION
from localsettings import SUBMISSION_WINDOW_TTL, MAX_SUBMISSIONS_PER_WINDOW

from crowdai_worker import worker

import redis
from rq import Queue
import json

import logging
logger = logging.getLogger('werkzeug')
logger.setLevel(logging.ERROR)

"""
    Redis Conneciton Pool Helpers
"""
POOL = redis.ConnectionPool(host=REDIS_HOST, port=REDIS_PORT, db=1)
Q = Queue(connection=redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=1))

def hSet(key, field, value):
    my_server = redis.Redis(connection_pool=POOL)
    my_server.hset(key, field, value)

def rPush(key, value):
    my_server = redis.Redis(connection_pool=POOL)
    my_server.rpush(key, value)

def generate_ttl_message(ttl):
    m, s = divmod(ttl, 60)
    h, m = divmod(m, 60)
    _response = ""
    if h > 0:
        _response += "%d hours " % h
    if m > 0:
        _response += "%d minutes " % m
    if s > 0:
        _response += "%d seconds " % s
    return _response

def respectSubmissionLimit(_key):
    r = redis.Redis(connection_pool=POOL)
    submission_count = r.get(_key)
    if submission_count == None:
        submission_count = 0
    else:
        submission_count = int(submission_count)

    ttl = r.ttl(_key)
    if ttl == None:
        ttl = SUBMISSION_WINDOW_TTL
    TTL_MESSAGE = generate_ttl_message(ttl)

    status = False
    message = ""
    if submission_count == 0:
        r.set(_key, 1)
        r.expire(_key, SUBMISSION_WINDOW_TTL)
        status = True
        message = "You have %d submissions left over the next %s " % (MAX_SUBMISSIONS_PER_WINDOW - 1, TTL_MESSAGE)
    elif submission_count > 0 and submission_count < MAX_SUBMISSIONS_PER_WINDOW:
        r.incr(_key)
        status = True
        message = "You have %d submissions left over the next %s " % (MAX_SUBMISSIONS_PER_WINDOW - 1, TTL_MESSAGE)
    else:
        status = False
        message = "You have already made %d submissions in the last 24 hours. You can make your next submission in %s " % (MAX_SUBMISSIONS_PER_WINDOW, TTL_MESSAGE)
    return (status, message)

"""
    Redis Connection Pool Helpers End
"""

class ChallengeMonitor(Monitor):
    total = 0.0
    def __init__(self, *args, **kwargs):
        super(ChallengeMonitor, self).__init__(*args, **kwargs)
        self.total = 0.0

    def _step(self, *args, **kwargs):
        observation, reward, done, info = super(ChallengeMonitor, self)._step(*args, **kwargs)
        self.total = self.total + reward
        return observation, reward, done, info

    def _reset(self, *args, **kwargs):
        self._before_reset()
        observation = self.env.reset(*args, **kwargs)
        self._after_reset(observation)
        print("Points so far: %f" % self.total)

#        observation = super(ChallengeMonitor, self)._reset(*args, **kwargs)
        return observation


# def ChallengeMonitor(env=None, directory=None, video_callable=None, force=False, resume=False,
#             write_upon_reset=False, uid=None, mode=None):
#     if not isinstance(env, gym.Env):
#         raise error.Error("Monitor decorator syntax is deprecated as of 12/28/2016. Replace your call to `env = gym.wrappers.Monitor(directory)(env)` with `env = gym.wrappers.Monitor(env, directory)`")

#     return _ChallengeMonitor(TimeLimit(env, max_episode_steps=env.spec.timestep_limit), directory, video_callable, force, resume,
# write_upon_reset, uid, mode)


########## Container for environments ##########
class Envs(object):
    """
    Container and manager for the environments instantiated
    on this server.

    When a new environment is created, such as with
    envs.create('CartPole-v0'), it is stored under a short
    identifier (such as '3c657dbc'). Future API calls make
    use of this instance_id to identify which environment
    should be manipulated.
    """
    def __init__(self):
        self.envs = {}
        self.id_len = 8

    def _lookup_env(self, instance_id):
        try:
            return self.envs[instance_id]
        except KeyError:
            raise InvalidUsage('Instance_id {} unknown'.format(instance_id))

    def _remove_env(self, instance_id):
        try:
            del self.envs[instance_id]
        except KeyError:
            raise InvalidUsage('Instance_id {} unknown'.format(instance_id))

    def create(self, env_id, token):
        status, message = respectSubmissionLimit("CROWDAI::SUBMISSION_COUNT::%s" % token)
        if not status:
            raise InvalidUsage(message)

        try:
            osim_envs = {'Run': RunEnv}
            if env_id in osim_envs.keys():
                env = osim_envs[env_id](visualize=False)
            else:
                raise InvalidUsage("Attempted to look up malformed environment ID '{}'".format(env_id))

        except gym.error.Error:
            raise InvalidUsage("Attempted to look up malformed environment ID '{}'".format(env_id))

        instance_id = token + "___" + str(uuid.uuid4().hex)[:10]
        # TODO: that's an ugly way to control the program...
        try:
            self.env_close(instance_id)
        except:
            pass
        self.envs[instance_id] = env

        # Start the relevant data-queues for actions, observations and rewards
        # for the said instance id
        rPush("CROWDAI::SUBMISSION::%s::actions"%(instance_id), "start")
        rPush("CROWDAI::SUBMISSION::%s::observations"%(instance_id), "start")
        rPush("CROWDAI::SUBMISSION::%s::rewards"%(instance_id), "start")

        return instance_id

    def list_all(self):
        return dict([(instance_id, env.spec.id) for (instance_id, env) in self.envs.items()])

    def reset(self, instance_id):
        env = self._lookup_env(instance_id)
        obs = env._reset(difficulty=2, seed=SEED_MAP[env.trial-1])
        env.trial += 1
        if env.trial == len(SEED_MAP)+1:
            obs = None

        rPush("CROWDAI::SUBMISSION::%s::actions"%(instance_id), "reset")
        rPush("CROWDAI::SUBMISSION::%s::observations"%(instance_id), "reset")
        rPush("CROWDAI::SUBMISSION::%s::rewards"%(instance_id), "reset")
        rPush("CROWDAI::SUBMISSION::%s::observations"%(instance_id),repr(obs))
        return env.observation_space.to_jsonable(obs)

    def step(self, instance_id, action, render):
        env = self._lookup_env(instance_id)
        if isinstance( action, six.integer_types ):
            nice_action = action
        else:
            nice_action = np.array(action)
        if render:
            env.render()
         
        serialized_action = repr(nice_action.tolist())
        rPush("CROWDAI::SUBMISSION::%s::actions"%(instance_id), serialized_action)
        deserialized_action = np.array(eval(serialized_action))

        [observation, reward, done, info] = env.step(deserialized_action)
        obs_jsonable = env.observation_space.to_jsonable(observation)

        rPush("CROWDAI::SUBMISSION::%s::observations"%(instance_id), repr(obs_jsonable))
        rPush("CROWDAI::SUBMISSION::%s::rewards"%(instance_id), repr(reward))
        return [obs_jsonable, reward, done, info]

    def get_action_space_contains(self, instance_id, x):
        env = self._lookup_env(instance_id)
        return env.action_space.contains(int(x))

    def get_action_space_info(self, instance_id):
        env = self._lookup_env(instance_id)
        return self._get_space_properties(env.action_space)

    def get_action_space_sample(self, instance_id):
        env = self._lookup_env(instance_id)
        action = env.action_space.sample()
        if isinstance(action, (list, tuple)) or ('numpy' in str(type(action))):
            try:
                action = action.tolist()
            except TypeError:
                print(type(action))
                print('TypeError')
        return action

    def get_action_space_contains(self, instance_id, x):
        env = self._lookup_env(instance_id)
        return env.action_space.contains(int(x))

    def get_observation_space_info(self, instance_id):
        env = self._lookup_env(instance_id)
        return self._get_space_properties(env.observation_space)

    def _get_space_properties(self, space):
        info = {}
        info['name'] = space.__class__.__name__
        if info['name'] == 'Discrete':
            info['n'] = space.n
        elif info['name'] == 'Box':
            info['shape'] = space.shape
            # It's not JSON compliant to have Infinity, -Infinity, NaN.
            # Many newer JSON parsers allow it, but many don't. Notably python json
            # module can read and write such floats. So we only here fix "export version",
            # also make it flat.
            info['low']  = [(x if x != -np.inf else -1e100) for x in np.array(space.low ).flatten()]
            info['high'] = [(x if x != +np.inf else +1e100) for x in np.array(space.high).flatten()]
        elif info['name'] == 'HighLow':
            info['num_rows'] = space.num_rows
            info['matrix'] = [((float(x) if x != -np.inf else -1e100) if x != +np.inf else +1e100) for x in np.array(space.matrix).flatten()]

        return info

    def monitor_start(self, instance_id, directory, force, resume, video_callable):
        env = self._lookup_env(instance_id)
        if video_callable == False:
            v_c = lambda count: False
        else:
            v_c = lambda count: count % video_callable == 0
        self.envs[instance_id] = ChallengeMonitor(env, directory, force=force, resume=resume, video_callable=v_c)
        self.envs[instance_id].trial = 0

    def monitor_close(self, instance_id):
        env = self._lookup_env(instance_id)
        rPush("CROWDAI::SUBMISSION::%s::actions"%(instance_id), "close")
        rPush("CROWDAI::SUBMISSION::%s::observations"%(instance_id), "close")
        rPush("CROWDAI::SUBMISSION::%s::rewards"%(instance_id), "close")

        rPush("CROWDAI::SUBMISSION::%s::actions"%(instance_id), "CROWDAI_REPLAY_DATA_VERSION:"+CROWDAI_REPLAY_DATA_VERSION)
        rPush("CROWDAI::SUBMISSION::%s::observations"%(instance_id), "CROWDAI_REPLAY_DATA_VERSION:"+CROWDAI_REPLAY_DATA_VERSION)
        rPush("CROWDAI::SUBMISSION::%s::rewards"%(instance_id), "CROWDAI_REPLAY_DATA_VERSION:"+CROWDAI_REPLAY_DATA_VERSION)

        SCORE = env.total
        SCORE = SCORE * 1.0 / len(SEED_MAP)

        print("CLOSED %s, %f" % (instance_id, SCORE))
        print("Submitting to crowdAI.org as Stanford...")

        if not DEBUG_MODE:
            headers = {'Authorization': 'Token token="%s"' % CROWDAI_TOKEN}
            r = requests.post(CROWDAI_URL + "?api_key=%s&challenge_id=%d&score=%f&grading_status=graded" % (instance_id.split("___")[0], CROWDAI_CHALLENGE_ID, SCORE), headers=headers)
            if r.status_code != 202:
                return None
            else:
		print r.text
		crowdai_submission_id = json.loads(r.text)["submission_id"]
        rPush("CROWDAI::SUBMITTED_Q", instance_id)


        if not DEBUG_MODE:
	    hSet("CROWDAI::INSTANCE_ID_MAP", instance_id, crowdai_submission_id)
            Q.enqueue(worker, instance_id, timeout=3600)
        ## TO-DO :: Store instance_id -> submission_id mapping in a hash

        return SCORE

    def env_close(self, instance_id):
        env = self._lookup_env(instance_id)
        env.close()
        self._remove_env(instance_id)

########## App setup ##########
app = Flask(__name__)
envs = Envs()

########## Error handling ##########
class InvalidUsage(Exception):
    status_code = 400
    def __init__(self, message, status_code=None, payload=None):
        Exception.__init__(self)
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        self.payload = payload

    def to_dict(self):
        rv = dict(self.payload or ())
        rv['message'] = self.message
        return rv

def get_required_param(json, param):
    if json is None:
        logger.info("Request is not a valid json")
        raise InvalidUsage("Request is not a valid json")
    value = json.get(param, None)
    if (value is None) or (value=='') or (value==[]):
        logger.info("A required request parameter '{}' had value {}".format(param, value))
        raise InvalidUsage("A required request parameter '{}' was not provided".format(param))
    return value

def get_optional_param(json, param, default):
    if json is None:
        logger.info("Request is not a valid json")
        raise InvalidUsage("Request is not a valid json")
    value = json.get(param, None)
    if (value is None) or (value=='') or (value==[]):
        logger.info("An optional request parameter '{}' had value {} and was replaced with default value {}".format(param, value, default))
        value = default
    return value

@app.errorhandler(InvalidUsage)
def handle_invalid_usage(error):
    response = jsonify(error.to_dict())
    response.status_code = error.status_code
    return response

import httplib

def patch_send():
    old_send= httplib.HTTPConnection.send
    def new_send( self, data ):
        print data
        return old_send(self, data) #return is not necessary, but never hurts, in case the library is changed
    httplib.HTTPConnection.send= new_send

#patch_send()

########## API route definitions ##########
@app.route('/v1/envs/', methods=['POST'])
def env_create():
    """
    Create an instance of the specified environment

    Parameters:
        - env_id: gym environment ID string, such as 'CartPole-v0'
    Returns:
        - instance_id: a short identifier (such as '3c657dbc')
        for the created environment instance. The instance_id is
        used in future API calls to identify the environment to be
        manipulated
    """
    env_id = get_required_param(request.get_json(), 'env_id')
    token = get_required_param(request.get_json(), 'token')
    version = get_required_param(request.get_json(), 'version')

    instance_id = envs.create(env_id, token)

    if version != pkg_resources.get_distribution("osim-rl").version:
        response = jsonify(message = "Wrong version. Please update to the new version. Read more on https://github.com/stanfordnmbl/osim-rl/docs")
        response.status_code = 400
        return response

    if DEBUG_MODE:
        response = jsonify(instance_id=instance_id)
        response.status_code = 200
        return response

    headers = {'Authorization': 'Token token="%s"' % CROWDAI_TOKEN}
    r = requests.get(CROWDAI_URL + token, headers=headers)
    response = jsonify(instance_id = instance_id)
    response.status_code = r.status_code

    return response

#@app.route('/v1/envs/', methods=['GET'])
def env_list_all():
    """
    List all environments running on the server

    Returns:
        - envs: dict mapping instance_id to env_id
        (e.g. {'3c657dbc': 'CartPole-v0'}) for every env
        on the server
    """
    all_envs = envs.list_all()
    return jsonify(all_envs = all_envs)

@app.route('/v1/envs/<instance_id>/reset/', methods=['POST'])
def env_reset(instance_id):
    """
    Reset the state of the environment and return an initial
    observation.

    Parameters:
        - instance_id: a short identifier (such as '3c657dbc')
        for the environment instance
    Returns:
        - observation: the initial observation of the space
    """
    observation = envs.reset(instance_id)
    return jsonify(observation = observation)

@app.route('/v1/envs/<instance_id>/step/', methods=['POST'])
def env_step(instance_id):
    """
    Run one timestep of the environment's dynamics.

    Parameters:
        - instance_id: a short identifier (such as '3c657dbc')
        for the environment instance
        - action: an action to take in the environment
    Returns:
        - observation: agent's observation of the current
        environment
        - reward: amount of reward returned after previous action
        - done: whether the episode has ended
        - info: a dict containing auxiliary diagnostic information
    """
    json = request.get_json()
    action = get_required_param(json, 'action')
    render = get_optional_param(json, 'render', False)
    [obs_jsonable, reward, done, info] = envs.step(instance_id, action, render)
    return jsonify(observation = obs_jsonable,
                    reward = reward, done = done, info = info)

#@app.route('/v1/envs/<instance_id>/action_space/', methods=['GET'])
def env_action_space_info(instance_id):
    """
    Get information (name and dimensions/bounds) of the env's
    action_space

    Parameters:
        - instance_id: a short identifier (such as '3c657dbc')
        for the environment instance
    Returns:
    - info: a dict containing 'name' (such as 'Discrete'), and
    additional dimensional info (such as 'n') which varies from
    space to space
    """
    info = envs.get_action_space_info(instance_id)
    return jsonify(info = info)

#@app.route('/v1/envs/<instance_id>/action_space/sample', methods=['GET'])
def env_action_space_sample(instance_id):
    """
    Get a sample from the env's action_space

    Parameters:
        - instance_id: a short identifier (such as '3c657dbc')
        for the environment instance
    Returns:

    	- action: a randomly sampled element belonging to the action_space
    """
    action = envs.get_action_space_sample(instance_id)
    return jsonify(action = action)

#@app.route('/v1/envs/<instance_id>/action_space/contains/<x>', methods=['GET'])
def env_action_space_contains(instance_id, x):
    """
    Assess that value is a member of the env's action_space

    Parameters:
        - instance_id: a short identifier (such as '3c657dbc')
        for the environment instance
	- x: the value to be checked as member
    Returns:
        - member: whether the value passed as parameter belongs to the action_space
    """

    member = envs.get_action_space_contains(instance_id, x)
    return jsonify(member = member)

#@app.route('/v1/envs/<instance_id>/observation_space/', methods=['GET'])
def env_observation_space_info(instance_id):
    """
    Get information (name and dimensions/bounds) of the env's
    observation_space

    Parameters:
        - instance_id: a short identifier (such as '3c657dbc')
        for the environment instance
    Returns:
        - info: a dict containing 'name' (such as 'Discrete'),
        and additional dimensional info (such as 'n') which
        varies from space to space
    """
    info = envs.get_observation_space_info(instance_id)
    return jsonify(info = info)

@app.route('/v1/envs/<instance_id>/monitor/start/', methods=['POST'])
def env_monitor_start(instance_id):
    """
    Start monitoring.

    Parameters:
        - instance_id: a short identifier (such as '3c657dbc')
        for the environment instance
        - force (default=False): Clear out existing training
        data from this directory (by deleting every file
        prefixed with "openaigym.")
        - resume (default=False): Retain the training data
        already in this directory, which will be merged with
        our new data
    """
    j = request.get_json()

    directory = get_required_param(j, 'directory')
    force = get_optional_param(j, 'force', False)
    resume = get_optional_param(j, 'resume', False)
    video_callable = get_optional_param(j, 'video_callable', False)
    #envs.envs['instance_id'] = Monitor(envs.envs['instance_id'], directory)
    envs.monitor_start(instance_id, directory, force, resume, video_callable)
    return ('', 204)

@app.route('/v1/envs/<instance_id>/monitor/close/', methods=['POST'])
def env_monitor_close(instance_id):
    """
    Flush all monitor data to disk.

    Parameters:
        - instance_id: a short identifier (such as '3c657dbc')
          for the environment instance
    """
    total = envs.monitor_close(instance_id)
    response = jsonify(reward = total)
    if total == None:
        response.status_code = 400
    else:
        response.status_code = 200
    return response

@app.route('/v1/envs/<instance_id>/close/', methods=['POST'])
def env_close(instance_id):
    """
    Manually close an environment

    Parameters:
        - instance_id: a short identifier (such as '3c657dbc')
          for the environment instance
    """
    envs.env_close(instance_id)
    return ('', 204)

#@app.route('/v1/upload/', methods=['POST'])
def upload():
    """
    Upload the results of training (as automatically recorded by
    your env's monitor) to OpenAI Gym.

    Parameters:
        - training_dir: A directory containing the results of a
        training run.
        - api_key: Your OpenAI API key
        - algorithm_id (default=None): An arbitrary string
        indicating the paricular version of the algorithm
        (including choices of parameters) you are running.
        """
    j = request.get_json()
    training_dir = get_required_param(j, 'training_dir')
    api_key      = get_required_param(j, 'api_key')
    algorithm_id = get_optional_param(j, 'algorithm_id', None)

    try:
        gym.upload(training_dir, algorithm_id, writeup=None, api_key=api_key,
                   ignore_open_monitors=False)
        return ('', 204)
    except gym.error.AuthenticationError:
        raise InvalidUsage('You must provide an OpenAI Gym API key')

#@app.route('/v1/shutdown/', methods=['POST'])
def shutdown():
    """ Request a server shutdown - currently used by the integration tests to repeatedly create and destroy fresh copies of the server running in a separate thread"""
    f = request.environ.get('werkzeug.server.shutdown')
    f()
    return 'Server shutting down'

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Start a Gym HTTP API server')
    parser.add_argument('-l', '--listen', help='interface to listen to', default='127.0.0.1')
    parser.add_argument('-p', '--port', default=5000, type=int, help='port to bind to')

    args = parser.parse_args()
    print('Server starting at: ' + 'http://{}:{}'.format(args.listen, args.port))
    app.run(host=args.listen, port=args.port, debug=DEBUG_MODE)
