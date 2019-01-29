This will automatically shut down all the VMs dependant on filesystems exported by the NAS
it will also shut down the rest of the VMs and power off the host

This script is designed to run as the shutdown script under UPS services. 

It figures out which VMs are dependant on datastores by looking at the VMWare-Snapshots tasks in FreeNAS. 
And VMs dependant on datastores listed under VMWare snapshots will be shut down first. 
Once all those VMs are shutdown, it will shutdown the remainder of the VMs on the host. 
It uses the credentials as provided in the FreeNAS Gui for snapshots to communicate with the VMWare server.



