#!/usr/local/bin/python

debug = False
forceOffAfter = 100
powerOffHost = False

import logging
import os
import sys
import time
import ssl

sys.path.append('/usr/local/www')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'freenasUI.settings')

from django.db.models.loading import cache
cache.get_apps()

from pysphere import VIServer, VITask, VIMor
from pysphere.resources import VimService_services as VI

from freenasUI.storage.models import Task
from freenasUI.storage.models import VMWarePlugin

#Monkey patch ssl checking to get back to Python 2.7.8 behavior
ssl._create_default_https_context = ssl._create_unverified_context

# setup ability to log to syslog
log = logging.getLogger()
log.setLevel(logging.DEBUG)

soutformatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
sout = logging.StreamHandler(sys.stdout)
sout.setLevel(logging.DEBUG)
sout.setFormatter(soutformatter)
log.addHandler(sout)

syslogformatter = logging.Formatter('%(name)s - %(levelname)s - %(message)s')
syslog = logging.handlers.SysLogHandler(address='/var/run/log')
syslog.setLevel(logging.WARNING)
syslog.setFormatter(syslogformatter)
log.addHandler(syslog)

# Check if a VM is using a certain datastore
def doesVMDependOnDataStore(vm, dataStore):
    try:
        # simple case, VM config data is on a datastore.
        # not sure how critical it is to snapshot the store that has config data, but best to do so
        if vm.get_property('path').startswith("[%s]" % dataStore):
            return True
        # check if VM has disks on the data store
        # we check both "diskDescriptor" and "diskExtent" types of files
        disks = vm.get_property("disks")
        for disk in disks:
            for file in disk["files"]:
                if file["name"].startswith("[%s]" % dataStore):
                    return True
    except:
        log.debug('Exception in doesVMDependOnDataStore')
    return False

def VMToolsRunning(vm):
    cur_state = vm.get_tools_status()
    if cur_state in ['RUNNING', 'RUNNING_OLD']:
        return True
    else:
        return False

def host_mor(mor):
    if not VIMor.is_mor(mor):
        return VIMor(mor, "HostSystem")
    return mor        

# Get the snapshot tasks
TaskObjects = Task.objects.filter(task_enabled=True)
for task in TaskObjects:

    # Get the filesystems it depends on
    fs = task.task_filesystem
    log.debug("Getting VMs for filesystem %s", fs)
    qs = VMWarePlugin.objects.filter(filesystem=fs)
    for obj in qs:
        server = VIServer()
        try:
            server.connect(obj.hostname, obj.username, obj.get_password())
        except:
            log.warn("VMware login failed to %s", obj.hostname)
            continue
        vmlist = server.get_registered_vms(status='poweredOn')
        for vm in vmlist:
            vm1 = server.get_vm_by_path(vm)
            if doesVMDependOnDataStore(vm1, obj.datastore):
                if(VMToolsRunning(vm1)):
                    if not debug:
                        vm1.shutdown_guest()
                    log.warn("VM: %s Guest Shutdown", vm)
                else:
                    if not debug:
                        vm1.power_off()
                    log.warn("VM: %s Powering Off", vm)

log.info("Waiting %s seconds for VMs to power off", forceOffAfter)
if not debug:
    time.sleep(forceOffAfter)
log.info("Checking if all VMs have shut down")

# Get the snapshot tasks
TaskObjects = Task.objects.filter(task_enabled=True)
for task in TaskObjects:

    # Get the filesystems it depends on
    fs = task.task_filesystem
    log.debug("Getting VMs for filesystem %s", fs)
    qs = VMWarePlugin.objects.filter(filesystem=fs)
    for obj in qs:
        server = VIServer()
        try:
            server.connect(obj.hostname, obj.username, obj.get_password())
        except:
            log.warn("VMware login failed to %s", obj.hostname)
            continue
        vmlist = server.get_registered_vms(status='poweredOn')
        for vm in vmlist:
            vm1 = server.get_vm_by_path(vm)
            if doesVMDependOnDataStore(vm1, obj.datastore):
                if not debug:
                    vm1.power_off()
                log.warn("VM: %s Forcing Off", vm)


log.info("Shutting Down Remaining VMs")
vmlist = server.get_registered_vms(status='poweredOn')
for vm in vmlist:
    vm1 = server.get_vm_by_path(vm)
    if(VMToolsRunning(vm1)):
        if not debug:
            vm1.shutdown_guest()
        log.info("VM: %s Guest Shutdown", vm)
    else:
        if not debug:
            vm1.power_off()
        log.info("VM: %s Powering Off", vm)

if powerOffHost:
    log.info("Triggering host shutdown")
    # Issue shutdown command for hosts
    for host in server.get_hosts():
        log.info("Shutting Down Host: %s", host)
        host = host_mor(host)
        request = VI.ShutdownHost_TaskRequestMsg()
        _this = request.new__this(host)
        _this.set_attribute_type(host.get_attribute_type())
        request.set_element__this(_this)
        request.set_element_force(True)
        if not debug:
            task = server._proxy.ShutdownHost_Task(request)._returnval
