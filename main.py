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
    return pwargs

# Get any command line arguments
args = read_args()
job_number = args['job_number']

print(args)
print(job_number)

inp_file_list=args['inp'].split('___')
print(inp_file_list)

#=====================================
# Step 2: Configure Parsl
#=====================================
print("Configuring Parsl...")

# Original config
#print(config)

# Make changes to config
#config.executors[0].worker_debug=False
if args['ram'] == "0":
    # Use all avail RAM on node
    config.executors[0].provider.mem_per_node=int(args['ram'])
else:
    # Add 20GB overhead to account for Gaussian binaries
    config.executors[0].provider.mem_per_node=int(args['ram'])+20

# Set partition
config.executors[0].provider.partition=args['partition']

# Blank default Gaussian GPU option
gpu_opt = " "
ngpu=int(args['num_gpu'])
if ngpu > 0:
    # Add --gpus-per-node SLURM directive
    config.executors[0].provider.scheduler_options = '--gpus-per-node='+args['num_gpu']

    # Build the Gaussian GPU option flag
    gpu_opt = "-g=\"0-"+str(ngpu-1)+"=0-"+str(ngpu-1)+"\""

# Set cores_per_node
config.executors[0].provider.cores_per_node=int(args['cpu'])

# Overwrite scheduler_directives with AECM options
# Force partition here - TESTING
config.executors[0].provider.scheduler_options='\n#SBATCH --get-user-env\n#SBATCH --export=ALL\n#SBATCH --partition '+args['partition']+'\n'


# Modified config
print('================Parsl Config=================')
print(config)
print('=============================================')

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
def g16_run(cpu, ram, gpu, pre, inp, job, inputs=[], outputs=[], stdout='g16.run.stdout', stderr='g16.run.stderr'):
    return '''
    module load gaussian
    bn=$(basename {inp_file} .inp)
    export GAUSS_SCRDIR=/scratch/$USER/$bn
    mkdir -p $GAUSS_SCRDIR
    out_dir={prefix}/$bn.{job_num}
    mkdir -p $out_dir
    cd {prefix}
    cp $bn.inp $out_dir
    cp $bn.chk $out_dir
    cd $out_dir
    which g16
    g16 -y=$bn.chk -m={run_ram}GB -c="0-{run_cpu}" {gpu_opt} < $bn.inp > $bn.log
    rm -rf $GAUSS_SCRDIR
    '''.format( 
        run_cpu = cpu,
        run_ram = ram,
        gpu_opt = gpu,
        prefix = pre,
        inp_file = inp,
        job_num = job
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
futures = []
local_dir = os.getcwd()
remote_dir = exec_conf["cluster1"]['RUN_DIR']

print("local_dir "+local_dir)
print("remote_dir "+remote_dir)

for ii, inp in enumerate(inp_file_list):
    
    print("In loop iteration "+str(ii)+" for file "+inp)
    
    # Run simulation
    # Subtract 1 from CPU because g16 starts counting
    # at 0 instead of 1 but SLURM counts starting at 1.
    futures.append(
        g16_run(
            cpu = (int(args['cpu']) - 1),
	    ram = int(args['ram']),
            gpu = gpu_opt,
            pre = args['prefix'],
            inp = inp,
            job = args['job_number'],
            inputs = [],
            outputs = [],
            stdout = args['prefix']"/"+inp+"."+args['job_number']+'.stdout'
            stderr = args['prefix']"/"+inp+"."+args['job_number']+'.stderr'
        )
    )

# Call results for all app futures to require
# execution to wait for all simulations to complete.
for run in futures:
    run.result()
    
print('Done with simulations.')
