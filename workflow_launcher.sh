#!/bin/bash
set -x

# Grab current version of parsl_utils
git clone -b dev https://github.com/parallelworks/parsl_utils.git parsl_utils

# If not present, use default local.conf and executors.json
if [ ! -f "local.conf" ]; then
    echo Using default local.conf...
    cp ./examples/local.conf.example ./local.conf
fi

if [ ! -f "executors.json" ]; then
    echo Using default executors.json...
    cp ./examples/executors.json.example ./executors.json
fi

# Cannot run scripts inside parsl_utils directly
bash parsl_utils/main.sh $@

