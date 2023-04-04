#!/usr/bin/env python

# This PW workflow is launched from its form in the `Compute` tab.
# The form is defined in workflow.xml
# The workflow is launched by pressing the execute button on the form
# and the chain of execution goes to workflow_launcher.sh, which starts
# the parsl_utils infrastructure which, in turn, starts this main.py.
# This script is the main workflow executor.
#
# In addition to a Miniconda environment containing Parsl, the only other dependency of 
# this workflow is Gaussian, which is assumed to be pre-installed on the system and 
# available via module load gaussian. The Miniconda environment is installed by
# parsl_utils using the information in ./requirements.

# System stuff
import os
from os.path import exists

# Parsl essentials
import parsl
from parsl.app.app import python_app, bash_app

# PW essentials
import parsl_utils
from parsl_utils.config import config, exec_conf
from parsl_utils.data_provider import PWFile

#=====================================
# Step 1: Get inputs from the WORKFLOW FORM
#=====================================
import argparse
    
# For reading command line arguments
def read_args():
    parser=argparse.ArgumentParser()
    parsed, unknown = parser.parse_known_args()
    for arg in unknown:
        if arg.startswith(("-", "--")):
            parser.add_argument(arg)
    pwargs=vars(parser.parse_args())
    print(pwargs)
    return pwargs

# Get any command line arguments
args = read_args()
job_number = args['job_number']

print(args)
print(job_number)

tmp_str=args['inp']
inp_file_list=tmp_str.split('___')

#=====================================
# Step 2: Configure Parsl
#=====================================
print("Configuring Parsl...")

# Original config
print(config)

# Make changes to config
#config.executors[0].worker_debug=False
config.executors[0].provider.mem_per_node=80

# Modified config
print(config)

parsl.load(config)
print("Parsl config loaded.")

#=====================================
# Step 3: Define Parsl workflow apps
#=====================================
# These apps are decorated with Parsl's `@bash_app` and as such 
# are executed in parallel on the compute resources that are 
# defined in the Parsl configuration loaded above.  Functions 
# that are **not** decorated are not executed in parallel on 
# remote resources. The files that need to be staged to remote 
# resources will be marked with Parsl's `File()` (or its PW 
# extension, `Path()`) in the workflow.

print("Defining Parsl workflow apps...")

#===================================
# Launch Gaussian
#===================================
# The Bash lines in the core of this app
# are automatically inserted into an sbatch
# script by Parsl to launch the job on the
# cluster.
# 
# Parsl apps generally have inputs and outputs.
# These are reserved for files whose existance 
# tell Parsl whether the app (and following apps
# that depend on other apps' output) can run. 
# For this simple workflow
# (with only one app) inputs and outputs are
# not stictly necessary but they are included 
# here for templating purposes. Parsl apps can
# also have "normal" variables (e.g. ram and cpu,
# below).
@parsl_utils.parsl_wrappers.log_app
@bash_app(executors=['cluster1'])
def md_run(cpu, ram, inputs=[], outputs=[], stdout='g16.run.stdout', stderr='g16.run.stderr'):
    return '''
    hostname
    echo run_cpu
    echo run_ram
    #mkdir -p {outdir}
    #cd {outdir}
    #{srcdir}/mdlite/runMD.sh "{runopt}" metric.out trj.out
    '''.format(
        run_cpu = cpu,
        run_ram = ram,
        srcdir = inputs[0].local_path,
        outdir = outputs[0].local_path
    )

print("Done defining Parsl workflow apps.")

#===================================
# Step 4: Workflow
#===================================
# This section executes the workflow itself.
print("Running workflow...")

#============================================================================
# SIMULATE
#============================================================================
# The empty list will store the futures of Parsl-parallelized apps. Set the local
# and remote working directories for this app here.
md_run_fut = []
local_dir = os.getcwd()
remote_dir = exec_conf["cluster1"]['RUN_DIR']

for inp, ii in enumerate(inp_file_list):
    # Define remote working (sub)dir for this case
    case_dir = "case_"+str(ii)
    
    # Run simulation
    md_run_fut.append(
        md_run(
            args['cpu'],
	    args['ram'],
            inputs = [
                PWFile(
                    # Rsync with "copy dir by name" no trailing slash convention
                    url = 'file://usercontainer/'+local_dir,
                    local_path = remote_dir+'/src'
                )
            ],
            outputs = [
                PWFile(
                    url = 'file://usercontainer/'+local_dir+'/results/'+case_dir,
                    local_path = remote_dir+'/'+case_dir+'/md'
                )
            ],
            # Any files in outputs directory at end of app are rsynced back
            stdout = remote_dir+'/'+case_dir+'/md/std.out',
            stderr = remote_dir+'/'+case_dir+'/md/std.err'
        )
    )

# Call results for all app futures to require
# execution to wait for all simulations to complete.
for run in md_run_fut:
    run.result()
    
print('Done with simulations.')
