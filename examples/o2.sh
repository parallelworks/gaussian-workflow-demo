#!/bin/bash
#SBATCH -p normal
#SBATCH -J o2
#SBATCH -o o2-%j.out
#SBATCH -e o2-%j.err
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=16
#SBATCH --mem=100GB
#SBATCH --export=ALL
#SBATCH --get-user-env
#SBATCH -t 6:00:00

set echo

umask 0027
echo $SLURM_SUBMIT_DIR
module load gaussian
module list

# default scratch location is /scratch/$USER/gaussian. Users can change it using
 export GAUSS_SCRDIR=/scratch/bhammond/o2
 mkdir -p $GAUSS_SCRDIR
which g16

g16 -y="o2.chk" -m=80GB -c="0-15" < o2.inp > o2.log

rm -rf $GAUSS_SCRDIR
