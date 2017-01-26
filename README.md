osim-rl-grader
============

This project provides a grader for the RL task in crowdAI. It is based on openai/gym-http-api

Installation
============
	
    conda create -n opensim-rl -c kidzik opensim
    activate opensim-rl
    conda install -c conda-forge lapack
    conda install flask git
    pip install git+https://github.com/kidzik/osim-rl.git

Getting started
============

To start the server from the command line, run this:

    python gym_http_server.py -p 80 -l [IP]

API specification
============

  * POST `/v1/envs/`
      * Create an instance of the specified environment
      * param: `env_id` -- gym environment ID string, such as 'CartPole-v0'
      * param: `token` -- token from crowdAI
      * returns: `token` -- a short identifier (such as '3c657dbc')
	    for the created environment instance. The token is
        used in future API calls to identify the environment to be
        manipulated

  * POST `/v1/envs/<token>/reset/`
      * Reset the state of the environment and return an initial
        observation.
      * param: `token` -- token from crowdAI
        for the environment instance
      * returns: `observation` -- the initial observation of the space
    
  * POST `/v1/envs/<token>/step/`
      *  Step though an environment using an action.
      * param: `token` -- token from crowdAI
	  * param: `action` -- an action to take in the environment
      * returns: `observation` -- agent's observation of the current
        environment
      * returns: `reward` -- amount of reward returned after previous action
      * returns: `done` -- whether the episode has ended
      * returns: `info` -- a dict containing auxiliary diagnostic information

  * POST `/v1/envs/<token>/monitor/start/`
      * Start monitoring
      * param: `token` -- token from crowdAI
      * param: `force` (default=False) -- Clear out existing training
        data from this directory (by deleting every file
        prefixed with "openaigym.")
      * param: `resume` (default=False) -- Retain the training data
        already in this directory, which will be merged with
        our new data
      * (NOTE: the `video_callable` parameter from the native
    `env.monitor.start` function is NOT implemented)

  * POST `/v1/envs/<token>/monitor/close/`
      * Flush all monitor data to disk
      * param: `token` -- token from crowdAI	
