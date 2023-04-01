from os.path import exists
    "print('Define workflow inputs...')\n",
    "\n",
    "# Start assuming workflow is launched from the form.\n",
    "run_in_notebook=False\n",
    "\n",
    "if (exists(\"./params.run\")):\n",
    "    print(\"Running from a PW form.\")\n",
    "    \n",
    "else:\n",
    "    print(\"Running from a notebook.\")\n",
    "    \n",
    "    # Set flag for later\n",
    "    run_in_notebook=True\n",
    "    \n",
    "    # Manually set workflow inputs here (same as the\n",
    "    # default values in workflow launch form)\n",
    "    # The ranges of EACH dimension in the parameter\n",
    "    # sweep are defined by the format:\n",
    "    #\n",
    "    # NAME;input;MIN:MAX:STEP\n",
    "    #\n",
    "    #=========================================\n",
    "    # npart = number of particles\n",
    "    # steps = time steps in simulation\n",
    "    # mass = mass of partiles\n",
    "    # trsnaps = number of frames (\"snapshots\") of simulation for animation\n",
    "    #=========================================\n",
    "    params=\"npart;input;25:50:25|steps;input;3000:6000:3000|mass;input;0.01:0.02:0.01|trsnaps;input;5:10:5|\"\n",
    "    \n",
    "    print(params)\n",
    "    \n",
    "    # Write to params.run\n",
    "    with open(\"params.run\",\"w\") as f:\n",
    "        n_char_written = f.write(params+\"\\n\")\n",
    "        \n",
    "    # Run the setup stages for parsl_utils\n",
    "    !time ./workflow_notebook_setup.sh"
   ]
  },
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "## Step 2: Configure Parsl\n",
    "The molecular dynamics software itself is a lightweight, precompiled executable written in C. The executable is distributed with this workflow in `./models/mdlite`, and along with input files, it is staged to the remote resources and does not need to be preinstalled.\n",
    "\n",
    "The core visualization tool used here is a precompiled binary of [c-ray](https://github.com/vkoskiv/c-ray) distributed with this workflow in `./models/c-ray`. The executable is staged to remote resources and does not need to be preinstalled.\n",
    "\n",
    "In addition to a Miniconda environment containing Parsl, the only other dependency of this workflow is ImageMagick's `convert` tool for image format conversion (`.ppm` to `.png`) and building animated `.gif` files from `.png` frames."
   ]
  },
  {
   "cell_type": "code",
   "execution_count": null,
   "metadata": {},
   "outputs": [],
   "source": [
    "# Parsl essentials\n",
    "import parsl\n",
    "\n",
    "# PW essentials\n",
    "import parsl_utils\n",
    "from parsl_utils.config import config, exec_conf\n",
    "from parsl_utils.data_provider import PWFile\n",
    "\n",
    "# For embedding Design Explorer results in notebook\n",
    "from IPython.display import display, HTML\n",
    "\n",
    "# Gather inputs from the WORKFLOW FORM\n",
    "import argparse\n",
    "if (not run_in_notebook):\n",
    "    \n",
    "    # For reading command line arguments\n",
    "    def read_args():\n",
    "        parser=argparse.ArgumentParser()\n",
    "        parsed, unknown = parser.parse_known_args()\n",
    "        for arg in unknown:\n",
    "            if arg.startswith((\"-\", \"--\")):\n",
    "                parser.add_argument(arg)\n",
    "        pwargs=vars(parser.parse_args())\n",
    "        print(pwargs)\n",
    "        return pwargs\n",
    "\n",
    "    # Get any command line arguments\n",
    "    args = read_args()\n",
    "    job_number = args['job_number']\n",
    "\n",
    "    print(args)\n",
    "    print(job_number)\n",
    "\n",
    "print(\"Configuring Parsl...\")\n",
    "parsl.load(config)\n",
    "print(\"Parsl config loaded.\")"
   ]
  },
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "## Step 3: Define Parsl workflow apps\n",
    "These apps are decorated with Parsl's `@bash_app` and as such are executed in parallel on the compute resources that are defined in the PW configuration loaded above.  Functions that are **not** decorated are not executed in parallel on remote resources. The files that need to be staged to remote resources will be marked with Parsl's `File()` (or its PW extension, `Path()`) in the workflow."
   ]
  },
  {
   "cell_type": "code",
   "execution_count": null,
   "metadata": {},
   "outputs": [],
   "source": [
    "print(\"Defining Parsl workflow apps...\")\n",
    "\n",
    "from parsl.app.app import python_app, bash_app\n",
    "import parsl_utils\n",
    "\n",
    "#===================================\n",
    "# Molecular dynamics simulation app\n",
    "#===================================\n",
    "# Sleeps inserted to allow time for\n",
    "# concurrent rsyncs from all invocations\n",
    "# of this app to finish transfering srcdir.\n",
    "@parsl_utils.parsl_wrappers.log_app\n",
    "@bash_app(executors=['cluster1'])\n",
    "def md_run(case_definition, inputs=[], outputs=[], stdout='md.run.stdout', stderr='md.run.stderr'):\n",
    "    return '''\n",
    "    sleep 10\n",
    "    mkdir -p {outdir}\n",
    "    cd {outdir}\n",
    "    {srcdir}/mdlite/runMD.sh \"{runopt}\" metric.out trj.out\n",
    "    '''.format(\n",
    "        runopt = case_definition,\n",
    "        srcdir = inputs[0].local_path,\n",
    "        outdir = outputs[0].local_path\n",
    "    )\n",
    "\n",
    "#===================================\n",
    "# App to render frames for animation\n",
    "#===================================\n",
    "# All frames for a given simulation\n",
    "# are rendered together.\n",
    "\n",
    "# This app takes a very simple \n",
    "# approach to zero padding by adding \n",
    "# integers to 1000.\n",
    "@parsl_utils.parsl_wrappers.log_app\n",
    "@bash_app(executors=['cluster2'])\n",
    "def md_vis(num_frames, inputs=[], outputs=[], stdout='md.vis.stdout', stderr='md.vis.stderr'):\n",
    "    return '''\n",
    "    sleep 10\n",
    "    mkdir -p {outdir}\n",
    "    for (( ff=0; ff<{nf}; ff++ ))\n",
    "    do\n",
    "        frame_num_padded=$((1000+$ff))\n",
    "        {srcdir}/c-ray/renderframe_shared_fs {indir}/md/trj.out {outdir}/f_$frame_num_padded.ppm $ff\n",
    "    done\n",
    "    '''.format(\n",
    "        nf = num_frames,\n",
    "        srcdir = inputs[0].local_path,\n",
    "        indir = inputs[1].local_path,\n",
    "        outdir = outputs[0].local_path\n",
    "    )\n",
    "\n",
    "print(\"Done defining Parsl workflow apps.\")"
   ]
  },
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "## Step 4: Workflow\n",
    "These cells execute the workflow itself.\n",
    "\n",
    "### Molecular dynamics simulation stage"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": null,
   "metadata": {},
   "outputs": [],
   "source": [
    "print(\"Running workflow...\")\n",
    "\n",
    "#============================================================================\n",
    "# SETUP PARAMETER SWEEP\n",
    "#============================================================================\n",
    "# Generate a case list from params.run (the ranges to parameters to sweep)\n",
    "os.system(\"python ./models/mexdex/prepinputs.py params.run cases.list\")\n",
    "\n",
    "# Each line in cases.list is a unique combination of the parameters to sweep.\n",
    "with open(\"cases.list\",\"r\") as f:\n",
    "    cases_list = f.readlines()\n",
    "\n",
    "#============================================================================\n",
    "# SIMULATE\n",
    "#============================================================================\n",
    "# For each line in cases.list, run and visualize a molecular dynamics simulation\n",
    "# The empty list will store the futures of Parsl-parallelized apps. Set the local\n",
    "# and remote working directories for this app here.\n",
    "md_run_fut = []\n",
    "local_dir = os.getcwd()\n",
    "remote_dir = exec_conf[\"cluster1\"]['RUN_DIR']\n",
    "\n",
    "for ii, case in enumerate(cases_list):\n",
    "    # Define remote working (sub)dir for this case\n",
    "    case_dir = \"case_\"+str(ii)\n",
    "    \n",
    "    # Run simulation\n",
    "    md_run_fut.append(\n",
    "        md_run(\n",
    "            case_definition = case,\n",
    "            inputs = [\n",
    "                PWFile(\n",
    "                    # Rsync with \"copy dir by name\" no trailing slash convention\n",
    "                    url = 'file://usercontainer/'+local_dir+'/models/mdlite',\n",
    "                    local_path = remote_dir+'/src'\n",
    "                )\n",
    "            ],\n",
    "            outputs = [\n",
    "                PWFile(\n",
    "                    url = 'file://usercontainer/'+local_dir+'/results/'+case_dir,\n",
    "                    local_path = remote_dir+'/'+case_dir+'/md'\n",
    "                )\n",
    "            ],\n",
    "            # Any files in outputs directory at end of app are rsynced back\n",
    "            stdout = remote_dir+'/'+case_dir+'/md/std.out',\n",
    "            stderr = remote_dir+'/'+case_dir+'/md/std.err'\n",
    "        )\n",
    "    )"
   ]
  },
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "### Examples for interacting with running Parsl jobs"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": null,
   "metadata": {},
   "outputs": [],
   "source": [
    "#md_run_fut[15].__dict__"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": null,
   "metadata": {},
   "outputs": [],
   "source": [
    "#md_run_fut[15].task_def"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": null,
   "metadata": {},
   "outputs": [],
   "source": [
    "#config.executors[0].provider.cancel([\"0\",\"2\",\"15\"])"
   ]
  },
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "### Force workflow to wait for all simulation apps"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": null,
   "metadata": {},
   "outputs": [],
   "source": [
    "# Call results for all app futures to require\n",
    "# execution to wait for all simulations to complete.\n",
    "for run in md_run_fut:\n",
    "    run.result()\n",
    "    \n",
    "print('Done with simulations.')"
   ]
  },
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "### Visualization stage"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": null,
   "metadata": {},
   "outputs": [],
   "source": [
    "#============================================================================\n",
    "# VISUALIZE\n",
    "#============================================================================\n",
    "md_vis_fut = []\n",
    "local_dir = os.getcwd()\n",
    "remote_dir = exec_conf[\"cluster2\"]['RUN_DIR']\n",
    "\n",
    "for ii, case in enumerate(cases_list):\n",
    "    # Define remote working dir for this case\n",
    "    case_dir = \"case_\"+str(ii)\n",
    "        \n",
    "    # Get number of frames to render for this case\n",
    "    nframe = int(case.split(',')[4])\n",
    "    \n",
    "    #=========================================================\n",
    "    # Render all frames for each case in one app.  This approach\n",
    "    # reduces the number of SSH connections (e.g. rsync instances) \n",
    "    # compared to an app that only renders one frame at a time.\n",
    "    md_vis_fut.append(\n",
    "        md_vis(\n",
    "            nframe,\n",
    "            inputs=[\n",
    "                PWFile(\n",
    "                    url = 'file://usercontainer/'+local_dir+'/models/c-ray',\n",
    "                    local_path = remote_dir+'/src'\n",
    "                ),\n",
    "                PWFile(\n",
    "                    url = 'file://usercontainer/'+local_dir+'/results/'+case_dir+'/md',\n",
    "                    local_path = remote_dir+'/'+case_dir\n",
    "                )\n",
    "            ],\n",
    "            outputs=[\n",
    "                PWFile(\n",
    "                    url = 'file://usercontainer/'+local_dir+'/results/'+case_dir,\n",
    "                    local_path = remote_dir+'/'+case_dir+'/vis'\n",
    "                )\n",
    "            ],\n",
    "            stdout = remote_dir+'/'+case_dir+'/vis/std.out',\n",
    "            stderr = remote_dir+'/'+case_dir+'/vis/std.err'\n",
    "        )\n",
    "    )\n",
    "\n",
    "for vis in md_vis_fut:\n",
    "    vis.result()\n",
    "    \n",
    "# Compile frames into movies locally\n",
    "for ii, case in enumerate(cases_list):\n",
    "    os.system(\"cd ./results/case_\"+str(ii)+\"/vis; convert -delay 10 *.ppm mdlite.gif\")\n",
    "\n",
    "# Compile movies into Design Explorer results locally\n",
    "os.system(\"./models/mexdex/postprocess.sh mdlite_dex.csv mdlite_dex.html ./\")\n",
    "\n",
    "print('Done with visualizations.')"
   ]
  },
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "## Step 5: View results\n",
    "This step is only necessary when running directly in a notebook. The outputs of this workflow are stored in the `results` folder and they can be interactively visualized with the Design Explorer by clicking on `mdlite_dex.html` which uses `mdlite_dex.csv` and the data in the `results` folder. The Design Explorer visualization is automatically embedded below."
   ]
  },
  {
   "cell_type": "code",
   "execution_count": null,
   "metadata": {},
   "outputs": [],
   "source": [
    "# Modify width and height to display as wanted\n",
    "from IPython.display import IFrame\n",
    "def designExplorer(url,height=600):\n",
    "    return IFrame(url, width=800, height=height)\n",
    "\n",
    "# Make sure path to datafile=/pw/workflows/mdlite/mdlite_dex.csv is correct\n",
    "nb_cwd = os.getcwd()\n",
    "designExplorer(\n",
    "    '/preview/DesignExplorer/index.html?datafile='+nb_cwd+'/mdlite_dex.csv&colorby=kinetic',\n",
    "    height=600)"
   ]
  },
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "## Step 6: Use notebook to interact directly with simulation results\n",
    "Jupyter notebooks are great because cells can be re-run in isolation as ideas are fine-tuned.  The cell below allows for plotting a new result directly from the simulation outputs; there is no need to re-run the simulation if the plot needs to be modified as the user explores the results."
   ]
  },
  {
   "cell_type": "code",
   "execution_count": null,
   "metadata": {},
   "outputs": [],
   "source": [
    "# Import needed libraries\n",
    "import pandas as pd\n",
    "import numpy as np\n",
    "import glob\n",
    "import math \n",
    "import matplotlib.pyplot as plt"
   ]
  },
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "### Load data and compute statistics"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": null,
   "metadata": {},
   "outputs": [],
   "source": [
    "# All data are in the results/case_* folders.\n",
    "list_of_cases = glob.glob(\"results/case_*\")\n",
    "\n",
    "# Initialize lists to store data for plotting\n",
    "cases = []\n",
    "all_cases_time_val = []\n",
    "all_cases_rt_mean_sq_std = []\n",
    "all_cases_rt_mean_sq_mean = []\n",
    "\n",
    "# Loop through each case\n",
    "for case in list_of_cases:\n",
    "\n",
    "    # Get info about this case\n",
    "    path = case + \"/md/trj.out\"\n",
    "    case_name = case[case.index('case'):]\n",
    "    cases.append(case_name)\n",
    "    \n",
    "    # Load data for this case\n",
    "    data = pd.read_csv(path, sep=\" \")\n",
    "    data.columns=['time', 'var', 'x_pos', 'y_pos', 'z_pos', 'ig0', 'ig1', 'ig2', 'ig3', 'ig4', 'ig5']\n",
    "    t_val = data['time'].unique()\n",
    "    all_cases_time_val.append(t_val)\n",
    "    \n",
    "    # Create and initialize lists of root mean square for std and mean\n",
    "    one_case_rt_mean_sq_std = []\n",
    "    one_case_rt_mean_sq_mean = []\n",
    "\n",
    "    # Loop through each instance in time and compute statistics\n",
    "    for t in t_val:\n",
    "\n",
    "        each_time = data.loc[data['time'] == t, 'x_pos':'z_pos']\n",
    "        all_pos_std = each_time.std()\n",
    "        all_pos_mean = each_time.mean()\n",
    "        \n",
    "        # Calculate root mean square of std and mean (vector magnitude)\n",
    "        # Fix decimal points to 6\n",
    "        rt_mean_sq_std = math.sqrt((all_pos_std['x_pos'])**2 + (all_pos_std['y_pos'])**2 + (all_pos_std['z_pos'])**2)\n",
    "        one_case_rt_mean_sq_std.append(round(rt_mean_sq_std,6))\n",
    "        rt_mean_sq_mean = math.sqrt((all_pos_mean['x_pos'])**2 + (all_pos_mean['y_pos'])**2 + (all_pos_mean['z_pos'])**2)\n",
    "        one_case_rt_mean_sq_mean.append(round(rt_mean_sq_mean,6))\n",
    "        \n",
    "    # After getting all root mean square for std and mean of all time,\n",
    "    # put it in the list for all cases.\n",
    "    all_cases_rt_mean_sq_std.append(one_case_rt_mean_sq_std)\n",
    "    all_cases_rt_mean_sq_mean.append(one_case_rt_mean_sq_mean)"
   ]
  },
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "### Plot"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": null,
   "metadata": {},
   "outputs": [],
   "source": [
    "# Plot side by side root mean square std vs. time \n",
    "# and root mean square mean vs. time\n",
    "fig, (ax0, ax1) = plt.subplots(1,2,figsize=(20,5))\n",
    "\n",
    "# Go through each cases to plot\n",
    "# If desired to see some case not all,\n",
    "# could change range(len(cases)) to range(<some number less than len(cases)>)\n",
    "for c in range(len(cases)):\n",
    "    # Plot root mean square std vs. time with solid line\n",
    "    # and dots for each value (x,y) on the graph\n",
    "    # x-axis is time, y-axis is root mean square std\n",
    "    ax0.plot(all_cases_time_val[c],all_cases_rt_mean_sq_std[c],'-o')\n",
    "    ax0.set_xlabel('Time(s)', fontsize=20)\n",
    "    ax0.set_ylabel('RMS variance of positions', fontsize=15)\n",
    "\n",
    "    # Plot root mean square mean vs. time with solid line\n",
    "    # and squares for each value (x,y) on the graph\n",
    "    # x-axis is time, y-axis is root mean square mean\n",
    "    ax1.plot(all_cases_time_val[c],all_cases_rt_mean_sq_mean[c],'-s')\n",
    "    ax1.set_xlabel('Time(s)', fontsize=20)\n",
    "    ax1.set_ylabel('Magnitude of centroid position', fontsize=15)\n",
    "    \n",
    "# Add legend to show name of each case\n",
    "ax0.legend(cases)\n",
    "ax1.legend(cases)\n",
    "\n",
    "# Add title for each plot\n",
    "ax0.set_title(\"Spread of particle swarm\",\n",
    "              fontsize=25)\n",
    "ax1.set_title(\"Centroid of particle swarm\",\n",
    "              fontsize=25)"
   ]
  },
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "## Step 7: Clean up\n",
    "This step is only necessary when running directly in a notebook. These intermediate and log files are removed to keep the workflow file structure clean if this workflow is pushed into the PW Market Place.  Please feel free to comment out these lines in order to inspect intermediate files as needed. The first two, `params.run` and `cases.list` are explicitly created by the workflow in Steps 1 and 4, respectively.  The other files are generated automatically for logging, keeping track of workers, or starting up workers. **Note that even the results are deleted!**"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": null,
   "metadata": {},
   "outputs": [],
   "source": [
    "if (run_in_notebook):\n",
    "    # Shut down Parsl\n",
    "    parsl.dfk().cleanup()\n",
    "    \n",
    "    # Shut down tunnels\n",
    "    !time ./kill.sh\n",
    "    \n",
    "    # Destroy workdirs on remote clusters\n",
    "    cname = exec_conf[\"cluster1\"][\"POOL\"]\n",
    "    workd = exec_conf[\"cluster1\"]['RUN_DIR']\n",
    "    !ssh {cname}.clusters.pw rm -rf {workd}\n",
    "    \n",
    "    cname = exec_conf[\"cluster2\"][\"POOL\"]\n",
    "    workd = exec_conf[\"cluster2\"]['RUN_DIR']\n",
    "    !ssh {cname}.clusters.pw rm -rf {workd}\n",
    "    \n",
    "    # Delete intermediate files/logs that are NOT core code or results\n",
    "    !rm -f params.run\n",
    "    !rm -f cases.list\n",
    "    !rm -rf runinfo\n",
    "    !rm -rf __pycache__\n",
    "    !rm -rf logs\n",
    "    !rm -rf cluster1\n",
    "    !rm -rf cluster2\n",
    "    !rm -f exec_conf*\n",
    "    !rm -f executors*.json\n",
    "    !rm -f kill.sh\n",
    "    !rm -f local.conf\n",
    "    !rm -f pw.conf\n",
    "    !rm -f vars\n",
    "    !rm -f service.html\n",
    "    \n",
    "    # Delete supporting code (cloned in workflow_notebook_setup.sh)\n",
    "    !rm -rf parsl_utils\n",
    "    \n",
    "    # Delete outputs\n",
    "    !rm -rf ./results\n",
    "    !rm -f mdlite_dex.*"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": null,
   "metadata": {},
   "outputs": [],
   "source": []
  }
 ],
 "metadata": {
  "kernelspec": {
   "display_name": "Python 3 (ipykernel)",
   "language": "python",
   "name": "python3"
  },
  "language_info": {
   "codemirror_mode": {
    "name": "ipython",
    "version": 3
   },
   "file_extension": ".py",
   "mimetype": "text/x-python",
   "name": "python",
   "nbconvert_exporter": "python",
   "pygments_lexer": "ipython3",
   "version": "3.10.4"
  }
 },
 "nbformat": 4,
 "nbformat_minor": 2
}
