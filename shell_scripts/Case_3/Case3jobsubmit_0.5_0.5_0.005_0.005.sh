#!/bin/sh
#Set the job name (for your reference)
#PBS -N ML-Silicon-Anode
### Set the project name, your department code by default
#PBS -P ee
### Request email when job begins and ends
#PBS -m bea
### Specify email address to use for notification.
#PBS -M $ee1200560@iitd.ac.in
### chunk specific resources ###(select=5:ncpus=4:mpiprocs=4:ngpus=2:mem=2GB::centos=skylake etc.)
#PBS -l select=2:ncpus=2:mpiprocs=2:centos=haswell
### Specify "wallclock time" required for this job, hhh:mm:ss
#PBS -l walltime=12:30:00
#PBS -l software=Python3


## Keep single # before PBS to consider it as command ,
## more than one # before PBS considered as comment.
## any command/statement other than PBS starting with # is considered as comment.
## Please comment/uncomment the portion as per your requirement before submitting job



#Environment Setup
echo "==============================="
echo $PBS_JOBID
cd $PBS_O_WORKDIR

#job execution command
source /home/apps/skeleton/condaBaseEnv
conda activate PINN
python3 CRT_case3_0.5_0.5_0.005_0.005.py 

